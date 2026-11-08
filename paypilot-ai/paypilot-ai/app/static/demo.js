'use strict';
const status=document.querySelector('#status');
async function api(path,body,extra={}){
 const headers={'Content-Type':'application/json','X-PayPilot-Client':'dashboard',...extra};
 if(path==='/api/payments'&&body)headers['Idempotency-Key']=crypto.randomUUID();
 const r=await fetch(path,{method:body===undefined?'GET':'POST',headers,...(body===undefined?{}:{body:JSON.stringify(body)})});
 const data=await r.json();
 if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Request failed. Try again.');
 return data;
}
async function busy(button,fn){button.disabled=true;try{await fn();}catch(e){status.textContent=e.message;}finally{button.disabled=false;}}
async function showReceipt(id){const r=await api('/api/payments/'+id+'/receipt');document.querySelector('#receipt').textContent=r.receipt;status.textContent='Receipt generated. No real funds moved; sandbox transactions use PayPal test accounts only.';}
async function syncPayment(id){await api('/api/payments/'+id+'/refresh',{});await refresh();const item=new URLSearchParams(location.search);for(const key of ['paypal_return','paypal_cancelled','invoice','token','PayerID'])item.delete(key);history.replaceState({},'',location.pathname+(item.size?'?'+item:''));}
async function refresh(){
 const list=await api('/api/payments');const rows=document.querySelector('#rows');rows.replaceChildren();
 for(const invoice of list){
  const row=document.createElement('article');row.className='row';
  const text=document.createElement('div');text.textContent=invoice.description;
  const details=document.createElement('span');details.textContent=invoice.currency+' '+invoice.amount+' · '+invoice.status+(invoice.mode==='sandbox'?' · PayPal Sandbox':invoice.mode==='demo'?' · Simulated':'');text.append(details);
  const actions=document.createElement('div');actions.className='actions';
  if(invoice.status==='CAPTURED'){
   const receipt=document.createElement('button');receipt.textContent='View receipt';receipt.onclick=()=>busy(receipt,()=>showReceipt(invoice.id));actions.append(receipt);
  }else if(invoice.mode==='sandbox'){
   if(invoice.approve_link&&invoice.approve_link.startsWith('https://www.sandbox.paypal.com/')){const pay=document.createElement('a');pay.href=invoice.approve_link;pay.textContent='Pay with PayPal Sandbox';pay.className='pay-link';actions.append(pay);}
   const sync=document.createElement('button');sync.textContent=invoice.status==='PENDING'?'Retry checkout':'Check payment';sync.onclick=()=>busy(sync,async()=>{if(invoice.status==='PENDING')await api('/api/payments/'+invoice.id+'/retry-checkout',{});await syncPayment(invoice.id);});actions.append(sync);
  }else{
   const simulate=document.createElement('button');simulate.textContent='Simulate payment';simulate.onclick=()=>busy(simulate,async()=>{await api('/api/payments/'+invoice.id+'/simulate',{});await showReceipt(invoice.id);await refresh();});actions.append(simulate);
  }
  row.append(text,actions);rows.append(row);
 }
}
document.querySelector('#start').onclick=e=>busy(e.target,async()=>{
 await api('/api/auth/demo',{});document.querySelector('#workspace').hidden=false;document.querySelector('#receipt').textContent='Create an invoice or choose a sample to inspect its receipt.';await refresh();
 const cfg=await api('/api/config');
 document.querySelector('#payment-note').textContent=cfg.demo_payment_mode==='paypal_sandbox'?'PayPal Sandbox checkout is enabled. Use a Sandbox buyer account; no real money moves.':'This demo uses simulated payments. PayPal Sandbox is not configured for the public demo yet.';
 status.textContent='Your isolated fictional-data workspace is ready. It cannot access administrator records.';
});
document.querySelector('#create').onsubmit=e=>{e.preventDefault();busy(e.submitter,async()=>{
 const data=new FormData(e.target);let invoice;
 try{invoice=await api('/api/payments',{description:data.get('description'),amount:data.get('amount'),currency:'USD',recipient_email:'client@example.com'});}
 catch(error){await refresh().catch(()=>{});throw error;}
 await refresh();
 status.textContent=invoice.mode==='sandbox'?'Invoice created. Continue to PayPal Sandbox, approve with a Sandbox buyer, then return and check payment.':'Invoice created. Simulate payment to create an internal demo receipt.';
});};
const query=new URLSearchParams(location.search);
if(query.has('paypal_return')||query.has('paypal_cancelled')){
 document.querySelector('#workspace').hidden=false;
 refresh().then(async()=>{
  if(query.has('paypal_return')){status.textContent='Returned from PayPal Sandbox. Checking the order with PayPal…';await syncPayment(query.get('invoice'));}
  else status.textContent='Sandbox checkout was cancelled. You can retry from the invoice row.';
 }).catch(e=>{status.textContent='Could not load the returned sandbox invoice: '+e.message+' Start a fresh demo and try again.';});
}
