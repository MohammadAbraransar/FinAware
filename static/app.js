(function(){
  const $ = id => document.getElementById(id);
  const money = n => new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}).format(n);
  const fxButton=$('fx-convert');
  if(fxButton){
    async function convert(){
      const amount=Number($('fx-amount').value), base=$('fx-base').value, quote=$('fx-quote').value, result=$('fx-result');
      if(!Number.isFinite(amount)||amount<0){result.textContent='Enter a valid non-negative amount.';return;}
      result.textContent='Fetching latest available reference rate…';fxButton.disabled=true;
      try{
        const response=await fetch(`/api/exchange-rate?base=${encodeURIComponent(base)}&quote=${encodeURIComponent(quote)}`);
        const data=await response.json();if(!response.ok)throw new Error(data.error||'Rate unavailable.');
        result.textContent=`${new Intl.NumberFormat('en-IN',{maximumFractionDigits:4}).format(amount)} ${base} = ${new Intl.NumberFormat('en-IN',{maximumFractionDigits:4}).format(amount*data.rate)} ${quote} · Rate date: ${data.date}. ${data.note||''}`;
      }catch(e){result.textContent=e.message||'Could not fetch a reference rate. Try again later.';}
      finally{fxButton.disabled=false;}
    }
    fxButton.addEventListener('click',convert);
    $('fx-swap').addEventListener('click',()=>{const b=$('fx-base'),q=$('fx-quote'),v=b.value;b.value=q.value;q.value=v;});
    convert();
  }
  const cf=$('compound-form');
  if(cf)cf.addEventListener('submit',e=>{
    e.preventDefault();const p=Number($('principal').value),m=Number($('monthly').value),r=Number($('annual').value)/1200,y=Number($('years').value);
    const out=$('compound-result');
    if(p<0||m<0||r<0||y<1||![p,m,r,y].every(Number.isFinite)){out.textContent='Enter valid non-negative amounts and a positive time horizon.';return;}
    const months=Math.round(y*12);let future=p*Math.pow(1+r,months);
    for(let i=0;i<months;i++)future+=m*Math.pow(1+r,months-1-i);
    const invested=p+m*months;
    out.innerHTML=`Estimated future value<strong>${money(future)}</strong><small>Total contributions: ${money(invested)} · Illustrative growth: ${money(future-invested)}</small>`;
  });
  const lf=$('loan-form');
  if(lf)lf.addEventListener('submit',e=>{
    e.preventDefault();const p=Number($('loan-principal').value),annual=Number($('loan-rate').value),years=Number($('loan-years').value),out=$('loan-result');
    if(p<=0||annual<0||annual>100||years<1||![p,annual,years].every(Number.isFinite)){out.textContent='Enter valid loan assumptions.';return;}
    const n=Math.round(years*12),r=annual/1200,emi=r===0?p/n:p*r*Math.pow(1+r,n)/(Math.pow(1+r,n)-1);
    out.innerHTML=`Estimated monthly EMI<strong>${money(emi)}</strong><small>Total repayments: ${money(emi*n)} · Estimated interest: ${money(emi*n-p)}</small>`;
  });
})();
