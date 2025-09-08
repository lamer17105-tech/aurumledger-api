/* app/static/js/app.js
 * 訂單/支出：表內編輯、排序、拖曳勾選（含 Shift 範圍）
 * KPI/報表：日期變更自動送出、CSV 匯出（補 BOM）
 * 無外部依賴
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

  // ---------- 班別上色 ----------
  function paintShiftCell(td){
    if(!td) return;
    const t = (td.textContent||'').trim();
    td.classList.remove('shift-morning','shift-night');
    if (/早/.test(t)) td.classList.add('shift-morning');
    else if (/晚/.test(t)) td.classList.add('shift-night');
  }
  function paintAllShiftCells(scope){
    $$('td[data-field="shift"]', scope||document).forEach(paintShiftCell);
  }

  // ---------- 拖曳勾選（最後一欄；點擊可勾、拖曳可連選、Shift 範圍） ----------
  function initDragSelect(tbody){
    if(!tbody) return;

    const isSelectCell = (td)=>{
      if(!td) return false;
      const tr = td.parentElement;
      return td.cellIndex === tr.cells.length - 1; // 確認最後一欄
    };
    const getRows = ()=> Array.from(tbody.querySelectorAll('tr'));

    let dragging = false;
    let targetState = null;
    let lastIdx = -1;

    // 開始：只在「選取」欄
    on(tbody, 'pointerdown', (e)=>{
      if (e.button !== 0) return; // 只處理左鍵
      const td = e.target.closest('td'); if(!td || !isSelectCell(td)) return;
      const cb = td.querySelector('input[type="checkbox"][name="selected"]'); if(!cb) return;

      if (e.target === cb){
        // 讓瀏覽器先切換，再讀取最新狀態做拖曳
        setTimeout(()=>{ targetState = cb.checked; dragging = true; }, 0);
        return;
      }
      // 點到單元格空白處 → 我們負責切換
      e.preventDefault();
      targetState = !cb.checked;
      cb.checked = targetState;
      dragging = true;
    }, {passive:false});

    // 拖曳經過列 → 同步套用
    on(tbody, 'pointerenter', (e)=>{
      if(!dragging) return;
      const tr = e.target.closest('tr'); if(!tr) return;
      const cb = tr.querySelector('input[type="checkbox"][name="selected"]');
      if(cb) cb.checked = targetState;
    });

    on(document, 'pointerup', ()=>{ dragging=false; });

    // Shift + Click 範圍勾
    on(tbody, 'click', (e)=>{
      const cb = e.target.closest('input[type="checkbox"][name="selected"]');
      if(!cb) return;
      const rows = getRows();
      const idx  = rows.indexOf(cb.closest('tr'));
      if (e.shiftKey && lastIdx >= 0){
        const [a,b] = lastIdx < idx ? [lastIdx, idx] : [idx, lastIdx];
        for(let i=a; i<=b; i++){
          const cbi = rows[i].querySelector('input[type="checkbox"][name="selected"]');
          if(cbi) cbi.checked = cb.checked;
        }
      }
      lastIdx = idx;
    });
  }

  // ---------- 通用表內編輯 ----------
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

  // ---------- 訂單頁 ----------
  function initOrdersPage(){
    const table = $('#orders-table'); if(!table) return;
    const tbody = $('#orders-body') || table.tBodies[0];

    // 班別上色
    paintAllShiftCells(table);

    // 表內編輯
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
      if(field==='shift'){ type='select'; options=['早班','晚班']; }
      else if(field==='amount'){ type='number'; }
      else if(field==='odt'){ type='date'; }

      makeCellEditor(td, { id, field, url:'/orders/update-json', type, value: raw, options });

      const obs = new MutationObserver(()=>{
        if(!td.querySelector('.cell-editor')){ editingNow = null; obs.disconnect(); }
      });
      obs.observe(td, {childList:true, subtree:true});
    });

    // 表頭排序
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

    // 拖曳勾選
    initDragSelect(tbody);
  }

  // ---------- 支出頁 ----------
  function initExpensesPage(){
    const table = $('#expenses-table'); if(!table) return;
    const tbody = $('#expenses-body') || table.tBodies[0];

    const CAT_OPTIONS = ['原料','租金','人事','菜錢','雜支','租金水電','其他'];

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

  // ---------- KPI/報表：變更自動送出 ----------
  function initAutoSubmitForms(){
    const kForm = $('#range-form') || $('form[action="/kpi"]');
    if(kForm){
      const modeEl = kForm.querySelector('[name="mode"]');
      const dtEl   = kForm.querySelector('[name="dt"]');
      on(modeEl,'change', ()=> kForm.submit());
      on(dtEl,  'change', ()=> kForm.submit());
    }
    const repForm = $('#rep-form') || $('form[action="/reports"]');
    if(repForm){
      const modeEl = repForm.querySelector('[name="mode"], #rep-mode');
      const dtEl   = repForm.querySelector('[name="dt"], #rep-dt');
      on(modeEl,'change', ()=> repForm.submit());
      on(dtEl,  'change', ()=> repForm.submit());
    }
  }

  // ---------- 匯出 CSV（補 BOM） ----------
  async function exportCsv(kind){
    const scopeEl = $('#rep-mode') || $('#mode');
    const dtEl    = $('#rep-dt')   || $('#dt') || document.querySelector('[name="dt"]');
    if(!scopeEl || !dtEl){ alert('找不到匯出參數'); return; }
    const url = `/export/${kind}.csv?scope=${encodeURIComponent(scopeEl.value)}&base=${encodeURIComponent(dtEl.value)}`;
    const res = await fetch(url, {cache:'no-store'});
    if(!res.ok) return alert('匯出失敗');
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
/* === KPI 金額自動縮放（不動版型，只調字級） === */
(function(){
  "use strict";

  function fitText(el, opts){
    const cfg = Object.assign({min: 24, step: 1}, opts||{});
    const getMax = () => parseFloat(getComputedStyle(el).fontSize) || 56;

    function run(){
      // 先回到最大字，再往下微調直到不溢出
      let size = getMax();
      el.style.fontSize = size + 'px';

      // 允許一點點誤差（避免高 DPI 抖動）
      const fits = () => el.scrollWidth <= el.clientWidth + 1 && el.scrollHeight <= el.clientHeight + 1;

      let guard = 0;
      while (!fits() && size > cfg.min && guard < 200){
        size -= cfg.step;
        el.style.fontSize = size + 'px';
        guard++;
      }
    }

    run();

    // 視窗/容器尺寸改變時重新套用
    const ro = new ResizeObserver(run);
    ro.observe(el);
    window.addEventListener('resize', run);

    // 文字內容變動時也重算（例如切換期間）
    new MutationObserver(run).observe(el, {childList:true, characterData:true, subtree:true});
  }

  function initKpiAutoFit(){
    document.querySelectorAll('.kpi-card .kpi-value').forEach(el=>{
      // 一般卡給較低下限，淺紫色「營收」卡通常比較大，可再放寬一點
      const isRevenue = el.closest('.kpi-card')?.classList.contains('kpi-net');
      fitText(el, {min: isRevenue ? 28 : 24, step: 1});
    });
  }

  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', initKpiAutoFit);
  }else{
    initKpiAutoFit();
  }
})();
