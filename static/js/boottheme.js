// @ts-check
// Kalmido web client (#6365): the look of the first picture. A blocking script at the top of <head> (index.html; the CSP
// allows no inline script) sets theme, accent, theme pack, font size and html.rebooting before the loading screen (#boot)
// is drawn, so a cold start or a reload no longer flashes the system colours or the logo. icons.js keeps the same logic:
// applyTheme = bt_theme, applyLook sets the font size with bt_fsize and checks accent and pack against its LOOK table.
const bt_get = (/** @type {string} */ k) => { try { const v = localStorage.getItem('tasks.' + k); return v == null ? null : JSON.parse(v); } catch { return null; } };
// design per device: auto (follows the OS) | dark | light
function bt_theme() {
  const pref = bt_get('theme') || 'auto';
  document.documentElement.dataset.theme = pref;
  let light = pref === 'light';
  try { light = light || (pref === 'auto' && matchMedia('(prefers-color-scheme: light)').matches); } catch { /* old browser */ }
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', light ? '#f8f8f9' : '#16171a');
}
// (#429): the font size is a percentage (75-150 since 2.13.2) in steps of 5 (per device, LS fsize); the old steps s / m / l / xl
// (90 / 100 / 112 / 125) are read as their percentages. Named steps keep data-fsize (the CSS rules), any other value sets
// --ui inline. Below 100 % touch screens keep 44 px hit areas (app.css: .ui-small), only the text and spacing shrink.
/** @type {Record<string, number>} */
const FS_OLD = {s: 90, m: 100, l: 112, xl: 125};
// (#478 N5, decision #429): 75-150 %. At 50 % the text was 7.5 px (unreadable) and the 44 px touch rows bent the
// proportions; a stored value below 75 (2.13.0 / 2.13.1) counts as 75
const FS_MIN = 75, FS_MAX = 150;
const fsPct = () => { const v = bt_get('fsize'); if (typeof v === 'string' && v in FS_OLD) return FS_OLD[v]; const n = +v; return n >= 50 && n <= FS_MAX ? Math.max(FS_MIN, Math.round(n)) : 100; };
function bt_fsize() {
  const h = document.documentElement, pct = fsPct(), named = Object.keys(FS_OLD).find(k => FS_OLD[k] === pct);
  h.dataset.fsize = named || 'custom';
  if (named) h.style.removeProperty('--ui'); else h.style.setProperty('--ui', String(pct / 100));
  h.classList.toggle('ui-small', pct < 100);
}
bt_theme();
bt_fsize();
for (const k of ['accent', 'pack']) { const v = bt_get(k); if (typeof v === 'string' && /^[a-z]+$/.test(v)) document.documentElement.dataset[k] = v; }  // icons.js applyLook checks them against LOOK
try { if (sessionStorage.getItem('kalmido.booted')) document.documentElement.classList.add('rebooting'); } catch { /* no storage */ }  // (#1213): no loading screen on a reload within a session
