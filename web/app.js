const S = {
  token: null,
  revToken: null,
};

function $(id){ return document.getElementById(id); }
function setHidden(el, yes){ el.classList[yes?'add':'remove']('hidden'); }
function tabSwitch(name){
  for(const t of ['orders','expenses','kpi']){
    setHidden($('tab-'+t), t!==name);
  }
  for(const btn of document.querySelectorAll('nav button')){
    btn.classList.toggle('active', btn.dataset.tab===name);
  }
}

async function api(path, opts={}){
  opts.headers = opts.headers || {};
  const useRev = path.startsWith('/kpi/');
  const token = useRev ? S.revToken : S.token;
  if (token) opts.headers['Authorization'] = 'Bearer ' + token;
  opts.headers['Content-Type'] = 'application/json';
  const r = await fetch(path, opts);
  if(!r.ok){
    const t = await r.text();
    throw new Error(`${r.status} ${t}`);
  }
  const ct = r.headers.get('content-type')||'';
  return ct.includes('application/json') ? r.json() : r.text();
}

function initTabs(){
  document.querySelectorAll('nav button').forEach(b=>{
    b.onclick = ()=> tabSwitch(b.dataset.tab);
  });
}

function initLogin(){
  $('btn-setup').onclick = async ()=>{
    try{
      const code = $('code').value.trim();
      const password = $('password').value;
      const r = await api('/auth/setup', { method:'POST', body: JSON.stringify({code,password})});
      $('login-msg').textContent = '初始化完成，請按登入';
    }catch(e){ $('login-msg').textContent = e.message; }
  };
  $('btn-login').onclick = async ()=>{
    try{
      const code = $('code').value.trim();
      const password = $('password').value;
      const r = await api('/auth/login', { method:'POST', body: JSON.stringify({code,password})});
      S.token = r.token;
      setHidden($('login'), true);
      setHidden($('tabs'), false);
      tabSwitch('orders');
    }catch(e){ $('login-msg').textContent = e.message; }
  };
}

function initOrders(){
  const today = new Date().toISOString().slice(0,10);
  $('odate').value = today;
  $('o_add_date').value = today;

  $('btn-olist').onclick = async ()=>{
    try{
      const params = new URLSearchParams({ d: $('odate').value });
      const q = $('oq').value.trim(); if(q) params.append('q', q);
      const data = await api('/orders?'+params.toString());
      const tb = $('otbl').querySelector('tbody');
      tb.innerHTML = '';
      for(const o of data){
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${o.shift}</td><td>${o.order_no}</td><td>${o.amount.toLocaleString()}</td><td>${o.date}</td>`;
        tb.appendChild(tr);
      }
    }catch(e){ alert(e.message); }
  };

  $('btn-oadd').onclick = async ()=>{
    try{
      const payload = {
        date: $('o_add_date').value,
        shift: $('o_add_shift').value,
        order_no: $('o_add_no').value.trim(),
        amount: Number($('o_add_amt').value||0),
      };
      await api('/orders', {method:'POST', body: JSON.stringify(payload)});
      $('btn-olist').click();
    }catch(e){ alert(e.message); }
  };
}

function initExpenses(){
  const today = new Date().toISOString().slice(0,10);
  $('x_from').value = today;
  $('x_to').value = today;
  $('x_add_date').value = today;

  $('btn-xlist').onclick = async ()=>{
    try{
      const params = new URLSearchParams({ d1:$('x_from').value, d2:$('x_to').value });
      const q = $('xq').value.trim(); if(q) params.append('q', q);
      const data = await api('/expenses?'+params.toString());
      const tb = $('xtbl').querySelector('tbody');
      tb.innerHTML = '';
      for(const x of data){
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${x.category}</td><td>${x.amount.toLocaleString()}</td><td>${x.date}</td><td>${x.note||''}</td>`;
        tb.appendChild(tr);
      }
    }catch(e){ alert(e.message); }
  };

  $('btn-xadd').onclick = async ()=>{
    try{
      const payload = {
        date: $('x_add_date').value,
        category: $('x_add_cat').value.trim(),
        amount: Number($('x_add_amt').value||0),
        note: $('x_add_note').value.trim() || null
      };
      await api('/expenses', {method:'POST', body: JSON.stringify(payload)});
      $('btn-xlist').click();
    }catch(e){ alert(e.message); }
  };
}

function initKPI(){
  $('btn-unlock').onclick = async ()=>{
    try{
      const code = $('rev_code').value.trim();
      const password = $('rev_pw').value;
      const r = await api('/auth/unlock', {method:'POST', body: JSON.stringify({code,password})});
      S.revToken = r.rev_token;
      $('unlock-msg').textContent = '已解鎖';
      setHidden($('kpi-area'), false);
    }catch(e){ $('unlock-msg').textContent = e.message; }
  };

  $('btn-kday').onclick = async ()=>{
    try{
      const d = $('k_day').value;
      const r = await api('/kpi/day?d='+encodeURIComponent(d));
      $('kday-out').textContent = JSON.stringify(r, null, 2);
    }catch(e){ alert(e.message); }
  };
  $('btn-kmon').onclick = async ()=>{
    try{
      const y = $('k_my').value, m = $('k_mm').value;
      const r = await api(`/kpi/month?y=${y}&m=${m}`);
      $('kmon-out').textContent = JSON.stringify(r, null, 2);
    }catch(e){ alert(e.message); }
  };
  $('btn-kyr').onclick = async ()=>{
    try{
      const y = $('k_yy').value;
      const r = await api(`/kpi/year?y=${y}`);
      $('kyr-out').textContent = JSON.stringify(r, null, 2);
    }catch(e){ alert(e.message); }
  };
}

window.addEventListener('DOMContentLoaded', ()=>{
  initTabs();
  initLogin();
  initOrders();
  initExpenses();
  initKPI();
});
