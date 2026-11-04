document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('.main-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', () => {
      const open = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', String(open));
      toggle.textContent = open ? '×' : '☰';
    });
  }

  const launch = document.getElementById('assistantLaunch');
  const panel = document.getElementById('assistantPanel');
  const close = document.getElementById('assistantClose');
  if (launch && panel) {
    launch.addEventListener('click', () => { panel.hidden = !panel.hidden; });
  }
  if (close && panel) close.addEventListener('click', () => { panel.hidden = true; });
});
