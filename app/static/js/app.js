// === force-load AurumLedger CSS (gold5) ===
(function(){
  try{
    if (document.querySelector('link[data-al-css]')) return;
    var cur = (document.currentScript && document.currentScript.src) || '';
    var cssURL = '/static/css/style.css?v=gold5';
    if (cur && cur.indexOf('/static/js/') !== -1) {
      cssURL = cur.split('/static/js/')[0] + '/static/css/style.css?v=gold5';
    }
    var l = document.createElement('link');
    l.rel = 'stylesheet';
    l.href = cssURL;
    l.setAttribute('data-al-css','1');
    document.head.appendChild(l);
  }catch(e){}
})();
// === force-load AurumLedger CSS (gold4) ===
(function(){
  try{
    if (document.querySelector('link[data-al-css]')) return;
    var cur = (document.currentScript && document.currentScript.src) || '';
    var cssURL = '/static/css/style.css?v=gold4';
    if (cur && cur.indexOf('/static/js/') !== -1) {
      cssURL = cur.split('/static/js/')[0] + '/static/css/style.css?v=gold4';
    }
    var l = document.createElement('link');
    l.rel = 'stylesheet';
    l.href = cssURL;
    l.setAttribute('data-al-css','1');
    document.head.appendChild(l);
  }catch(e){}
})();

/* app/static/js/app.js
 * 閮/?臬嚗”?抒楊頛胯?摨??喳?賂???Shift 蝭?嚗?
 * KPI/?梯”嚗???渲??SV ?臬嚗? BOM嚗?
 * ?∪??其?鞈???base.html ?芾??仿??臬??
 */
(function(){
  "use strict";
  if (window.__APP_BOOTED__) return;
  window.__APP_BOOTED__ = true;

  // ---------- helpers ----------
  const $  = (s,root=document)=>root.querySelector(s);
  const $$ = (s,root=document)=>Array.from(root.querySelectorAll(s));
  const on = (el,ev,fn,o)=> el && el.addEventListener(ev,fn,o);
  const fmtNum = n => {
    const x = (n==null||n==="")?0:Number(String(n).replace(/,/g,""));
    return isNaN(x)? "0" : x.toLocaleString();
  };

  async function saveWithPicker(filename, blob){
    if ('showSaveFilePicker' in window){
      const handle = await window.showSaveFilePicker({
        suggestedName: filename,
        types: [{ description: 'CSV', accept: { 'text/csv': ['.csv'] } }]
      });
      const w = await handle.createWritable(); await w.write(blob); await w.close();
    }else{
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href=url; a.download=filename;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    }
  }

  // ---------- ?剖銝 ----------
  function paintShiftSelect(sel){
    if(!sel) return;
    sel.classList.remove('is-morning','is-night');
    const v = (sel.value || sel.options?.[sel.selectedIndex]?.text || '').trim();
    if (/??.test(v)) sel.classList.add('is-morning');
    else if (/??.test(v)) sel.classList.add('is-night');
  }
  function paintShiftCell(td){
    if(!td) return;
    const t = (td.textContent||'').trim();
    td.classList.remove('shift-morning','shift-night');
    if(/??.test(t)) td.classList.add('shift-morning');
    else if(/??.test(t)) td.classList.add('shift-night');
  }
  function paintAllShiftCells(scope){
    $$('td[data-field="shift"]', scope||document).forEach(paintShiftCell);
  }

  // ---------- ??暸嚗暺? Shift 蝭?嚗?----------
  function initDragSelect(tbody){
    if(!tbody) return;
    const getRows = ()=> Array.from(tbody.querySelectorAll('tr'));
    let dragging = false, targetState = false, lastIdx = -1;

    // mousedown嚗?具????嚗?湔暺?checkbox嚗??汗?函???
    on(tbody,'mousedown',(e)=>{
      if(e.button !== 0) return;
      const td = e.target.closest('td'); if(!td) return;
      const tr = td.parentElement;
      const isLast = td.cellIndex === tr.cells.length - 1;
      const cb = td.querySelector('input[type="checkbox"][name="selected"]');
      if(!cb || !isLast) return;

      // ?湔暺?checkbox嚗?摰???嚗????嚗??啁????
      if (e.target === cb){
        setTimeout(()=>{ targetState = cb.checked; dragging = true; }, 0);
        return;
      }

      // 暺蝛箇????鞎砍???銝衣??駁脣?
      e.preventDefault();
      targetState = !cb.checked;
      cb.checked = targetState;
      dragging = true;
    });

    // mouseover嚗??喟?????甇亙???
    on(tbody,'mouseover',(e)=>{
      if(!dragging) return;
      const tr = e.target.closest('tr'); if(!tr) return;
      const cb = tr.querySelector('input[type="checkbox"][name="selected"]');
      if(cb) cb.checked = targetState;
    });

    on(document,'mouseup',()=> dragging=false);

    // Shift+Click 蝭???
    on(tbody,'click',(e)=>{
      const cb = e.target.closest('input[type="checkbox"][name="selected"]');
      if(!cb) return;
      const rows = getRows();
      const idx = rows.indexOf(cb.closest('tr'));
      if(e.shiftKey && lastIdx >= 0){
        const [a,b] = lastIdx < idx ? [lastIdx, idx] : [idx, lastIdx];
        for(let i=a;i<=b;i++){
          const cbi = rows[i].querySelector('input[type="checkbox"][name="selected"]');
          if(cbi) cbi.checked = cb.checked;
        }
      }
      lastIdx = idx;
    });
  }

  // ---------- ?銵典蝺刻摩嚗?嚗?----------
  function makeCellEditor(td, opts){
    // opts: {id, field, url, type, value, options}
    const old = opts.value;
    let input, saved = false;

    if(opts.type === 'select'){
      input = document.createElement('select');
      (opts.options||[]).forEach(v=>{
        const o=document.createElement('option'); o.value=v; o.textContent=v;
        if(v===old) o.selected=true; input.appendChild(o);
      });
    }else{
      input = document.createElement('input');
      input.type = opts.type || 'text';
      if(opts.type==='number') input.step='1';
      input.value = old;
    }
    input.className = 'cell-editor center';
    td.dataset.old = old;
    td.innerHTML=''; td.appendChild(input);
    input.focus(); input.select?.();

    const restore = ()=>{ if(saved) return; td.textContent = old; paintShiftCell(td); };
    const done = (val)=>{
      saved = true;
      td.textContent = (opts.type==='number') ? fmtNum(val) : val;
      if(opts.field==='shift') paintShiftCell(td);
    };

    const save = async ()=>{
      if(saved) return;
      const value = String(input.value||'').trim();
      try{
        const res = await fetch(opts.url, {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({id: opts.id, field: opts.field, value})
        });
        const j = await res.json();
        if(j && j.ok) done(j.value); else restore();
      }catch(_e){ restore(); }
    };

    if (input.tagName==='SELECT'){
      on(input,'change', save);
      on(input,'blur',   save);
    }else{
      on(input,'keydown',(e)=>{
        if(e.key==='Enter'){ e.preventDefault(); save(); }
        if(e.key==='Escape'){ e.preventDefault(); restore(); }
      });
      on(input,'blur', save);
    }
  }

  // ---------- 閮??----------
  function initOrdersPage(){
    const table = $('#orders-table'); if(!table) return;
    const tbody = $('#orders-body') || table.tBodies[0];

    // ?啣???乩?????
    const createShiftSel = document.querySelector('.order-create select[name="shift"]');
    if(createShiftSel){ paintShiftSelect(createShiftSel); on(createShiftSel,'change',()=>paintShiftSelect(createShiftSel)); }

    paintAllShiftCells(table);

    // 銵典蝺刻摩
    let editingNow = null;
    on(tbody,'click',(e)=>{
      const td = e.target.closest('td.editable');
      if(!td) return;
      if(editingNow && editingNow===td) return;
      editingNow = td;

      const tr = td.closest('tr');
      const id = tr.getAttribute('data-id');
      const field = td.getAttribute('data-field');
      const raw = td.textContent.trim().replace(/,/g,'');

      let type='text', options=null;
      if(field==='shift'){ type='select'; options=['?拍','?']; }
      else if(field==='amount'){ type='number'; }
      else if(field==='odt'){ type='date'; }

      makeCellEditor(td, { id, field, url:'/orders/update-json', type, value: raw, options });

      const obs = new MutationObserver(()=>{
        if(!td.querySelector('.cell-editor')){ editingNow = null; obs.disconnect(); }
      });
      obs.observe(td, {childList:true, subtree:true});
    });

    // 銵券??
    const orig = Array.from(tbody.querySelectorAll('tr'));
    let currentKey = null;
    function restore(){
      while(tbody.firstChild) tbody.removeChild(tbody.firstChild);
      orig.sort((a,b)=> Number(a.dataset.idx)-Number(b.dataset.idx));
      orig.forEach(tr=>tbody.appendChild(tr));
    }
    function applySort(key){
      if(currentKey === key){ currentKey=null; return restore(); }
      const rows = Array.from(orig);
      rows.sort((a,b)=>{
        const ta = a.querySelector(`[data-field="${key}"]`).textContent.trim().replace(/,/g,'');
        const tb = b.querySelector(`[data-field="${key}"]`).textContent.trim().replace(/,/g,'');
        if(key==='amount') return Number(ta)-Number(tb);
        return (ta>tb?1:ta<tb?-1:0);
      });
      while(tbody.firstChild) tbody.removeChild(tbody.firstChild);
      rows.forEach(tr=>tbody.appendChild(tr));
      currentKey = key;
    }
    $$('#orders-table th.sortable').forEach(th=> on(th,'click',()=>applySort(th.dataset.key)));

    // ??暸
    initDragSelect(tbody);
  }

  // ---------- ?臬??----------
  function initExpensesPage(){
    const table = $('#expenses-table'); if(!table) return;
    const tbody = $('#expenses-body') || table.tBodies[0];

    const CAT_OPTIONS = ['??','蝘?','鈭箔?','?','?','蝘?瘞湧','?嗡?'];

    let editingNow = null;
    on(tbody,'click',(e)=>{
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

      makeCellEditor(td, { id, field, url:'/expenses/update-json', type, value: raw, options });

      const obs = new MutationObserver(()=>{
        if(!td.querySelector('.cell-editor')){ editingNow = null; obs.disconnect(); }
      });
      obs.observe(td, {childList:true, subtree:true});
    });

    initDragSelect(tbody);
  }

  // ---------- KPI/?梯”嚗??渲? ----------
  function initAutoSubmitForms(){
    // KPI嚗ame 敹???mode / dt嚗???蝡臬停?臬????
    const kForm = $('#range-form') || $('form[action="/kpi"]');
    if(kForm){
      const modeEl = kForm.querySelector('[name="mode"]');
      const dtEl   = kForm.querySelector('[name="dt"]');
      on(modeEl,'change', ()=> kForm.submit());
      on(dtEl,  'change', ()=> kForm.submit());
    }
    // Reports
    const repForm = $('#rep-form') || $('form[action="/reports"]');
    if(repForm){
      const modeEl = repForm.querySelector('[name="mode"], #rep-mode');
      const dtEl   = repForm.querySelector('[name="dt"], #rep-dt');
      on(modeEl,'change', ()=> repForm.submit());
      on(dtEl,  'change', ()=> repForm.submit());
    }
  }

  // ---------- ?臬 CSV嚗? BOM嚗?----------
  async function exportCsv(kind){
    const scopeEl = $('#rep-mode') || $('#mode');
    const dtEl    = $('#rep-dt')   || $('#dt') || document.querySelector('[name="dt"]');
    if(!scopeEl || !dtEl){ alert('?曆??啣?箏???); return; }
    const url = `/export/${kind}.csv?scope=${encodeURIComponent(scopeEl.value)}&base=${encodeURIComponent(dtEl.value)}`;
    const res = await fetch(url, {cache:'no-store'});
    if(!res.ok) return alert('?臬憭望?');
    let buf = await res.arrayBuffer();
    let data = new Uint8Array(buf);
    if (data.length>=3 && data[0]===0xEF && data[1]===0xBB && data[2]===0xBF) data = data.slice(3);
    const bom = new Uint8Array([0xEF,0xBB,0xBF]);
    const out = new Uint8Array(bom.length + data.length);
    out.set(bom,0); out.set(data,bom.length);
    await saveWithPicker(`${kind}_${scopeEl.value}_${dtEl.value}.csv`, new Blob([out],{type:'text/csv;charset=utf-8'}));
  }
  window.exportCsv = exportCsv;

  // ---------- boot ----------
  function boot(){
    initOrdersPage();
    initExpensesPage();
    initAutoSubmitForms();
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();

