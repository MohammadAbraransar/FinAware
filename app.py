import os, sqlite3, csv, io, json, urllib.request, urllib.error
from datetime import datetime, date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response, g
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.environ.get("FINAWARE_DB_PATH", os.path.join(BASE_DIR, "finaware.db"))
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-this-before-deployment")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "0") == "1"
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL,
 email TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 kind TEXT NOT NULL CHECK(kind IN ('income','expense')),
 amount_paise INTEGER NOT NULL CHECK(amount_paise > 0),
 category TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 txn_date TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS budgets (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 category TEXT NOT NULL,
 monthly_limit_paise INTEGER NOT NULL CHECK(monthly_limit_paise > 0),
 UNIQUE(user_id, category)
);
CREATE TABLE IF NOT EXISTS goals (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 title TEXT NOT NULL,
 target_paise INTEGER NOT NULL CHECK(target_paise > 0),
 saved_paise INTEGER NOT NULL DEFAULT 0 CHECK(saved_paise >= 0),
 target_date TEXT,
 created_at TEXT NOT NULL
);
"""
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.executescript(SCHEMA)

@app.before_request
def ensure_db():
    init_db()
    if request.method == "POST":
        token = session.get("_csrf_token")
        supplied = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or token != supplied:
            return "Invalid or expired form token. Refresh the page and try again.", 400

@app.context_processor
def inject_globals():
    if "_csrf_token" not in session:
        import secrets
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return {"csrf_token": session["_csrf_token"], "current_year": datetime.now().year}

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to continue.", "info")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

def current_user():
    if not session.get("user_id"): return None
    return get_db().execute("SELECT id,name,email FROM users WHERE id=?", (session["user_id"],)).fetchone()

def money(paise):
    return round((paise or 0) / 100, 2)

@app.route("/")
def index():
    if session.get("user_id"): return redirect(url_for("dashboard"))
    return render_template("landing.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        if len(name) < 2 or len(name) > 80:
            flash("Enter a name between 2 and 80 characters.", "error")
        elif "@" not in email or len(email) > 254:
            flash("Enter a valid email address.", "error")
        elif len(password) < 10:
            flash("Use a password with at least 10 characters.", "error")
        else:
            try:
                get_db().execute("INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                    (name,email,generate_password_hash(password),datetime.utcnow().isoformat()))
                get_db().commit()
                user = get_db().execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
                session.clear()
                session["user_id"] = user["id"]
                flash("Your account is ready. Add your first real transaction to begin.", "success")
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                flash("An account with that email already exists. Sign in instead.", "error")
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        user=get_db().execute("SELECT id,password_hash FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"]=user["id"]
            return redirect(url_for("dashboard"))
        flash("Email or password is incorrect.", "error")
    return render_template("auth.html", mode="login")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    db=get_db(); uid=session["user_id"]
    month=date.today().strftime("%Y-%m")
    totals=db.execute("""SELECT kind, COALESCE(SUM(amount_paise),0) total FROM transactions
        WHERE user_id=? AND substr(txn_date,1,7)=? GROUP BY kind""",(uid,month)).fetchall()
    summary={"income":0,"expense":0}
    for row in totals: summary[row["kind"]]=money(row["total"])
    summary["balance"]=round(summary["income"]-summary["expense"],2)
    rows=db.execute("""SELECT id,kind,amount_paise,category,description,txn_date FROM transactions
        WHERE user_id=? ORDER BY txn_date DESC,id DESC LIMIT 8""",(uid,)).fetchall()
    transactions=[dict(r, amount=money(r["amount_paise"])) for r in rows]
    budget_rows=db.execute("SELECT category,monthly_limit_paise FROM budgets WHERE user_id=? ORDER BY category",(uid,)).fetchall()
    spent=db.execute("""SELECT category,SUM(amount_paise) total FROM transactions WHERE user_id=? AND kind='expense'
        AND substr(txn_date,1,7)=? GROUP BY category""",(uid,month)).fetchall()
    spent_map={r["category"]:money(r["total"]) for r in spent}
    budgets=[{"category":r["category"],"limit":money(r["monthly_limit_paise"]),
        "spent":spent_map.get(r["category"],0),
        "percent":min(100,round(spent_map.get(r["category"],0)/money(r["monthly_limit_paise"])*100))}
        for r in budget_rows]
    goals=db.execute("SELECT id,title,target_paise,saved_paise,target_date FROM goals WHERE user_id=? ORDER BY id DESC",(uid,)).fetchall()
    goals=[{"id":r["id"],"title":r["title"],"target":money(r["target_paise"]),"saved":money(r["saved_paise"]),
        "target_date":r["target_date"],"percent":min(100,round(money(r["saved_paise"])/money(r["target_paise"])*100))}
        for r in goals]
    return render_template("dashboard.html", user=current_user(), summary=summary, transactions=transactions,
        budgets=budgets, goals=goals, month_label=date.today().strftime("%B %Y"))

@app.route("/transactions", methods=["GET","POST"])
@login_required
def transactions_page():
    db=get_db(); uid=session["user_id"]
    if request.method=="POST":
        kind=request.form.get("kind")
        category=request.form.get("category","").strip()
        description=request.form.get("description","").strip()
        txn_date=request.form.get("txn_date","")
        try: amount=float(request.form.get("amount",""))
        except ValueError: amount=0
        try: date.fromisoformat(txn_date)
        except ValueError: txn_date=""
        if kind not in ("income","expense") or not category or len(category)>60 or amount<=0 or amount>1000000000 or not txn_date:
            flash("Check the transaction type, category, amount and date. Amount must be greater than zero.", "error")
        else:
            db.execute("INSERT INTO transactions(user_id,kind,amount_paise,category,description,txn_date,created_at) VALUES(?,?,?,?,?,?,?)",
                (uid,kind,round(amount*100),category,description[:200],txn_date,datetime.utcnow().isoformat()))
            db.commit(); flash("Transaction saved.", "success")
            return redirect(url_for("transactions_page"))
    rows=db.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY txn_date DESC,id DESC",(uid,)).fetchall()
    return render_template("transactions.html", user=current_user(), transactions=[dict(r,amount=money(r["amount_paise"])) for r in rows], today=date.today().isoformat())

@app.post("/transactions/<int:txn_id>/delete")
@login_required
def delete_transaction(txn_id):
    db=get_db()
    cur=db.execute("DELETE FROM transactions WHERE id=? AND user_id=?",(txn_id,session["user_id"]))
    db.commit()
    flash("Transaction deleted." if cur.rowcount else "Transaction not found.", "success" if cur.rowcount else "error")
    return redirect(request.referrer or url_for("transactions_page"))

@app.route("/budgets", methods=["GET","POST"])
@login_required
def budgets_page():
    db=get_db(); uid=session["user_id"]
    if request.method=="POST":
        category=request.form.get("category","").strip()
        try: limit=float(request.form.get("monthly_limit",""))
        except ValueError: limit=0
        if not category or len(category)>60 or limit<=0 or limit>1000000000:
            flash("Enter a valid category and monthly limit greater than zero.", "error")
        else:
            db.execute("""INSERT INTO budgets(user_id,category,monthly_limit_paise) VALUES(?,?,?)
                ON CONFLICT(user_id,category) DO UPDATE SET monthly_limit_paise=excluded.monthly_limit_paise""",
                (uid,category,round(limit*100)))
            db.commit(); flash("Budget saved.", "success")
            return redirect(url_for("budgets_page"))
    month=date.today().strftime("%Y-%m")
    rows=db.execute("SELECT category,monthly_limit_paise FROM budgets WHERE user_id=? ORDER BY category",(uid,)).fetchall()
    spent=db.execute("""SELECT category,SUM(amount_paise) total FROM transactions WHERE user_id=? AND kind='expense'
        AND substr(txn_date,1,7)=? GROUP BY category""",(uid,month)).fetchall()
    spent_map={r["category"]:money(r["total"]) for r in spent}
    budgets=[{"category":r["category"],"limit":money(r["monthly_limit_paise"]),
        "spent":spent_map.get(r["category"],0),
        "percent":min(100,round(spent_map.get(r["category"],0)/money(r["monthly_limit_paise"])*100))}
        for r in rows]
    return render_template("budgets.html",user=current_user(),budgets=budgets,month_label=date.today().strftime("%B %Y"))

@app.post("/budgets/<path:category>/delete")
@login_required
def delete_budget(category):
    get_db().execute("DELETE FROM budgets WHERE user_id=? AND category=?",(session["user_id"],category)); get_db().commit()
    flash("Budget removed.", "success"); return redirect(url_for("budgets_page"))

@app.route("/goals", methods=["GET","POST"])
@login_required
def goals_page():
    db=get_db(); uid=session["user_id"]
    if request.method=="POST":
        title=request.form.get("title","").strip()
        try: target=float(request.form.get("target","")); saved=float(request.form.get("saved","0") or 0)
        except ValueError: target=0; saved=0
        target_date=request.form.get("target_date","").strip() or None
        valid_date=True
        if target_date:
            try: date.fromisoformat(target_date)
            except ValueError: valid_date=False
        if len(title)<2 or len(title)>100 or target<=0 or saved<0 or saved>target or not valid_date:
            flash("Check the goal name, target, saved amount and target date.", "error")
        else:
            db.execute("INSERT INTO goals(user_id,title,target_paise,saved_paise,target_date,created_at) VALUES(?,?,?,?,?,?)",
                (uid,title,round(target*100),round(saved*100),target_date,datetime.utcnow().isoformat()))
            db.commit(); flash("Savings goal created.", "success")
            return redirect(url_for("goals_page"))
    rows=db.execute("SELECT * FROM goals WHERE user_id=? ORDER BY id DESC",(uid,)).fetchall()
    goals=[dict(r,target=money(r["target_paise"]),saved=money(r["saved_paise"]),
        percent=min(100,round(money(r["saved_paise"])/money(r["target_paise"])*100))) for r in rows]
    return render_template("goals.html",user=current_user(),goals=goals)

@app.post("/goals/<int:goal_id>/contribute")
@login_required
def contribute_goal(goal_id):
    try: amount=float(request.form.get("amount",""))
    except ValueError: amount=0
    db=get_db()
    goal=db.execute("SELECT saved_paise,target_paise FROM goals WHERE id=? AND user_id=?",(goal_id,session["user_id"])).fetchone()
    if not goal or amount<=0 or amount>100000000:
        flash("Enter a valid contribution amount.", "error")
    else:
        new_saved=min(goal["target_paise"],goal["saved_paise"]+round(amount*100))
        db.execute("UPDATE goals SET saved_paise=? WHERE id=? AND user_id=?",(new_saved,goal_id,session["user_id"])); db.commit()
        flash("Goal progress updated.", "success")
    return redirect(url_for("goals_page"))

@app.post("/goals/<int:goal_id>/delete")
@login_required
def delete_goal(goal_id):
    get_db().execute("DELETE FROM goals WHERE id=? AND user_id=?",(goal_id,session["user_id"])); get_db().commit()
    flash("Goal removed.", "success"); return redirect(url_for("goals_page"))

@app.route("/education")
def education():
    return render_template("education.html",user=current_user())

@app.route("/api/exchange-rate")
def exchange_rate():
    base=request.args.get("base","USD").upper()
    quote=request.args.get("quote","INR").upper()
    if not (base.isalpha() and len(base)==3 and quote.isalpha() and len(quote)==3):
        return jsonify({"error":"Currency codes must be three letters."}),400
    if base==quote: return jsonify({"base":base,"quote":quote,"rate":1,"date":date.today().isoformat(),"source":"Identity conversion"} )
    url=f"https://api.frankfurter.dev/v2/rate/{base}/{quote}"
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"FinAware-Prototype/1.0"})
        with urllib.request.urlopen(req,timeout=8) as response:
            data=json.loads(response.read().decode("utf-8"))
        return jsonify({"base":data["base"],"quote":data["quote"],"rate":data["rate"],"date":data["date"],
            "source":"Frankfurter reference rates","note":"Daily reference rate, not a live trading quote."})
    except urllib.error.HTTPError as e:
        return jsonify({"error":f"Rate provider returned HTTP {e.code}. Try another supported currency pair."}),502
    except Exception:
        return jsonify({"error":"Exchange-rate service is unavailable. Please retry later; no estimated rate was substituted."}),503

@app.route("/calculator")
def calculator():
    return render_template("calculator.html",user=current_user())

@app.route("/export.csv")
@login_required
def export_csv():
    rows=get_db().execute("SELECT txn_date,kind,category,description,amount_paise FROM transactions WHERE user_id=? ORDER BY txn_date DESC,id DESC",(session["user_id"],)).fetchall()
    out=io.StringIO(); writer=csv.writer(out)
    writer.writerow(["Date","Type","Category","Description","Amount (INR)"])
    for r in rows: writer.writerow([r["txn_date"],r["kind"],r["category"],r["description"],f"{r['amount_paise']/100:.2f}"])
    return Response("\\ufeff"+out.getvalue(),mimetype="text/csv",headers={"Content-Disposition":"attachment; filename=finaware-transactions.csv"})

@app.route("/health")
def health():
    try:
        get_db().execute("SELECT 1").fetchone()
        return jsonify({"status":"ok","database":"connected","timestamp":datetime.utcnow().isoformat()+"Z"})
    except Exception: return jsonify({"status":"error","database":"unavailable"}),503

@app.errorhandler(404)
def not_found(error): return render_template("error.html",code=404,message="That page could not be found.",user=current_user()),404
@app.errorhandler(500)
def server_error(error): return render_template("error.html",code=500,message="Something went wrong. Please try again.",user=current_user()),500

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1",port=int(os.environ.get("PORT","5000")),debug=False)
