/* app/static/js/app.js
 * AURUM UI Runtime — 2025-09-10 focus/selection lock
 * 重點：
 * 1) 只有 /orders#create 自動聚焦「單號」，搜尋頁永遠停在搜尋框
 * 2) 反白：僅班別欄禁用選取（含 ::selection），拖曳不會出現藍底
 * 3) 編輯器採絕對定位覆蓋，不撐高表格；拖曳結束確實解鎖，不會卡住
 */
(function(){
  "use strict";
  if (window.__AURUM_BOOTED__) return;
  window.__AURUM_BOOTED__ = true;

  // ---------- helpers ----------
  const $  = (s,root=document)=>root.querySelector(s);
  const $$ = (s,root=document)=>Array.from(root.querySelectorAll(s));
  const on = (el,ev,fn,opt)=> el && el.addEventListener(ev,fn,opt);
  const fmtNum = n => {
    const x = (n==null||n==="")?0:Number(String(n).replace(/,/g,""));
    return isNaN(x)? "0" : x.toLocaleString();
  };
  const text = el => (el && el.textContent || '').trim();

  // －－－ 小工具：短暫「強制鎖定」焦點，避免其他腳本/瀏覽器搶回去 －－－
  function enforceFocus(target, select=true, holdMs=400){
    if(!target) return;
    const t0 = performance.now();
    let cancelling = false;
    const tick = ()=>{
      if (cancelling) return;
      if (document.activeElement !== target) {
        try{
          target.focus({ preventScroll:true });
          if(select && typeof target.select==='function') target.select();
        }catch{}
      }
      if (performance.now() - t0 < holdMs) requestAnimationFrame(tick);
    };
    // 一次到位，之後 400ms 內每一 frame 再確認一次，杜絕「先跳搜尋再跳單號」或反過來
    tick();
    // 若目標失效則停止
    const obs = new MutationObserver(()=>{
      if(!document.body.contains(target)){ cancelling=true; obs.disconnect(); }
    });
    obs.observe(document, { childList:true, subtree:true });
  }

  // KPI 同步
  let kpiChan=null; try{ if('BroadcastChannel' in window) kpiChan=new BroadcastChannel('aurum-kpi'); }catch{}
  function notifyKpiDirty(){ try{ kpiChan && kpiChan.postMessage({type:'dirty'}); }catch{} }
  if(kpiChan && location.pathname.startsWith('/kpi')){
    kpiChan.onmessage = e=>{ if(e?.data?.type==='dirty') location.reload(); };
  }

  // ---------- 班別上色 ----------
  function paintShiftCell(td){
    if(!td) return;
    const t=(td.textContent||'').trim();
    td.classList.remove('shift-morning','shift-night');
    if(/^早/.test(t)) td.classList.add('shift-morning');
    else if(/^晚/.test(t)) td.classList.add('shift-night');
  }
  function paintAllShiftCells(scope){
    $$('td[data-field="shift"]', scope||document).forEach(paintShiftCell);
  }

  // ---------- 表內編輯（覆蓋不撐高） ----------
  function makeCellEditor(td, opts){
    // opts: {id, field, url, type, value, options, onSaved}
    const old = opts.value;
    let input, saved=false;

    if(opts.type==='select'){
      input=document.createElement('select');
      (opts.options||[]).forEach(v=>{
        const o=document.createElement('option'); o.value=v; o.textContent=v;
        if(v===old) o.selected=true; input.appendChild(o);
      });
    }else{
      input=document.createElement('input');
      input.type = opts.type || 'text';
      if(opts.type==='number') input.step='1';
      input.value = old;
    }
    input.className='cell-editor center';

    // 絕對定位覆蓋，不改列高/表格寬
    td.classList.add('editing-cell');
    td.dataset.old = old;
    td.innerHTML='';
    td.appendChild(input);
    try{ input.focus(); input.select?.(); }catch{}

    const cleanup=()=>{ td.classList.remove('editing-cell'); };
    const restore=()=>{
      if(saved) return;
      td.textContent = old; paintShiftCell(td);
      cleanup();
    };
    const done=(val)=>{
      saved=true;
      td.textContent = (opts.type==='number') ? fmtNum(val) : val;
      if(opts.field==='shift') paintShiftCell(td);
      opts.onSaved && opts.onSaved(val);
      cleanup();
    };

    const save = async()=>{
      if(saved) return;
      const value = String(input.value||'').trim();
      try{
        const res = await fetch(opts.url, {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({id:opts.id, field:opts.field, value})
        });
        const j = await res.json();
        if(j && j.ok){ done(j.value); notifyKpiDirty(); }
        else restore();
      }catch(_e){ restore(); }
    };

    if (input.tagName==='SELECT'){
      on(input,'change',save);
      on(input,'blur',save);
    }else{
      on(input,'keydown',e=>{
        if(e.key==='Enter'){ e.preventDefault(); save(); }
        if(e.key==='Escape'){ e.preventDefault(); restore(); }
      });
      on(input,'blur',save);
    }
  }

  // ---------- 拖曳勾選（含 Shift 範圍） ----------
  function initDragSelect(tbody){
    if(!tbody) return;
    let dragging=false, targetState=false, lastIdx=-1;
    const rows = ()=> Array.from(tbody.querySelectorAll('tr'));

    on(tbody,'mousedown',e=>{
      if(e.button!==0) return;
      const td = e.target.closest('td'); if(!td) return;
      const tr = td.parentElement;
      const isLast = td.cellIndex === tr.cells.length-1;
      const cb = td.querySelector('input[type="checkbox"][name="selected"]');
      if(!cb || !isLast) return;

      if(e.target===cb){
        setTimeout(()=>{
          targetState = cb.checked;
          dragging = true;
          document.documentElement.classList.add('x-dragging');  // 鎖選取（只對班別欄有效，見樣式）
        },0);
        return;
      }
      e.preventDefault();
      targetState = !cb.checked;
      cb.checked = targetState;
      dragging = true;
      document.documentElement.classList.add('x-dragging');
    });

    on(tbody,'mouseover',e=>{
      if(!dragging) return;
      const tr = e.target.closest('tr'); if(!tr) return;
      const cb = tr.querySelector('input[type="checkbox"][name="selected"]');
      if (cb) cb.checked = targetState;
    });

    // 確保拖曳結束一定釋放，避免「卡住」
    const clearDragFlag = ()=>{
      dragging=false;
      document.documentElement.classList.remove('x-dragging');
    };
    on(document,'mouseup', clearDragFlag);
    on(document,'dragend', clearDragFlag);
    on(document,'mouseleave', clearDragFlag);
    on(window,'blur', clearDragFlag);
    on(document,'click', clearDragFlag);

    // Shift+Click 範圍
    on(tbody,'click',e=>{
      const cb = e.target.closest('input[type="checkbox"][name="selected"]');
      if(!cb) return;
      const rs = rows();
      const idx = rs.indexOf(cb.closest('tr'));
      if(e.shiftKey && lastIdx>=0){
        const [a,b] = lastIdx<idx ? [lastIdx,idx] : [idx,lastIdx];
        for(let i=a;i<=b;i++){
          const cbi = rs[i].querySelector('input[type="checkbox"][name="selected"]');
          if(cbi) cbi.checked = cb.checked;
        }
      }
      lastIdx = idx;
    });
  }

  // ---------- 訂單頁：分班別 + 新增列置尾 ----------
  function getShiftFromRow(tr){
    const td = tr.querySelector('td[data-field="shift"]');
    if(!td) return '';
    const v = (td.querySelector('select')?.value || text(td)).trim();
    if(!v) return '';
    if(v.startsWith('早')) return '早班';
    if(v.startsWith('晚')) return '晚班';
    return v;
  }
  function stableGroupAll(tbody){
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const early=[], late=[], other=[];
    rows.forEach(tr=>{
      const s=getShiftFromRow(tr);
      if(s==='早班') early.push(tr);
      else if(s==='晚班') late.push(tr);
      else other.push(tr);
    });
    const frag=document.createDocumentFragment();
    early.forEach(tr=>frag.appendChild(tr));
    late.forEach(tr=>frag.appendChild(tr));
    other.forEach(tr=>frag.appendChild(tr));
    tbody.innerHTML='';
    tbody.appendChild(frag);
  }
  function moveRowToShiftTail(tr, tbody){
    const s = getShiftFromRow(tr); if(!s) return;
    const rows = Array.from(tbody.querySelectorAll('tr'));
    let insertAfter=null;
    if(s==='早班'){
      for(let i=rows.length-1;i>=0;i--){ if(getShiftFromRow(rows[i])==='早班'){ insertAfter=rows[i]; break; } }
      if(insertAfter) insertAfter.after(tr);
      else{
        const firstLate = rows.find(r=>getShiftFromRow(r)==='晚班');
        if(firstLate) tbody.insertBefore(tr, firstLate);
        else tbody.insertBefore(tr, tbody.firstChild);
      }
    }else if(s==='晚班'){
      for(let i=rows.length-1;i>=0;i--){ if(getShiftFromRow(rows[i])==='晚班'){ insertAfter=rows[i]; break; } }
      if(insertAfter) insertAfter.after(tr);
      else{
        for(let i=rows.length-1;i>=0;i--){ if(getShiftFromRow(rows[i])==='早班'){ insertAfter=rows[i]; break; } }
        if(insertAfter) insertAfter.after(tr);
        else tbody.appendChild(tr);
      }
    }
  }
  function observeNewRows(tbody){
    const obs = new MutationObserver(muts=>{
      muts.forEach(m=>{
        m.addedNodes.forEach(node=>{
          if(!(node instanceof HTMLElement)) return;
          if(node.tagName==='TR'){
            paintAllShiftCells(node);
            moveRowToShiftTail(node, tbody);
          }else{
            node.querySelectorAll && node.querySelectorAll('tr').forEach(tr=>{
              paintAllShiftCells(tr);
              moveRowToShiftTail(tr, tbody);
            });
          }
        });
      });
    });
    obs.observe(tbody, {childList:true, subtree:true});
  }

  // ---------- 焦點策略：/orders#create → 單號；有 q → 搜尋；其餘不動 ----------
  function applyOrdersFocus(){
    if (location.pathname !== '/orders') return;
    const no = $('#order_no_input');
    const q  = $('form[action="/orders"] input[name="q"]') || $('input[name="q"]');
    const url = new URL(location.href);
    const hasQ = !!(url.searchParams.get('q') || '').trim();
    const isCreate = (location.hash === '#create');

    if (isCreate && no){
      enforceFocus(no, true, 450);     // 牢牢黏住單號，消除「先跳搜尋再跳單號」的閃動
      return;
    }
    if (hasQ && q){
      // 搜尋時就黏在搜尋框（尾端），不讓任何腳本再跳走
      try{ q.setSelectionRange(q.value.length, q.value.length); }catch{}
      enforceFocus(q, false, 450);
    }
  }

  // ---------- 訂單頁初始化 ----------
  function initOrdersPage(){
    const table = $('#orders-table'); if(!table) return;
    const tbody = $('#orders-body') || table.tBodies[0];

    paintAllShiftCells(table);
    stableGroupAll(tbody);
    observeNewRows(tbody);

    // 表內編輯
    let editingNow=null;
    on(tbody,'click',e=>{
      const td = e.target.closest('td.editable'); if(!td) return;
      if(editingNow && editingNow===td) return;
      editingNow = td;

      const tr = td.closest('tr');
      const id = tr.getAttribute('data-id');
      const field = td.getAttribute('data-field');
      const raw = td.textContent.trim().replace(/,/g,'');

      let type='text', options=null;
      if(field==='shift'){ type='select'; options=['早班','晚班']; }
      else if(field==='amount'){ type='number'; }
      else if(field==='odt'){ type='date'; }

      makeCellEditor(td, {
        id, field, url:'/orders/update-json', type, value:raw, options,
        onSaved:(val)=>{
          if(field==='shift'){
            td.textContent = (/^早/.test(val)?'早班': /^晚/.test(val)?'晚班': val);
            paintShiftCell(td);
            moveRowToShiftTail(tr, tbody);
          }
        }
      });

      const obs = new MutationObserver(()=>{
        if(!td.querySelector('.cell-editor')){ editingNow=null; obs.disconnect(); }
      });
      obs.observe(td,{childList:true, subtree:true});
    });

    // 拖曳勾選
    initDragSelect(tbody);

    // 表頭排序（點同欄第二次恢復）
    const orig = Array.from(tbody.querySelectorAll('tr'));
    let currentKey=null;
    function restore(){
      while(tbody.firstChild) tbody.removeChild(tbody.firstChild);
      orig.sort((a,b)=> Number(a.dataset.idx)-Number(b.dataset.idx));
      orig.forEach(tr=>tbody.appendChild(tr));
      stableGroupAll(tbody);
    }
    function applySort(key){
      if(currentKey===key){ currentKey=null; return restore(); }
      const rows = Array.from(orig);
      rows.sort((a,b)=>{
        const ta = a.querySelector(`[data-field="${key}"]`).textContent.trim().replace(/,/g,'');
        const tb = b.querySelector(`[data-field="${key}"]`).textContent.trim().replace(/,/g,'');
        if(key==='amount') return Number(ta)-Number(tb);
        return (ta>tb?1:ta<tb?-1:0);
      });
      while(tbody.firstChild) tbody.removeChild(tbody.firstChild);
      rows.forEach(tr=>tbody.appendChild(tr));
      stableGroupAll(tbody);
      currentKey=key;
    }
    $$('#orders-table th.sortable').forEach(th=> on(th,'click',()=>applySort(th.dataset.key)));

    // 新增送出時（導回 #create），這裡只發 KPI 髒訊號
    const createForm = $('#form-create');
    if(createForm){ on(createForm,'submit', ()=>{ notifyKpiDirty(); }); }

    // 專屬焦點（最後做，並以短暫鎖定方式避免被其他程式覆寫）
    applyOrdersFocus();

    // －－－ 班別欄反白補丁 & 編輯器覆蓋樣式（最高權重 + !important）－－－
    const stylePatch=document.createElement('style');
    stylePatch.textContent = `
      /* 只鎖班別欄的文字選取（拖曳經過不會出現藍底） */
      #orders-table td[data-field="shift"],
      #orders-table td[data-field="shift"] *{
        -webkit-user-select:none !important; user-select:none !important;
      }
      #orders-table td[data-field="shift"]::selection,
      #orders-table td[data-field="shift"] *::selection{
        background:transparent !important; color:inherit !important;
      }
      #orders-table td[data-field="shift"]::-moz-selection,
      #orders-table td[data-field="shift"] *::-moz-selection{
        background:transparent !important; color:inherit !important;
      }
      /* hover 高亮不覆蓋班別色 */
      #orders-table td[data-field="shift"].editable:hover{ box-shadow:none !important; }
      #orders-table tr:hover td[data-field="shift"]{ background:inherit !important; }
      #orders-table td[data-field="shift"] .cell-editor{ background:transparent !important; }

      /* 編輯器絕對定位覆蓋，不撐高、不改寬 */
      #orders-table td.editable{ position:relative; }
      #orders-table td.editable.editing-cell .cell-editor{
        position:absolute; inset:2px 4px;
        height:auto; min-height:0;
        border:1px solid var(--line, #E5D7B2);
        border-radius:8px; padding:0 8px; margin:0;
        font: inherit; line-height: normal;
        box-sizing: border-box; background: transparent;
      }
    `;
    document.head.appendChild(stylePatch);
  }

  // ---------- 支出頁 ----------
  function initExpensesPage(){
    const table = $('#expenses-table'); if(!table) return;
    const tbody = $('#expenses-body') || table.tBodies[0];

    const CAT_OPTIONS = ['原料','租金','人事','菜錢','雜支','租金水電','其他'];

    let editingNow=null;
    on(tbody,'click',e=>{
      const td = e.target.closest('td.editable'); if(!td) return;
      if(editingNow && editingNow===td) return;
      editingNow = td;

      const tr = td.closest('tr');
      const id = tr.getAttribute('data-id');
      const field = td.getAttribute('data-field');
      const raw = td.textContent.trim().replace(/,/g,'');

      let type='text', options=null;
      if(field==='cat'){ type='select'; options=CAT_OPTIONS; }
      else if(field==='amount'){ type='number'; }
      else if(field==='odt'){ type='date'; }

      makeCellEditor(td, { id, field, url:'/expenses/update-json', type, value:raw, options,
        onSaved:()=>notifyKpiDirty() });

      const obs = new MutationObserver(()=>{
        if(!td.querySelector('.cell-editor')){ editingNow=null; obs.disconnect(); }
      });
      obs.observe(td,{childList:true, subtree:true});
    });

    initDragSelect(tbody);
  }

  // ---------- KPI/報表：變更自動送出 ----------
  function initAutoSubmitForms(){
    const kForm = $('form[action="/kpi"]');
    if(kForm){
      const modeEl=kForm.querySelector('[name="mode"]');
      const dtEl  =kForm.querySelector('[name="dt"], [name="od"], input[type="date"]');
      on(modeEl,'change',()=>kForm.submit());
      on(dtEl,  'change',()=>kForm.submit());
    }
    const repForm = $('form[action="/reports"]');
    if(repForm){
      const modeEl=repForm.querySelector('[name="mode"], #rep-mode');
      const dtEl  =repForm.querySelector('[name="dt"], #rep-dt, input[type="date"]');
      on(modeEl,'change',()=>repForm.submit());
      on(dtEl,  'change',()=>repForm.submit());
    }
  }

  // ---------- boot ----------
  function boot(){
    initOrdersPage();
    initExpensesPage();
    initAutoSubmitForms();
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
