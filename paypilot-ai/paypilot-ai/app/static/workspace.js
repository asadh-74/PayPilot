
/* =====================================================================
   PayPilot — private workspace frontend.
   FastAPI owns authentication, validation, persistent records and payment state.
   No credentials or private records are stored in localStorage.
===================================================================== */

const CURRENCIES = { PKR:{symbol:'₨',locale:'en-PK'}, USD:{symbol:'$',locale:'en-US'}, EUR:{symbol:'€',locale:'en-IE'}, GBP:{symbol:'£',locale:'en-GB'}, CAD:{symbol:'CA$',locale:'en-CA'}, AUD:{symbol:'A$',locale:'en-AU'}, SGD:{symbol:'S$',locale:'en-SG'}, AED:{symbol:'AED',locale:'en-AE'}, SAR:{symbol:'SAR',locale:'en-SA'} };
const fmt = (amt,cur)=> new Intl.NumberFormat(CURRENCIES[cur]?.locale||'en-US',{style:'currency',currency:cur,minimumFractionDigits:2,maximumFractionDigits:2}).format(amt);
const fmtDate = d => new Date(d+'T00:00:00').toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});
const daysFromNow = n => { const d=new Date(); d.setDate(d.getDate()+n); return d.toISOString().slice(0,10); };
const esc = s => String(s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

const DB={business:{name:'My business',instructions:''},customers:[],invoices:[],reviews:[],drafts:[],activity:[],automations:{},automationRuns:[]};
let signedIn=false;

const invoiceTotal = inv => Number(inv.amount);
const custName = id => (DB.customers.find(c=>c.id===id)||{name:'—'}).name;
function invoiceStatus(inv){ // recompute overdue from due date
  if(inv.status==='paid') return 'paid';
  return inv.due < daysFromNow(0) ? 'overdue' : 'pending';
}

/* ---------- Toast & dialog ---------- */
function toast(msg){
  const t=document.createElement('div');t.className='toast';t.textContent=msg;
  document.getElementById('toastRegion').appendChild(t);
  setTimeout(()=>{t.style.opacity='0';t.style.transition='opacity .3s';setTimeout(()=>t.remove(),320)},3200);
}
let dialogReturnFocus;
function openDialog(html){ dialogReturnFocus=document.activeElement; const b=document.getElementById('dialogBackdrop');document.getElementById('dialogBox').innerHTML=html;b.classList.add('open');b.setAttribute('aria-label','PayPilot action');setTimeout(()=>b.querySelector('button,input,a')?.focus(),0); }
function closeDialog(){ document.getElementById('dialogBackdrop').classList.remove('open');dialogReturnFocus?.focus(); }
document.getElementById('dialogBackdrop').addEventListener('click',e=>{ if(e.target.id==='dialogBackdrop') closeDialog(); });
document.addEventListener('keydown',e=>{ if(e.key==='Escape') closeDialog(); if(e.key==='Tab'&&document.getElementById('dialogBackdrop').classList.contains('open')){const els=[...document.getElementById('dialogBox').querySelectorAll('button,input,select,textarea,a[href]')];const first=els[0],last=els[els.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}} });

/* =====================================================================
   ROUTER
===================================================================== */
const TITLES={overview:['Overview','Workspace · This Week'],invoices:['Invoices','Search, filter and manage invoices'],
  create:['New invoice','Create and share a bank-transfer invoice'],review:['Payment review','Verify submitted transfer references'],
  reports:['Reports','Receivables by currency · manual invoices'],collections:['Collections','Overdue aging and follow-up priorities'],automations:['Automations','Receipt and reminder workflows'],
  drafts:['Message drafts','Receipts, invoice emails and reminders — review before sending'],activity:['Activity','Workspace timeline'],settings:['Settings','Business and bank details']};
let currentView='overview';
let invSearch='', invFilter='all';

function navigate(view){
  if(!TITLES[view]) view='overview';
  currentView=view;
  document.getElementById('publicScreen').classList.add('hidden');
  document.getElementById('appShell').classList.add('active');
  document.getElementById('authScreen').style.display='none';
  document.getElementById('pagePicker').value=view;
  if(location.hash!=='#workspace/'+view)history.replaceState(null,'','#workspace/'+view);
  document.querySelectorAll('.nav-item[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
  document.getElementById('pageTitle').textContent=TITLES[view][0];
  document.getElementById('pageCrumb').textContent=TITLES[view][1];
  closeMobileNav();
  render();
  window.scrollTo({top:0,behavior:'instant'});
}
document.getElementById('pagePicker').innerHTML=Object.entries(TITLES).map(([key,value])=>'<option value="'+key+'">'+value[0]+'</option>').join('');

function closeMobileNav(){}
/* =====================================================================
   VIEWS
===================================================================== */
const V={};

/* ---------- Overview ---------- */
V.overview=function(){
  const invs=DB.invoices, today=daysFromNow(0);
  const paid=invs.filter(i=>i.status==='paid');
  const outstanding=invs.filter(i=>i.status!=='paid');
  const overdue=invs.filter(i=>invoiceStatus(i)==='overdue');
  // collection rate per currency (never mix currencies)
  const byCur={};
  invs.forEach(i=>{ byCur[i.currency]=byCur[i.currency]||{total:0,paid:0}; byCur[i.currency].total+=invoiceTotal(i); if(i.status==='paid') byCur[i.currency].paid+=invoiceTotal(i); });
  const avgRate=Object.entries(byCur).map(([c,v])=>c+' '+Math.round(v.paid/v.total*100)+'%').join(' · ')||'—';
  // per-currency outstanding summary
  const outByCur={}; outstanding.forEach(i=>{outByCur[i.currency]=(outByCur[i.currency]||0)+invoiceTotal(i)});
  const outSummary=Object.entries(outByCur).map(([c,a])=>fmt(a,c)).join(' · ')||'No balance';
  const recent=[...invs].sort((a,b)=>b.issued.localeCompare(a.issued)).slice(0,5);

  // invoice activity: issued per week for last 6 weeks (count + value PKR-equivalent NOT used — counts only to avoid mixing currencies)
  const weeks=[]; for(let w=5;w>=0;w--){ const d=new Date(); d.setDate(d.getDate()-w*7); weeks.push(d.toISOString().slice(0,10)); }
  const weekCounts=weeks.map(ws=>invs.filter(i=>i.issued>=ws && i.issued< (()=>{const e=new Date(ws);e.setDate(e.getDate()+7);return e.toISOString().slice(0,10)})()).length);

  return `
  <div class="grid grid-4" style="margin-bottom:20px">
    ${statCard('Payments recorded', String(paid.length), 'Recorded payments · see invoice history for source', 'green', 'M9 11l3 3L22 4 M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 0 2-2h11')}
    ${statCard('Outstanding balances', outSummary, outstanding.length+' open invoice'+(outstanding.length===1?'':'s')+' · shown per currency', 'amber', 'M12 8v4l3 3 M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20')}
    ${statCard('Overdue invoices', String(overdue.length), overdue.length+' invoices need follow-up', 'red', 'M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01')}
    ${statCard('Collection rate', avgRate, 'Value collected / invoiced · per currency', 'stone', 'M22 12h-4l-3 9L9 3l-3 9H2')}
  </div>
  <div class="grid grid-2-1" style="margin-bottom:20px">
    <div class="card card-pad">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <h2 class="section-title" style="margin:0">Invoice activity</h2>
        <span class="small muted">Invoices issued per week · last 6 weeks</span>
      </div>
      <canvas id="activityChart" height="210" style="width:100%" role="img" aria-label="Invoice counts issued each week over the last six weeks. See the recent invoices table for dated records."></canvas>
    </div>
    <div class="card card-pad">
      <h2 class="section-title">Follow-up priorities</h2>
      ${overdue.length? overdue.slice(0,4).map(i=>`
        <div style="display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:1px solid var(--line-soft)">
          <div><div style="font-weight:600;font-size:13.5px">${i.number}</div><div class="small muted">${esc(custName(i.customerId))}</div></div>
          <div style="text-align:right"><div class="small" style="font-weight:600">${fmt(invoiceTotal(i),i.currency)}</div><div class="small" style="color:var(--danger)">${Math.floor((new Date(today)-new Date(i.due))/86400000)}d overdue</div></div>
        </div>`).join('')+`<button class="btn btn-soft btn-sm" data-view="collections" style="margin-top:14px">View all in Collections</button>`
      : emptyState('All clear','No overdue invoices right now.','M9 11l3 3L22 4')}
    </div>
  </div>
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;padding:20px 24px 6px">
      <h2 class="section-title" style="margin:0">Recent invoices</h2>
      <button class="btn btn-ghost btn-sm" data-view="invoices">View all</button>
    </div>
    <div class="table-wrap">${invoiceTable(recent,false)}</div>
  </div>`;
};
function statCard(label,value,sub,tone,path){
  return `<div class="card stat"><div class="stat-label"><span class="stat-icon ${tone}"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${path}"/></svg></span>${label}</div><div class="stat-value">${value}</div><div class="stat-sub">${sub}</div></div>`;
}

/* ---------- Invoices ---------- */
function invoiceTable(rows,withActions=true){
  if(!rows.length) return `<div class="empty"><div class="empty-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg></div><h3>No invoices match</h3><p>Try a different search or status filter, or create a new invoice.</p></div>`;
  return `<table><thead><tr><th>Invoice</th><th>Customer</th><th>Status</th><th class="num">Amount</th><th>Issued</th><th>Due</th>${withActions?'<th></th>':''}</tr></thead><tbody>
  ${rows.map(i=>{const st=invoiceStatus(i);return `<tr>
    <td style="font-weight:600">${i.number}</td>
    <td><div style="font-weight:500">${esc(custName(i.customerId))}</div><div class="small muted">${i.currency} · ${i.mode==='manual'?'manual transfer':i.mode==='demo'?'simulated payment':'sandbox payment'}</div></td>
    <td><span class="badge ${st}">${st==='paid'?'Paid':st==='overdue'?'Overdue':'Pending'}</span></td>
    <td class="num" style="font-weight:600">${fmt(invoiceTotal(i),i.currency)}</td>
    <td class="muted">${fmtDate(i.issued)}</td>
    <td class="${st==='overdue'?'':''}" style="${st==='overdue'?'color:var(--danger);font-weight:600':''}">${fmtDate(i.due)}</td>
    ${withActions?`<td class="row-actions">
      <button class="btn btn-ghost btn-sm" data-act="copylink" data-id="${i.id}">Share</button>
      <a class="btn btn-ghost btn-sm" href="/api/payments/${encodeURIComponent(i.id)}/pdf">PDF</a><button class="btn btn-soft btn-sm" data-act="details" data-id="${i.id}">Details</button>${i.mode==='manual'?`<button class="btn btn-ghost btn-sm" data-act="invoiceemail" data-id="${i.id}">Email invoice</button>`:''}${i.status==='paid'?`<button class="btn btn-ghost btn-sm" data-act="receipt" data-id="${i.id}">Receipt</button>`:''}
    </td>`:''}
  </tr>`}).join('')}</tbody></table>`;
}
V.invoices=function(){
  const q=invSearch.toLowerCase();
  let rows=DB.invoices.filter(i=>(i.number.toLowerCase().includes(q)||custName(i.customerId).toLowerCase().includes(q)));
  if(invFilter!=='all') rows=rows.filter(i=>invoiceStatus(i)===invFilter);
  rows.sort((a,b)=>b.issued.localeCompare(a.issued));
  const counts={all:DB.invoices.length,paid:0,pending:0,overdue:0};
  DB.invoices.forEach(i=>counts[invoiceStatus(i)]++);
  return `
  <div class="toolbar">
    <div class="search-box"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
      <input id="invSearch" type="search" placeholder="Search invoice number or customer…" value="${esc(invSearch)}" aria-label="Search invoices"></div>
    <div class="chips" role="tablist" aria-label="Status filter">
      ${['all','pending','overdue','paid'].map(f=>`<button class="chip ${invFilter===f?'active':''}" data-filter="${f}" role="tab" aria-selected="${invFilter===f}">${f[0].toUpperCase()+f.slice(1)} (${counts[f]})</button>`).join('')}
    </div>
  </div>
  <div class="card"><div class="table-wrap">${invoiceTable(rows)}</div></div>`;
};

/* ---------- Create invoice ---------- */
let draftItems=[{desc:'',qty:1,price:''}];
V.create=function(){
  return `
  <section class="card sentence-composer" aria-labelledby="sentenceTitle"><div><span class="composer-kicker">LESS TYPING. MORE DOING.</span><h2 id="sentenceTitle">Write it. Review it. Invoice it.</h2><p class="muted">Describe your invoice in one sentence. We’ll fill the details below for your review.</p></div><label for="sentencePrompt" class="small">Invoice request</label><textarea id="sentencePrompt" maxlength="1000" rows="3" placeholder="Invoice Cedar Studio at billing@customer.example for 2 logo designs at PKR 5000 each, due in 14 days."></textarea><div class="composer-actions"><button id="parseSentence" class="btn btn-primary">Generate invoice details</button><button id="sentenceExample" class="btn btn-ghost">Try an example</button><span class="small muted">Nothing is saved or sent until you confirm.</span></div><p id="sentenceStatus" class="small" role="status"></p></section>
  <div class="grid grid-2-1">
    <div class="card card-pad">
      <div class="form-grid">
        <div class="field"><label for="fCustomer">Customer name</label><input id="fCustomer" maxlength="120" placeholder="Business or customer name" required></div>
        <div class="field"><label for="fEmail">Customer email (optional)</label><input id="fEmail" type="email" maxlength="254" placeholder="billing@customer.example"></div>
        <div class="field"><label for="fAddress">Customer billing address</label><textarea id="fAddress" maxlength="800" rows="2" placeholder="Street, city, postal code, country"></textarea></div><div class="field"><label for="fTaxId">Customer tax / registration reference (optional)</label><input id="fTaxId" maxlength="100"></div><div class="field"><label for="fPO">Purchase order (optional)</label><input id="fPO" maxlength="100"></div><div class="field"><label for="fCurrency">Currency</label><select id="fCurrency">${Object.keys(CURRENCIES).map(c=>`<option>${c}</option>`).join('')}</select><p class="small muted">Totals stay in the selected currency.</p></div>
        <div class="field"><label for="fIssued">Issue date</label><input id="fIssued" type="date" value="${daysFromNow(0)}"></div>
        <div class="field"><label for="fDue">Due date</label><input id="fDue" type="date" value="${daysFromNow(14)}"></div>
      </div>
      <div class="divider"></div>
      <h3 class="section-title">Line items</h3>
      <div class="table-wrap"><table class="line-items"><thead><tr>
        <th style="padding-left:0">Description</th><th style="width:90px">Qty</th><th style="width:140px">Unit price</th><th class="num" style="width:120px">Amount</th><th style="width:44px"></th>
      </tr></thead><tbody id="itemsBody"></tbody></table></div>
      <button class="btn btn-ghost btn-sm" id="addItem" style="margin-top:10px"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>Add line item</button>
      <div class="divider"></div>
      <div class="field"><label for="fNotes">Notes to customer (optional)</label><textarea id="fNotes" rows="2" placeholder="Payment terms, thank-you note…"></textarea></div>
      <div style="display:flex;gap:10px;margin-top:8px">
        <button class="btn btn-primary" id="saveInvoice">Create invoice</button><button class="btn btn-soft" id="createEmailInvoice">Create & prepare email</button>
        <button class="btn btn-ghost" data-view="invoices">Cancel</button>
      </div>
    </div>
    <div>
      <div class="card card-pad" style="margin-bottom:16px">
        <h3 class="section-title">Summary</h3>
        <div class="totals" style="width:100%">
          <div class="totals-row"><span class="muted">Subtotal</span><strong id="sumSub" class="mono">—</strong></div>
          <div class="totals-row grand"><span>Total</span><span id="sumTotal" class="mono">—</span></div>
        </div>
        <p class="small muted" style="margin-top:14px">The total is calculated from line items and stays in the selected currency. The customer pays by manual bank transfer and shares a transfer reference — nothing is charged or verified automatically.</p>
      </div>
      <div class="card card-pad">
        <h3 class="section-title">What happens next</h3>
        <div class="timeline">
          ${['Invoice created — copy the shareable customer link','Customer transfers via their own bank','Customer submits the transfer reference','You verify against your bank statement','Confirm payment — receipt draft is prepared'].map((s,i)=>`<div class="tl-item"><span class="tl-dot"></span><div class="tl-title" style="font-weight:500">${i+1}. ${s}</div></div>`).join('')}
        </div>
      </div>
    </div>
  </div>`;
};
function renderItems(){
  const body=document.getElementById('itemsBody'); if(!body) return;
  const cur=document.getElementById('fCurrency').value;
  body.innerHTML=draftItems.map((it,idx)=>`<tr>
    <td style="padding-left:0"><input value="${esc(it.desc)}" placeholder="e.g. Logo design" data-idx="${idx}" data-f="desc" aria-label="Item description"></td>
    <td><input type="number" min="1" max="10000" step="1" value="${it.qty}" data-idx="${idx}" data-f="qty" aria-label="Quantity"></td>
    <td><input type="number" min="0.01" step="0.01" value="${it.price}" placeholder="0.00" data-idx="${idx}" data-f="price" aria-label="Unit price"></td>
    <td class="num" style="font-weight:600" id="amt-${idx}">${it.qty&&it.price?fmt(it.qty*it.price,cur):'—'}</td>
    <td>${draftItems.length>1?`<button class="icon-btn" data-del="${idx}" aria-label="Remove line item"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg></button>`:''}</td>
  </tr>`).join('');
  const sub=draftItems.reduce((s,i)=>s+(+i.qty||0)*(+i.price||0),0);
  document.getElementById('sumSub').textContent=fmt(sub,cur);
  document.getElementById('sumTotal').textContent=fmt(sub,cur);
}

/* ---------- Payment review ---------- */
V.review=function(){
  const awaiting=DB.reviews.filter(r=>r.status==='awaiting');
  const done=DB.reviews.filter(r=>r.status!=='awaiting');
  const row=r=>{ const inv=DB.invoices.find(i=>i.id===r.invoiceId);
    return `<div class="card card-pad" style="margin-bottom:14px">
      <div style="display:flex;flex-wrap:wrap;gap:16px;justify-content:space-between;align-items:flex-start">
        <div style="flex:1;min-width:240px">
          <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><strong style="font-size:16px">${inv.number}</strong><span class="badge ${invoiceStatus(inv)}">${invoiceStatus(inv)==='paid'?'Paid':invoiceStatus(inv)==='overdue'?'Overdue':'Pending'}</span>${r.status==='awaiting'?'<span class="badge pending">Awaiting review</span>':`<span class="badge draft">${r.status==='confirmed'?'Confirmed':'No match'}</span>`}</div>
          <div class="muted small" style="margin-top:4px">${esc(custName(inv.customerId))} · ${fmt(invoiceTotal(inv),inv.currency)} · due ${fmtDate(inv.due)}</div>
          <div style="margin-top:14px" class="small"><span class="muted">Submitted reference</span><br><kbd class="ref">${esc(r.reference)}</kbd></div>
          ${r.note?`<div class="small muted" style="margin-top:10px">Customer note: “${esc(r.note)}”</div>`:''}
          <div class="small muted" style="margin-top:10px">Submitted ${fmtDate(r.submitted)}</div>
        </div>
        <div style="min-width:260px;max-width:340px">
          <div class="alert info" style="margin-bottom:12px"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:2px"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg><span>PayPilot does not verify payments. Check your bank statement for a matching credit, then confirm below. The invoice is <strong>not</strong> marked paid until you do.</span></div>
          ${r.status==='awaiting'?`
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button class="btn btn-primary btn-sm" data-act="confirm" data-id="${r.id}">Confirm payment</button>
            <button class="btn btn-danger-soft btn-sm" data-act="reject" data-id="${r.id}">No match found</button>
          </div>`:`<div class="alert ${r.status==='confirmed'?'success':'warn'}" style="margin-bottom:0">${r.status==='confirmed'?'Payment confirmed against bank statement. Receipt draft prepared.':'Marked as no match — invoice stays unpaid. Follow up with the customer.'}</div>`}
        </div>
      </div>
    </div>`;};
  return `
  <div class="alert info"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:2px"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg><span><strong>Manual verification only.</strong> A submitted transfer reference never marks an invoice as paid. Confirmation always requires an administrator checking the actual bank statement.</span></div>
  <h2 class="section-title">Awaiting verification (${awaiting.length})</h2>
  ${awaiting.length?awaiting.map(row).join(''):emptyState('No references awaiting review','Submitted transfer references will appear here for verification.','M9 11l3 3L22 4')}
  ${done.length?`<h2 class="section-title" style="margin-top:28px">Previously reviewed</h2>${done.map(row).join('')}`:''}`;
};

/* ---------- Collections ---------- */
V.collections=function(){
  const today=new Date(daysFromNow(0));
  const buckets=[{label:'1–30 days overdue',min:1,max:30,tone:'amber'},{label:'31–60 days overdue',min:31,max:60,tone:'red'},{label:'60+ days overdue',min:61,max:9999,tone:'red'}];
  const overdue=DB.invoices.filter(i=>invoiceStatus(i)==='overdue');
  const soon=DB.invoices.filter(i=>invoiceStatus(i)==='pending' && (new Date(i.due)-today)/86400000<=5);
  return `
  <div class="alert warn"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:2px"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg><span>Amounts below are grouped by currency and never combined. Follow-ups are drafted messages — nothing is sent automatically.</span></div>
  <div class="grid grid-2" style="margin-bottom:20px">
    <div class="card card-pad">
      <h2 class="section-title">Overdue aging</h2>
      ${buckets.map(b=>{
        const rows=overdue.filter(i=>{const d=Math.floor((today-new Date(i.due))/86400000);return d>=b.min&&d<=b.max});
        const byCur={}; rows.forEach(i=>byCur[i.currency]=(byCur[i.currency]||0)+invoiceTotal(i));
        return `<div style="padding:12px 0;border-bottom:1px solid var(--line-soft)">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span style="font-weight:600;font-size:14px">${b.label}</span>
            <span class="badge ${b.tone}">${rows.length} invoice${rows.length===1?'':'s'}</span>
          </div>
          <div class="muted small" style="margin-top:4px">${rows.length?Object.entries(byCur).map(([c,a])=>fmt(a,c)).join(' · '):'—'}</div>
        </div>`}).join('')}
      ${!overdue.length?'<p class="muted small" style="margin-top:10px">No overdue invoices.</p>':''}
    </div>
    <div class="card card-pad">
      <h2 class="section-title">Follow-up priorities</h2>
      ${overdue.length? [...overdue].sort((a,b)=>a.due.localeCompare(b.due)).map(i=>{const d=Math.floor((today-new Date(i.due))/86400000);return `
        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;padding:11px 0;border-bottom:1px solid var(--line-soft)">
          <div><div style="font-weight:600;font-size:14px">${i.number} <span class="muted" style="font-weight:400">· ${esc(custName(i.customerId))}</span></div>
          <div class="small" style="color:var(--danger)">${d} days overdue · ${fmt(invoiceTotal(i),i.currency)}</div></div>
          <button class="btn btn-soft btn-sm" data-act="draftfollow" data-id="${i.id}">Prepare draft</button>
        </div>`}).join('')
      : emptyState('Nothing overdue','Great — no follow-ups needed right now.','M9 11l3 3L22 4')}
      ${soon.length?`<h3 class="section-title" style="margin-top:22px;font-size:15px">Due within 5 days</h3>${soon.map(i=>`<div class="small muted" style="padding:5px 0">• ${i.number} — ${esc(custName(i.customerId))} · ${fmt(invoiceTotal(i),i.currency)} · due ${fmtDate(i.due)}</div>`).join('')}`:''}
    </div>
  </div>`;
};

/* ---------- Automations ---------- */
V.automations=function(){
  const A=DB.automations;
  return `
  <div class="alert info"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:2px"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg><span>Automations only <strong>prepare drafts</strong> and log run history. Email sends only after explicit recipient and content review. Configure the email provider privately on the server.</span></div>
  <div class="grid grid-2-1">
    <div class="card card-pad">
      <h2 class="section-title">Receipts & reminders</h2><button class="btn btn-soft btn-sm" data-command="run">Run draft preparation</button>
      ${Object.entries(A).map(([k,a])=>`
      <div class="auto-row">
        <label class="switch"><input type="checkbox" data-auto="${k}" ${a.on?'checked':''} aria-label="${a.label}"><span class="track"></span><span class="thumb"></span></label>
        <div class="auto-text"><h4>${a.label}</h4><p>${a.desc}</p></div>
        <span class="badge ${a.on?'paid':'draft'}">${a.on?'On':'Off'}</span>
      </div>`).join('')}
    </div>
    <div class="card card-pad">
      <h2 class="section-title">Run history</h2>
      ${DB.automationRuns.length?DB.automationRuns.map(r=>`<div style="padding:10px 0;border-bottom:1px solid var(--line-soft)"><div class="small" style="font-weight:500">${esc(r.text)}</div><div class="tl-meta">${fmtDate(r.at)}</div></div>`).join(''):emptyState('No runs yet','Automation activity will be listed here.','M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4')}
    </div>
  </div>`;
};

/* ---------- Drafts ---------- */
V.drafts=function(){
  const grouped={invoice:[],receipt:[],reminder:[],overdue:[]};
  DB.drafts.forEach(d=>grouped[d.kind].push(d));
  const section=(kind,title,icon)=>`
    <h2 class="section-title" style="margin-top:${kind==='receipt'?0:'26px'}">${title}</h2>
    ${grouped[kind].length?grouped[kind].map(d=>{const inv=DB.invoices.find(i=>i.id===d.invoiceId);return `
    <div class="card card-pad" style="margin-bottom:12px">
      <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:flex-start">
        <div style="flex:1;min-width:220px">
          <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><strong>${esc(d.subject)}</strong><span class="badge ${d.status==='sent'?'paid':'draft'}">${d.status==='sent'?'Mail server accepted':d.delivery==='UNKNOWN'?'Acceptance uncertain':d.delivery==='SENDING'?'Sending':d.delivery==='FAILED'?'Send failed — draft kept':'Draft'}</span></div>
          <div class="muted small" style="margin-top:3px">${inv?inv.number+' · '+esc(custName(inv.customerId))+' · '+fmt(invoiceTotal(inv),inv.currency):''} · created ${fmtDate(d.created)}</div>
          <pre style="white-space:pre-wrap;font-family:inherit;font-size:13px;color:var(--ink-2);background:var(--surface-2);border:1px solid var(--line-soft);border-radius:10px;padding:12px 14px;margin-top:12px">${esc(d.body)}</pre>
        </div>
        <div style="display:flex;gap:8px;flex-direction:row;align-items:flex-start">
          ${d.status==='draft'?`<button class="btn btn-ghost btn-sm" data-act="downloaddraft" data-id="${d.id}">Download draft</button><button class="btn btn-primary btn-sm" data-act="sendmessage" data-id="${d.id}">Review & send</button>${['UNKNOWN','SENDING'].includes(d.delivery)?`<button class="btn btn-ghost btn-sm" data-act="resetdelivery" data-id="${d.id}">Resolve uncertain send</button>`:''}`:'<span class="small muted" style="padding-top:8px">Acceptance recorded</span>'}
        </div>
      </div>
    </div>`}).join(''):`<div class="card card-pad" style="margin-bottom:12px"><p class="muted small" style="padding:8px 0">No ${title.toLowerCase()} yet — they are prepared automatically when automations run, or from Collections.</p></div>`}`;
  return `
  <div class="alert info"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:2px"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg><span>Review the recipient and message, then explicitly send. Messages stay drafts until the mail server confirms acceptance. Acceptance does not guarantee inbox delivery.</span></div>
  ${section('invoice','Invoice emails')}${section('receipt','Receipts')}${section('reminder','Reminders')}${section('overdue','Overdue follow-ups')}`;
};

/* ---------- Activity ---------- */
V.activity=function(){
  const TONE={green:'',amber:'amber',red:'red',stone:'stone'};
  return `<div class="card card-pad" style="max-width:720px">
    <h2 class="section-title">Workspace timeline</h2>
    <div class="timeline">
      ${DB.activity.map(a=>`<div class="tl-item"><span class="tl-dot ${TONE[a.tone]}"></span><div class="tl-title">${esc(a.text)}</div><div class="tl-meta">${fmtDate(a.at)}</div></div>`).join('')}
    </div></div>`;
};

/* ---------- Settings ---------- */
V.settings=function(){return `<div class="grid grid-2"><div class="card card-pad"><h2 class="section-title">Business identity</h2><div class="email-readiness"><strong>Email delivery: ${DB.emailReady?'Configured':'Not configured'}</strong><p class="small muted">${DB.emailReady?'An email provider is configured. A send still requires your review; acceptance is shown after the mail server responds.':'For Render Free, configure EMAIL_PROVIDER=resend, RESEND_API_KEY and EMAIL_FROM privately on the server. Standard SMTP ports are blocked on Render Free. No credentials belong in this form.'}</p></div><div class="field"><label for="sName">Business name</label><input id="sName" maxlength="100" value="${esc(DB.business.name)}"></div><p class="muted small">Saved with new invoices. Later settings changes will not rewrite their billing details.</p>${[['address','Business address'],['registration_id','Registration / tax reference'],['contact_email','Business contact email'],['website','Business website'],['terms','Default payment terms']].map(([key,label])=>`<div class="field"><label for="b_${key}">${label}</label><textarea id="b_${key}" rows="${key==='address'||key==='terms'?3:1}" maxlength="${key==='address'?800:key==='terms'?1500:key==='registration_id'?100:key==='contact_email'?254:300}">${esc(DB.billing?.[key]||'')}</textarea></div>`).join('')}</div><div class="card card-pad"><h2 class="section-title">Bank-transfer instructions</h2><div class="field"><label for="sInstructions">Account details and instructions</label><textarea id="sInstructions" maxlength="2000" rows="9" placeholder="Bank name, account title, IBAN / account number, transfer reference instructions">${esc(DB.business.instructions)}</textarea></div><p class="muted small">Only share the receiving account details your customers need. PayPilot has no connection to your bank.</p></div></div><button id="saveSettings" class="btn btn-primary" style="margin-top:20px">Save business settings</button>`;};

function emptyState(title,msg,path){
  return `<div class="empty"><div class="empty-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="${path}"/></svg></div><h3>${title}</h3><p>${msg}</p></div>`;
}

/* =====================================================================
   RENDER + EVENT DELEGATION
===================================================================== */
function render(){
    const c=document.getElementById('viewContainer');
  c.innerHTML=`<div class="preview-strip"><span><strong>${esc(DB.business.name)}</strong> · Private workspace · ${esc(DB.database||'database')}</span><span>Manual bank transfers · Email requires explicit review</span></div>`+(V[currentView]||V.overview)();
  bindView();
}

/* Production API adapter. Same-origin cookies; no secrets or records in browser storage. */
let requestKey=null, saving=false, loadGeneration=0;
const iso=t=>new Date(t*1000).toISOString().slice(0,10);
const uuid=()=>crypto.randomUUID?crypto.randomUUID():Array.from(crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,'0')).join('');
async function api(path,method='GET',body,extra={}){
 const response=await fetch('/api'+path,{method,credentials:'same-origin',headers:{'Content-Type':'application/json','X-PayPilot-Client':'dashboard',...extra},body:body===undefined?undefined:JSON.stringify(body)});
 const result=await response.json().catch(()=>({}));
 if(!response.ok){if(response.status===401){signedIn=false;showAuth();}throw Error(typeof result.detail==='string'?result.detail:response.status===422?'Check the entered values. Quantities must be whole numbers and amounts must have no more than two decimals.':'Request failed. Please retry.');}return result;
}
async function action(button,fn){if(button?.disabled)return;if(button)button.disabled=true;try{await fn();}catch(e){toast(e.message);const box=document.getElementById('actionError');if(box)box.textContent=e.message;}finally{if(button)button.disabled=false;}}
function showAuth(){document.getElementById('authScreen').style.display='flex';document.getElementById('appShell').classList.remove('active');document.getElementById('publicScreen').classList.add('hidden');document.getElementById('authScreen').querySelector('input')?.focus();}
function applySnapshot(s){
 DB.database=s.database==='mysql'?'MySQL connected':'Local SQLite';document.getElementById('businessLabel').textContent=s.business.business_name;
 DB.emailReady=Boolean(s.email_ready);DB.business={name:s.business.business_name,instructions:s.business.payment_instructions};DB.billing=s.billing_profile||{};
 const meta=new Map(s.metadata.map(m=>[m.payment_id,m]));
 DB.customers=s.invoices.map(p=>({id:p.id,name:meta.get(p.id)?.customer_name||p.recipient_email||'Customer',contact:p.recipient_email||''}));
 DB.invoices=s.invoices.map(p=>{const m=meta.get(p.id),items=s.items.filter(i=>i.payment_id===p.id);return {id:p.id,number:(s.invoice_documents||[]).find(d=>d.payment_id===p.id)?.invoice_number||'INV-'+p.id.slice(0,8).toUpperCase(),customerId:p.id,currency:p.currency,status:p.status==='CAPTURED'?'paid':'pending',issued:m?.issued_date||iso(p.created_at),due:iso(p.due_at),notes:m?.notes||'',mode:p.mode,description:p.description,amount:p.amount,items:items.length?items.map(i=>({desc:i.description,qty:i.quantity,price:i.unit_amount})):[{desc:p.description,qty:1,price:p.amount}]};});
 DB.reviews=s.reports.map(r=>({id:r.payment_id,invoiceId:r.payment_id,reference:r.reference,submitted:iso(r.created_at),note:'',status:r.status==='SUBMITTED'?'awaiting':r.status==='APPROVED'?'confirmed':'rejected'}));
 DB.drafts=s.drafts.map(d=>({id:d.id,kind:d.kind,invoiceId:d.payment_id,subject:d.subject,body:d.body,recipient:d.recipient,status:d.status==='SENT'?'sent':'draft',delivery:(s.deliveries||[]).find(x=>x.outbox_id===d.id)?.status,created:iso(d.created_at)}));
 DB.activity=s.activity.map(a=>({at:iso(a.created_at),tone:a.kind.includes('rejected')?'red':a.kind.includes('verified')?'green':'stone',text:a.detail+' · '+a.kind}));
 DB.automations={receiptOnConfirm:{on:s.rules.receipts,label:'Receipt drafts',desc:'Prepare a receipt draft after administrator confirmation.'},overdueNotice:{on:s.rules.reminders,label:'Overdue reminders',desc:'Prepare a daily reminder draft for overdue invoices. References awaiting review pause reminders.'}};
 DB.automationRuns=s.latest_run?[{at:iso(s.latest_run.completed_at),text:s.latest_run.queued+' drafts prepared in latest completed run. No messages sent.'}]:[];
 DB.automationRuns.push(...s.activity.filter(a=>a.kind.startsWith('automation.')).slice(0,12).map(a=>({at:iso(a.created_at),text:a.detail})));
 document.getElementById('reviewCount').textContent=DB.reviews.filter(r=>r.status==='awaiting').length;document.querySelectorAll('[data-review-count]').forEach(el=>el.textContent=DB.reviews.filter(r=>r.status==='awaiting').length);
}
async function refreshWorkspace(){const generation=++loadGeneration;const [s,report]=await Promise.all([api('/workspace/snapshot'),api('/reports/receivables')]);if(generation===loadGeneration){applySnapshot(s);DB.report=report;}}
async function reloadView(){await refreshWorkspace();if(signedIn)render();}
function visit(view){navigate(view);if(view!=='create')refreshWorkspace().then(()=>{if(signedIn&&currentView===view)render();}).catch(e=>toast(e.message));}
function loading(){document.getElementById('viewContainer').innerHTML='<div class="loading-surface" role="status">Loading your workspace…</div>';}
function pageError(error){document.getElementById('viewContainer').innerHTML='<div class="global-status" role="alert"><h2>Could not load the workspace</h2><p>'+esc(error.message)+'</p><button class="btn btn-primary" data-command="retry">Retry</button></div>';}
// Replace preview-only inline actions with delegated, CSP-compatible controls.
function prepareRenderedControls(){
 document.querySelectorAll('[onclick]').forEach(el=>{const code=el.getAttribute('onclick');el.removeAttribute('onclick');if(code.includes('runAutomations'))el.dataset.command='run';else if(code.includes('closeDialog'))el.dataset.command='close';});
 document.querySelectorAll('.chips [role="tab"]').forEach(el=>{el.removeAttribute('role');el.removeAttribute('aria-selected');el.setAttribute('aria-pressed',el.classList.contains('active'));});
 document.querySelector('.chips')?.removeAttribute('role');
}
const renderView=render;
render=function(){renderView();prepareRenderedControls();};
function bindView(){
 const search=document.getElementById('invSearch');if(search)search.oninput=e=>{invSearch=e.target.value;render();const input=document.getElementById('invSearch');input.focus();};
 document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{invFilter=b.dataset.filter;render();});
 if(currentView==='overview')drawChart();
 if(currentView==='create'){
  renderItems();requestKey=requestKey||uuid();
  document.getElementById('parseSentence').onclick=e=>action(e.currentTarget,generateSentence);
  document.getElementById('sentenceExample').onclick=()=>{document.getElementById('sentencePrompt').value='Invoice Cedar Studio at billing@customer.example for 2 logo designs at PKR 5000 each; 3 banners at PKR 1000 each, due in 14 days.';document.getElementById('sentencePrompt').focus();};
  document.getElementById('fCurrency').onchange=renderItems;
  document.getElementById('addItem').onclick=()=>{if(draftItems.length>=30){toast('Maximum 30 line items');return;}draftItems.push({desc:'',qty:1,price:''});renderItems();requestKey=uuid();};
  document.getElementById('itemsBody').oninput=e=>{const t=e.target;if(t.dataset.idx===undefined)return;draftItems[+t.dataset.idx][t.dataset.f]=t.value;requestKey=uuid();updateTotals();};
  document.getElementById('itemsBody').onclick=e=>{const b=e.target.closest('[data-del]');if(b){draftItems.splice(+b.dataset.del,1);renderItems();requestKey=uuid();}};
  ['fCustomer','fEmail','fCurrency','fIssued','fDue','fNotes','fAddress','fTaxId','fPO'].forEach(id=>document.getElementById(id).addEventListener('input',()=>{requestKey=uuid();}));
  document.getElementById('saveInvoice').onclick=e=>action(e.currentTarget,saveInvoice);document.getElementById('createEmailInvoice').onclick=e=>action(e.currentTarget,()=>saveInvoice(true));
 }
 if(currentView==='settings')document.getElementById('saveSettings').onclick=e=>action(e.currentTarget,async()=>{const name=document.getElementById('sName').value.trim();if(!name)throw Error('Enter a business name');await api('/workspace','PUT',{business_name:name,payment_instructions:document.getElementById('sInstructions').value.trim()});await api('/business-profile','PUT',Object.fromEntries(['address','registration_id','contact_email','website','terms'].map(k=>[k,document.getElementById('b_'+k).value.trim()])));await reloadView();toast('Business settings saved for future invoices');});
 document.querySelectorAll('[data-auto]').forEach(input=>input.onchange=()=>action(null,async()=>{try{await api('/automations','PUT',{receipts:input.dataset.auto==='receiptOnConfirm'?input.checked:DB.automations.receiptOnConfirm.on,reminders:input.dataset.auto==='overdueNotice'?input.checked:DB.automations.overdueNotice.on});await reloadView();toast('Automation setting saved');}catch(e){input.checked=!input.checked;throw e;}}));
}
function itemCents(item){if(!/^\d+(\.\d{1,2})?$/.test(String(item.price)))throw Error('Use prices with at most two decimal places');const [whole,fraction='']=String(item.price).split('.');return (Number(whole)*100+Number(fraction.padEnd(2,'0')))*Number(item.qty);}
function updateTotals(){let cents=0;for(let idx=0;idx<draftItems.length;idx++){const item=draftItems[idx];let n=0;try{n=itemCents(item);}catch(e){}cents+=n;document.getElementById('amt-'+idx).textContent=fmt(n/100,document.getElementById('fCurrency').value);}for(const id of ['sumSub','sumTotal'])document.getElementById(id).textContent=fmt(cents/100,document.getElementById('fCurrency').value);}
async function saveInvoice(prepareEmail=false){
 if(saving)return;const customer=document.getElementById('fCustomer').value.trim(),email=document.getElementById('fEmail').value.trim();
 if(!customer)throw Error('Enter a customer name');if(prepareEmail&&!email)throw Error('Enter a customer email to prepare the invoice email');if(email&&!document.getElementById('fEmail').checkValidity())throw Error('Enter a valid customer email');
 if(draftItems.some(i=>!i.desc.trim()||!Number.isInteger(+i.qty)||+i.qty<1||+i.qty>10000||+i.price<=0))throw Error('Complete every item; use whole quantities and positive unit prices');
 const cents=draftItems.reduce((sum,i)=>sum+itemCents(i),0);if(!Number.isSafeInteger(cents)||cents<=0)throw Error('Check invoice total');
 const issued=document.getElementById('fIssued').value,due=document.getElementById('fDue').value;if(!issued||!due||due<issued)throw Error('Choose a due date on or after the issue date');
 saving=true;try{
 const inv=await api('/payments','POST',{amount:(cents/100).toFixed(2),currency:document.getElementById('fCurrency').value,description:draftItems[0].desc.trim(),recipient_email:email||null,customer_name:customer,customer_address:document.getElementById('fAddress').value.trim(),customer_tax_id:document.getElementById('fTaxId').value.trim(),purchase_order:document.getElementById('fPO').value.trim(),notes:document.getElementById('fNotes').value.trim(),issue_date:issued,due_date:due,items:draftItems.map(i=>({description:i.desc.trim(),quantity:+i.qty,unit_amount:Number(i.price).toFixed(2)}))},{'Idempotency-Key':requestKey});
 requestKey=null;draftItems=[{desc:'',qty:1,price:''}];await refreshWorkspace();navigate('invoices');toast('Invoice saved to the database');if(prepareEmail){await api('/payments/'+encodeURIComponent(inv.id)+'/email-draft','POST',{});await refreshWorkspace();navigate('drafts');reviewEmail('invoice-email-'+inv.id);}else await shareInvoice(inv.id);
 }finally{saving=false;}
}
async function shareInvoice(id){const result=await api('/payments/'+encodeURIComponent(id)+'/share','POST',{});const url=new URL(result.path,location.origin).href;openDialog('<h2>Customer invoice link</h2><div class="dialog-body"><p>This private link expires in 24 hours. Creating a new link revokes the previous one. Share it directly with your customer.</p><input id="shareLink" aria-label="Customer invoice link" readonly style="width:100%;padding:12px" value="'+esc(url)+'"><p><a class="btn btn-soft" target="_blank" rel="noopener" href="'+esc(result.path)+'">Open customer invoice ↗</a></p></div><div class="dialog-actions"><button class="btn btn-ghost" data-command="close">Close</button><button class="btn btn-ghost" data-command="revoke" data-id="'+esc(id)+'">Revoke link</button><button class="btn btn-primary" data-command="copy">Share</button></div>');}
async function reviewPayment(id,confirm){
 const report=DB.reviews.find(r=>r.id===id),inv=DB.invoices.find(i=>i.id===report.invoiceId);if(!report||!inv||report.status!=='awaiting')throw Error('Reference is no longer awaiting review');
 const amount=fmt(invoiceTotal(inv),inv.currency);
 openDialog('<h2>'+ (confirm?'Confirm recorded payment':'No matching transfer')+'</h2><div class="dialog-body"><p>'+esc(inv.number)+' · '+esc(custName(inv.customerId))+' · <strong>'+esc(amount)+'</strong></p><p>Submitted reference: <strong>'+esc(report.reference)+'</strong></p><p>'+ (confirm?'Check the bank statement independently. PayPilot cannot verify bank transactions.':'The invoice will stay unpaid. The customer may submit a corrected reference.')+'</p>'+(confirm?'<label style="display:flex;gap:12px;margin-top:20px"><input type="checkbox" id="statementChecked">I checked the statement and matched the amount, currency and reference.</label>':'')+'<p id="actionError" role="alert" style="color:var(--danger)"></p></div><div class="dialog-actions"><button class="btn btn-ghost" data-command="close">Cancel</button><button class="btn btn-primary" id="reviewSubmit">'+(confirm?'Confirm payment':'Mark no match')+'</button></div>');
 document.getElementById('reviewSubmit').onclick=e=>action(e.currentTarget,async()=>{if(confirm&&!document.getElementById('statementChecked').checked)throw Error('Confirm that you checked the bank statement');await api('/payments/'+encodeURIComponent(id)+(confirm?'/confirm-manual':'/reject-reference'),'POST',confirm?{reference:report.reference,verified:true}:{});closeDialog();await reloadView();toast(confirm?'Payment recorded. Receipt available; no message sent.':'Reference rejected. Invoice remains unpaid.');});
}
async function runAutomations(button){await action(button,async()=>{const r=await api('/automations/run','POST',{});await reloadView();toast(r.queued+' new drafts prepared. No external messages sent.');});}
function downloadDraft(id){const draft=DB.drafts.find(d=>d.id===id);if(!draft)return;const blob=new Blob(['DRAFT — NOT SENT\nSubject: '+draft.subject+'\n\n'+draft.body],{type:'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='PayPilot-draft.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
document.addEventListener('click',e=>{
 const nav=e.target.closest('[data-view]');if(nav&&signedIn){e.preventDefault();visit(nav.dataset.view);return;}
 const command=e.target.closest('[data-command]');if(command){const c=command.dataset.command;if(c==='refresh')action(command,reloadView);if(c==='close')closeDialog();if(c==='run')runAutomations(command);if(c==='retry')action(command,async()=>{await reloadView();});if(c==='logout')action(command,async()=>{await api('/auth/logout','POST',{});signedIn=false;DB.invoices=[];DB.drafts=[];DB.reviews=[];showAuth();});if(c==='copy')action(command,async()=>{const input=document.getElementById('shareLink');try{await navigator.clipboard.writeText(input.value);toast('Customer link copied');}catch(e){input.focus();input.select();toast('Copy the selected link using Ctrl+C');}});if(c==='revoke')action(command,async()=>{await api('/payments/'+encodeURIComponent(command.dataset.id)+'/share','DELETE');closeDialog();toast('Customer link revoked');});return;}
 const a=e.target.closest('[data-act]');if(!a)return;action(a,async()=>{const id=a.dataset.id,act=a.dataset.act;if(act==='copylink'||act==='viewinv')await shareInvoice(id);if(act==='details'){const result=await api('/payments/'+encodeURIComponent(id)+'/details');const inv=DB.invoices.find(i=>i.id===id);openDialog('<h2>'+esc(inv.number)+'</h2><div class="dialog-body"><p>'+esc(custName(inv.customerId))+' · '+esc(fmt(invoiceTotal(inv),inv.currency))+'</p><p>'+esc(inv.notes)+'</p><table><thead><tr><th>Item</th><th>Qty</th><th>Unit price</th></tr></thead><tbody>'+inv.items.map(i=>'<tr><td>'+esc(i.desc)+'</td><td>'+i.qty+'</td><td>'+esc(fmt(i.price,inv.currency))+'</td></tr>').join('')+'</tbody></table><h3>Activity</h3>'+result.events.map(x=>'<p>'+esc(new Date(x.created_at*1000).toLocaleString())+' · '+esc(x.detail)+'</p>').join('')+'</div><div class="dialog-actions"><button class="btn btn-ghost" data-command="close">Close</button></div>');}if(act==='receipt'){const r=await api('/payments/'+encodeURIComponent(id)+'/receipt');openDialog('<h2>Payment receipt</h2><div class="dialog-body"><pre style="white-space:pre-wrap;font:inherit">'+esc(r.receipt)+'</pre><p>No email sent. Open the customer invoice link for a printable receipt.</p></div><div class="dialog-actions"><button class="btn btn-ghost" data-command="close">Close</button><button class="btn btn-primary" data-act="copylink" data-id="'+esc(id)+'">Printable receipt link</button></div>');}if(act==='confirm'||act==='reject')await reviewPayment(id,act==='confirm');if(act==='draftfollow'){const r=await api('/payments/'+encodeURIComponent(id)+'/reminder-preview','POST',{});openDialog('<h2>'+esc(r.subject)+'</h2><div class="dialog-body"><pre style="white-space:pre-wrap;font:inherit">'+esc(r.body)+'</pre><p>Preview only. Run automations to save eligible reminders. No message sent.</p></div><button class="btn btn-primary" data-command="close">Close</button>');}if(act==='invoiceemail'){await api('/payments/'+encodeURIComponent(id)+'/email-draft','POST',{});await refreshWorkspace();navigate('drafts');toast('Invoice email prepared. Review before sending. Previous customer link may have been replaced.');}if(act==='sendmessage')reviewEmail(id);if(act==='resetdelivery')reviewRetry(id);if(act==='downloaddraft')downloadDraft(id);});
});
const picker=document.getElementById('pagePicker');picker.innerHTML=Object.entries(TITLES).map(([k,v])=>'<option value="'+k+'">'+v[0]+'</option>').join('');picker.onchange=e=>{if(signedIn)visit(e.target.value);};
const mobileInner=document.getElementById('mobileNavInner');mobileInner.innerHTML=Array.from(document.querySelectorAll('#sidebar .nav-item')).map(b=>b.outerHTML.replace('id="reviewCount"','data-review-count="true"')).join('');
document.getElementById('menuBtn').onclick=()=>{picker.focus();};
document.getElementById('loginForm').onsubmit=e=>{e.preventDefault();const button=document.getElementById('loginBtn'),error=document.getElementById('authError');action(button,async()=>{button.textContent='Signing in…';error.classList.remove('show');try{await api('/auth/login','POST',{password:document.getElementById('loginPass').value});document.getElementById('loginPass').value='';signedIn=true;navigate('overview');loading();await reloadView();}catch(e){if(!signedIn){error.textContent=e.message;error.classList.add('show');}else pageError(e);throw e;}finally{button.textContent='Sign in';}});};
window.addEventListener('hashchange',()=>{if(!signedIn)return;const m=location.hash.match(/^#workspace\/(\w+)$/);if(m)visit(m[1]);});
window.addEventListener('resize',()=>{if(signedIn&&currentView==='overview')drawChart();});
(async()=>{try{const me=await api('/auth/me');if(me.role!=='admin'){await api('/auth/logout','POST',{});showAuth();return;}signedIn=true;const view=location.hash.match(/^#workspace\/(\w+)$/)?.[1]||'overview';navigate(view);loading();await reloadView();}catch(e){if(signedIn)pageError(e);else showAuth();}})();

function drawChart(){
  const cv=document.getElementById('activityChart'); if(!cv)return;
  const ctx=cv.getContext('2d');
  const dpr=window.devicePixelRatio||1;
  const W=cv.clientWidth, H=210; cv.width=W*dpr; cv.height=H*dpr; ctx.scale(dpr,dpr);
  const invs=DB.invoices; const weeks=[];
  for(let w=5;w>=0;w--){ const d=new Date(); d.setDate(d.getDate()-w*7); weeks.push(d); }
  const counts=weeks.map(ws=>{ const we=new Date(ws); we.setDate(we.getDate()+7);
    return invs.filter(i=>i.issued>=ws.toISOString().slice(0,10) && i.issued<we.toISOString().slice(0,10)).length; });
  const max=Math.max(...counts,2);
  const padL=8,padB=26,padT=14, cw=(W-padL*2)/weeks.length;
  // gridlines
  ctx.strokeStyle='#EFEAE0'; ctx.lineWidth=1; ctx.font='11px Inter,sans-serif'; ctx.fillStyle='#A8A29E';
  for(let g=0;g<=max;g++){ if(max>4 && g%Math.ceil(max/4)!==0) continue;
    const y=H-padB-(H-padB-padT)*(g/max);
    ctx.beginPath(); ctx.moveTo(padL,y); ctx.lineTo(W-padL,y); ctx.stroke();
    ctx.fillText(String(g),padL-2,y-5);
  }
  counts.forEach((c,i)=>{
    const x=padL+i*cw+cw*0.22, bw=cw*0.56;
    const h=(H-padB-padT)*(c/max), y=H-padB-h;
    ctx.fillStyle=c===max&&c>0?'#0E6B57':'#9CC6B9';
    roundRect(ctx,x,y,Math.max(bw,14),Math.max(h,2),5); ctx.fill();
    ctx.fillStyle='#57534E'; ctx.font='600 12px Inter,sans-serif'; ctx.textAlign='center';
    if(c>0) ctx.fillText(String(c),x+bw/2,y-6);
    ctx.fillStyle='#A8A29E'; ctx.font='11px Inter,sans-serif';
    ctx.fillText(weeks[i].toLocaleDateString('en-GB',{day:'numeric',month:'short'}),x+bw/2,H-8);
    ctx.textAlign='left';
  });
  function roundRect(c,x,y,w,h,r){ c.beginPath(); c.moveTo(x+r,y); c.arcTo(x+w,y,x+w,y+h,r); c.arcTo(x+w,y+h,x,y+h,r); c.arcTo(x,y+h,x,y,r); c.arcTo(x,y,x+w,y,r); c.closePath(); }
}

api('/config').then(config=>{if(!config.admin_configured){const error=document.getElementById('authError');error.textContent='Administrator setup needed: ADMIN_PASSWORD must contain at least 16 characters in Render. Save the variable and deploy before signing in.';error.classList.add('show');}}).catch(()=>{});


async function generateSentence(){
 const status=document.getElementById('sentenceStatus'),prompt=document.getElementById('sentencePrompt').value.trim();
 if(!prompt)throw Error('Describe a customer, service, price and currency first');
 status.textContent='Reading your request…';
 try{const data=await api('/invoice-drafts/parse','POST',{prompt});
 document.getElementById('fCustomer').value=data.customer_name||'';document.getElementById('fEmail').value=data.recipient_email||'';
 document.getElementById('fCurrency').value=data.currency;document.getElementById('fIssued').value=data.issue_date;document.getElementById('fDue').value=data.due_date;
 draftItems=data.items.map(i=>({desc:i.description,qty:i.quantity,price:i.unit_amount}));renderItems();updateTotals();requestKey=uuid();
 status.textContent=data.provider+' · '+data.warnings.join(' ');document.getElementById('fCustomer').focus();
 toast('Invoice details generated. Review, then create.');
 }catch(e){status.textContent=e.message;throw e;}
}
function reviewEmail(id){
 const draft=DB.drafts.find(d=>d.id===id);if(!draft)return;
 openDialog('<h2>Review email before sending</h2><div class="dialog-body"><p><strong>To:</strong> '+esc(draft.recipient)+'</p><p><strong>Subject:</strong> '+esc(draft.subject)+'</p><pre class="email-body">'+esc(draft.body)+'</pre><p class="small muted">'+(DB.emailReady?'Mail-server acceptance will be recorded. Inbox delivery is not independently verified.':'Email is not configured yet. Configure the server email provider before sending.')+'</p><label class="email-confirm"><input type="checkbox" id="emailReviewed">I checked the recipient and message and want to send this email.</label><p id="actionError" role="alert" style="color:var(--danger)"></p></div><div class="dialog-actions"><button class="btn btn-ghost" data-command="close">Cancel</button><button class="btn btn-primary" id="emailSend">Send email</button></div>');
 document.getElementById('emailSend').onclick=e=>action(e.currentTarget,async()=>{if(!document.getElementById('emailReviewed').checked)throw Error('Confirm the recipient and message before sending');const result=await api('/outbox/'+encodeURIComponent(id)+'/send','POST',{reviewed:true});closeDialog();await reloadView();toast(result.message);});
}

function reviewRetry(id){openDialog('<h2>Check the email provider first</h2><div class="dialog-body"><p>A timeout can happen after a provider accepts an email. Check the provider delivery records to avoid sending a duplicate.</p><label class="email-confirm"><input type="checkbox" id="retryChecked">I checked the provider records and confirmed this email was not accepted.</label><p id="actionError" role="alert"></p></div><div class="dialog-actions"><button class="btn btn-ghost" data-command="close">Cancel</button><button class="btn btn-primary" id="retryAllow">Allow a new send</button></div>');document.getElementById('retryAllow').onclick=e=>action(e.currentTarget,async()=>{if(!document.getElementById('retryChecked').checked)throw Error('Confirm your provider-record check first');await api('/outbox/'+encodeURIComponent(id)+'/retry-check','POST',{confirmed_not_sent:true});closeDialog();await reloadView();toast('Retry enabled. Review the draft again before sending.');});}


V.reports=function(){
 const report=DB.report||{currencies:{},invoices:[]};
 const buckets=[['not_due','Not yet due'],['overdue_1_30','1–30 days overdue'],['overdue_31_60','31–60 days overdue'],['overdue_61_plus','61+ days overdue']];
 return `<section class="card card-pad"><div class="report-head"><div><span class="composer-kicker">RECEIVABLES REPORT</span><h2 class="section-title">Know what is due, in each currency.</h2><p class="muted">${esc(report.basis||'Manual invoices only. No currency conversion.')}</p></div><a class="btn btn-primary" href="/api/reports/receivables.csv">Download CSV</a></div><p class="small muted">Updated ${esc(report.as_of?new Date(report.as_of).toLocaleString():'—')}</p></section>
 <div class="report-currencies">${Object.entries(report.currencies).map(([currency,g])=>`<section class="card card-pad"><span class="badge draft">${esc(currency)}</span><h2 style="margin:16px 0 4px">${esc(fmt(g.outstanding,currency))}</h2><p class="muted">Outstanding balance</p><div class="divider"></div><div class="totals-row"><span>Total invoiced</span><strong>${esc(fmt(g.invoiced,currency))}</strong></div><div class="totals-row"><span>Payment recorded</span><strong>${esc(fmt(g.paid,currency))}</strong></div>${buckets.map(([key,label])=>`<div class="totals-row"><span>${label}</span><strong>${esc(fmt(g[key],currency))}</strong></div>`).join('')}</section>`).join('')||'<section class="card card-pad"><h2>No manual invoices yet</h2><p>Create an invoice to begin tracking receivables. Demo and sandbox invoices are excluded.</p></section>'}</div>
 <section class="card card-pad" style="margin-top:20px"><h2 class="section-title">Invoice register</h2><div class="table-wrap"><table><thead><tr><th>Invoice</th><th>Customer email</th><th>Due date</th><th>Balance</th><th>Aging</th></tr></thead><tbody>${report.invoices.map(i=>`<tr><td>${esc(i.number)}</td><td>${esc(i.customer_email||'—')}</td><td>${esc(i.due_date)}</td><td>${esc(fmt(i.balance,i.currency))}</td><td>${esc(i.bucket.replaceAll('_',' '))}</td></tr>`).join('')}</tbody></table></div></section>`;
};
