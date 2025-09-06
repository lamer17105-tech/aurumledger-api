// app/static/js/app.js
// 可擴充的全站 JS；先保留 active 樣式強化或之後放行為
document.addEventListener('DOMContentLoaded', () => {
  // 讓目前路徑對應的選單有 active 樣式（保險起見）
  const here = location.pathname;
  document.querySelectorAll('.menu-item').forEach(a => {
    if (here === '/' && a.getAttribute('href') === '/') a.classList.add('active');
    if (here.startsWith(a.getAttribute('href')) && a.getAttribute('href') !== '/') {
      a.classList.add('active');
    }
  });
});
