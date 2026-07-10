(function () {
  const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
  function apply() {
    document.querySelectorAll('.ticker-state').forEach(el => {
      el.style.animationPlayState = mq.matches ? 'paused' : 'running';
    });
    if (mq.matches) {
      document.querySelectorAll('.ticker-state--completed').forEach(el => {
        el.style.opacity = '1';
      });
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', apply);
  } else {
    apply();
  }
  mq.addEventListener('change', apply);
})();
