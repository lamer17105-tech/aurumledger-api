// app/static/js/app.js
function $(s, r=document){ return r.querySelector(s); }

const loginForm = $("#loginForm");
if (loginForm) {
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(loginForm);
    const res = await fetch("/auth/login", { method:"POST", body: fd });
    if (res.ok) location.href = "/orders";
    else alert("登入失敗：帳號或密碼錯誤");
  });
}

const btnLogout = $("#btnLogout");
if (btnLogout) {
  btnLogout.addEventListener("click", async () => {
    await fetch("/auth/logout", { method:"POST" });
    location.href = "/login";
  });
}

const btnExportOrders = $("#btnExportOrders");
if (btnExportOrders) btnExportOrders.addEventListener("click", () => window.location.href="/data/export/orders");

const btnExportExpenses = $("#btnExportExpenses");
if (btnExportExpenses) btnExportExpenses.addEventListener("click", () => window.location.href="/data/export/expenses");

const importForm = $("#importForm");
if (importForm) {
  importForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(importForm);
    const t = fd.get("table");
    const fileInput = importForm.querySelector('input[type="file"]');
    if (!fileInput.files.length) return alert("請選擇 CSV 檔");
    fd.set("file", fileInput.files[0]);
    const res = await fetch(`/data/import/${t}`, { method:"POST", body: fd });
    if (res.ok) {
      const j = await res.json();
      alert(`匯入完成：${j.inserted} 筆`);
      location.reload();
    } else {
      const err = await res.json().catch(()=>({detail:"未知錯誤"}));
      alert(`匯入失敗：${err.detail}`);
    }
  });
}
