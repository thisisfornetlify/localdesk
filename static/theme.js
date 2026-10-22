// Apply before styles load, so the saved theme does not flash on navigation.
(() => {
  'use strict';
  const key = 'localdesk-theme';
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  let preference;
  try { preference = localStorage.getItem(key); } catch { /* Storage can be disabled. */ }
  const valid = theme => theme === 'dark' || theme === 'light';
  if (!valid(preference)) preference = null;

  function apply(theme) {
    document.documentElement.dataset.theme = theme;
    const dark = theme === 'dark';
    const toggle = document.getElementById('theme-toggle');
    if (toggle) {
      const action = dark ? 'Switch to light mode' : 'Switch to dark mode';
      toggle.setAttribute('aria-label', action);
      toggle.title = action;
      document.getElementById('theme-label').textContent = dark ? 'Light mode' : 'Dark mode';
      document.getElementById('theme-icon').textContent = dark ? '☀' : '☾';
    }
    document.querySelector('meta[name="theme-color"]').content = dark ? '#141b18' : '#203e33';
  }

  const currentDefault = () => preference || (system.matches ? 'dark' : 'light');
  apply(currentDefault());
  document.addEventListener('DOMContentLoaded', () => {
    apply(currentDefault());
    document.getElementById('theme-toggle').addEventListener('click', () => {
      preference = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem(key, preference); } catch { /* Keep working for this tab. */ }
      apply(preference);
    });
  });
  system.addEventListener('change', () => { if (!preference) apply(currentDefault()); });
  window.addEventListener('storage', event => {
    if (event.key !== key && event.key !== null) return;
    preference = valid(event.newValue) ? event.newValue : null;
    apply(currentDefault());
  });
})();
