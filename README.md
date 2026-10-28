# FinAware — Personal Finance Literacy & Planning

A responsive, full-stack prototype for financial awareness, personal budgeting, transaction tracking, savings goals, financial calculators and daily reference currency conversion.

## Honest data policy
- The dashboard starts empty. It does not seed fake transactions or synthetic financial metrics.
- Personal records are entered by the user and stored in SQLite.
- Exchange rates are fetched at request time from the Frankfurter v2 reference-rate API. Rates update on the provider's publication schedule (daily), not tick-by-tick and are **not trading quotes**. If the provider is unavailable, the app displays an error rather than inventing a rate.
- Financial learning resources link to public institutional resources, including PMJDY financial-literacy materials and the NCFE financial-literacy dashboard.
- This prototype is educational and is not a bank, payment processor, investment advisor, or tax advisor.

## Run locally (Windows / VS Code / Command Prompt)
Requires Python 3.10+.

```bat
cd FinAware
py -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
set SECRET_KEY=replace-this-with-a-long-random-secret
python app.py
```
Open http://127.0.0.1:5000. Create your own account. No demo password or fabricated transaction data is included.

If `py` is unavailable, use `python` instead. If port 5000 is occupied, set `PORT=5001` before starting.

## Features
- Account registration and sign-in with password hashing
- Per-user transaction records (income/expense), validation and deletion
- Monthly income, expense and net cash-flow summaries
- Category budgets with monthly spending progress
- Savings goals and contribution tracking
- Compound-growth and loan-payment calculators
- Currency conversion using the latest available daily reference rate
- CSV export of the signed-in user's transactions
- Health endpoint at `/health`
- Responsive mobile/desktop layout and accessible form labels
- SQLite database with foreign-key constraints and parameterized SQL

## Deployment notes
For a public deployment:
1. Set a long, random `SECRET_KEY` environment variable.
2. Set `COOKIE_SECURE=1` when HTTPS is enabled.
3. Use persistent storage for `FINAWARE_DB_PATH` if using SQLite. Ephemeral hosting filesystems may erase SQLite data on redeploy. For multiple application instances, replace SQLite with a managed PostgreSQL database.
4. Configure backups, HTTPS, logging, rate limiting and an account recovery process before real users depend on the app.
5. Use `gunicorn app:app` on a Linux host. The included `Procfile` supports common platforms that read Procfile.
6. Run a production security review before collecting sensitive personal financial data.

## Data source references
- Frankfurter API docs: https://frankfurter.dev/
- PM Jan-Dhan Yojana financial literacy resources: https://pmjdy.gov.in/literacy
- NCFE financial literacy dashboard: https://fldashboard.ncfe.org.in/

## Prototype verification
- Visit `/health` to verify the app process and database.
- Register two separate accounts and verify their transactions are isolated.
- Add an income and expense; confirm dashboard totals and CSV export.
- Create a budget and a goal; confirm progress persists after sign-out/sign-in.
- Test invalid amounts, unsupported currency pairs and the provider outage path.
