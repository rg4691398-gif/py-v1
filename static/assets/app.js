// Sidebar toggle (mobile drawer)
(() => {
  const btn = document.querySelector('[data-sidebar-toggle]');
  const overlay = document.querySelector('[data-sidebar-overlay]');
  const sidebar = document.querySelector('[data-sidebar]');
  if (!btn || !overlay || !sidebar) return;

  const open = () => {
    sidebar.classList.remove('-translate-x-full');
    overlay.classList.remove('hidden');
    document.body.classList.add('overflow-hidden');
  };
  const close = () => {
    sidebar.classList.add('-translate-x-full');
    overlay.classList.add('hidden');
    document.body.classList.remove('overflow-hidden');
  };

  btn.addEventListener('click', () => {
    if (overlay.classList.contains('hidden')) open();
    else close();
  });

  overlay.addEventListener('click', close);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') close();
  });

  sidebar.addEventListener('click', (e) => {
    const a = e.target.closest('a');
    if (!a) return;
    if (window.matchMedia('(max-width: 1023px)').matches) close();
  });
})();
