// #7555 UI test: which settings sections are open at the start (settings.js SF_SHUT, decision of 20.11.2026).
// kalmido-suite: fresh
// freelancer-matrix: settings
// Own container (start.sh), Firefox, German, invented data only. Alice is the admin of the organisation "Alpha Studio"
// (her workspace: the organisation); Frida has no organisation.
// Every folded tab at 412 px and at 1280 px, as Alice and as Frida:
// - a section is open at the start unless SF_SHUT lists it ('lang' / 'selten'); the first section of a tab is always open
//   (Konto: Profil); Company & office: only its first group open
// - an open section (not the first of its tab) is at most 320 px high (content measured, opened one by one): else it belongs
//   in SF_SHUT as 'lang'; a section in SF_SHUT as 'lang' is higher than 320 px at 412 px: else it should be open - so the
//   rule keeps itself right for new sections
// - every section of a tab has its own icon (no two head rows of a tab with the same one)
// - opened or closed by hand still wins (settings_more o: / c:), also against the new start
// The measured list is printed (MEASURE lines) for the task's comment.
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7555_settings_open', check, shots: 'P7555_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (process.env.P7555_NOSTART !== '1') execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const FEAT = 'cal,comments,collab,files,docs,office,clients';
const TABS = ['account', 'general', 'look', 'nav', 'modules', 'notify', 'integr', 'docs', 'data', 'help', 'biz'];
const MAX = 320;
const SUM = [];  // the measured list, printed at the end

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'de', collab_all: true, modules: ['cal', 'comments']});
  const me = (await call(CA, 'GET', '/api/state')).me.id;
  const ORG = (await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha Studio', admin_id: me})).id;
  check(!!ORG, 'setup: an organisation');
  await call(CA, 'PATCH', '/api/settings', {lang: 'de', tour: 'done', features: FEAT, workspace: `org:${ORG}`});
  const fr = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fr.http < 300, 'setup: a person without an organisation');
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'de', tour: 'done', features: FEAT, workspace: 'private'});

  const stored = `fetch('/api/state', {headers: {'X-Requested-With': 'kalmido'}}).then(r => r.json()).then(j => j.settings.settings_more || '[]')`;
  const ROW = k => `document.querySelector('.smodal details[data-sf="${k}"]')`;
  const signIn = async ({ev, nav, until}, who) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); return 1; })()`);
    await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${who}', password: 'password123'})}).then(r => r.status)`);
    await nav(B + '#home');
    return until(`typeof settingsModal === 'function' && !!document.querySelector('#view') && document.documentElement.lang === 'de'`);
  };
  const open = async (o, tab) => {
    await o.ev(`(() => { document.querySelectorAll('.smodal').forEach(m => m.remove()); settingsModal('${tab}'); return 1; })()`);
    const okk = await o.until(`!!document.querySelector('.smodal [data-pane="${tab}"]:not(.hidden) details[data-sf]')`, {timeout: 15000});
    await o.idle({quiet: 500});  // what the tab draws after loading (sessions, servers, the office ...) is folded too
    return okk;
  };
  // the head rows of the open tab: key, open at the start, its default, its reason, icon, content height (opened one by one)
  const MEAS = tab => `(async () => {
    const p = document.querySelector('.smodal [data-pane="${tab}"]');
    const rows = [...p.querySelectorAll('details[data-sf]')].filter(d => !d.parentElement.closest('details[data-sf]'));
    const was = rows.map(d => d.open), out = [];
    rows.forEach(d => { d.open = false; });
    for (const [i, d] of rows.entries()) {
      d.open = true; await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      const b = d.querySelector(':scope > .sfb') || d, s = d.querySelector(':scope > summary');
      const h = Math.round(b === d ? d.getBoundingClientRect().height - s.getBoundingClientRect().height : b.getBoundingClientRect().height);
      d.open = false;
      const k = d.dataset.sf, sec = k.split('/')[0];
      out.push({k, i, start: was[i], dflt: d.dataset.sfd === '1', why: SF_SHUT[k] || SF_SHUT[sec + '/*'] || '', h,
        icon: s.querySelector(':scope > svg:not(.fcar)')?.innerHTML || '', name: (s.querySelector('h3, h4')?.textContent || '').trim().slice(0, 40)});
    }
    rows.forEach((d, i) => { d.open = was[i]; });
    return JSON.stringify(out);
  })()`;

  const walk = async (o, who, w) => {
    await o.cmd('browsingContext.setViewport', {context: o.ctx, viewport: {width: w, height: 1000}});
    check(await signIn(o, who), `${who} ${w}: the app runs in German`);
    for (const tab of TABS) {
      if (!await open(o, tab)) { console.log(`MEASURE ${who} ${w} ${tab}: no head rows`); continue; }
      const rows = JSON.parse(await o.ev(MEAS(tab)));
      SUM.push(`MEASURE ${who} ${w} ${tab}: ` + rows.map(r => `${r.k.split('/')[1]}=${r.h}${r.start ? '' : '(zu' + (r.why ? ':' + r.why : '') + ')'}`).join(' '));
      const tag = `${who} ${w} ${tab}`;
      // the start: open = its default; the first of the tab open; Company & office: only the first group
      const bad = rows.filter(r => r.start !== (r.i === 0 || !r.why));
      check(!bad.length, `${tag}: open at the start = not in SF_SHUT (first always open) ` + JSON.stringify(bad.map(r => [r.k, r.start, r.why])));
      check(rows.length && rows[0].start, `${tag}: the first section is open ` + (rows[0] && rows[0].k));
      if (tab === 'biz') check(rows.filter(r => r.start).length === 1, `${tag}: Company & office - only the first group open ` + JSON.stringify(rows.filter(r => r.start).map(r => r.k)));
      // the height rule
      const high = rows.filter(r => r.i > 0 && r.start && r.h > MAX);
      check(!high.length, `${tag}: an open section is at most ${MAX} px high (else SF_SHUT 'lang') ` + JSON.stringify(high.map(r => [r.k, r.h])));
      if (w === 412) {
        const low = rows.filter(r => SF_LANG(r) && r.h <= MAX && tab !== 'biz');
        check(!low.length, `${tag}: a section shut as 'lang' is higher than ${MAX} px (else it is open) ` + JSON.stringify(low.map(r => [r.k, r.h])));
      }
      // its own icon
      const seen = new Map(), dup = [];
      for (const r of rows) { if (seen.has(r.icon)) dup.push([seen.get(r.icon), r.k]); else seen.set(r.icon, r.k); }
      check(!dup.length, `${tag}: every section has its own icon ` + JSON.stringify(dup));
    }
  };
  // a 'lang' entry of the section itself (a tab-wide '<tab>/*' is checked by the Company & office line above)
  const SF_LANG = r => r.why === 'lang' && !r.k.endsWith('/*');

  await firefox(async o => {
    await walk(o, 'alice', 412);
    await o.shot('p7555-account-412.png');
    await walk(o, 'alice', 1280);
    // Konto: Profil open, the rare ones closed; by hand wins
    check(await open(o, 'account') && await o.ev(`${ROW('account/account')}?.open === true`), 'Konto: Profil is open');
    await o.shot('p7555-account-1280.png');
    const shut = await o.ev(`JSON.stringify([...document.querySelectorAll('.smodal [data-pane="account"] details[data-sf]')].filter(d => !d.dataset.sfd).map(d => d.dataset.sf))`);
    const k1 = JSON.parse(shut)[0];
    if (k1) {
      await o.ev(`(() => { ${ROW(k1)}.querySelector(':scope > summary').click(); return 1; })()`);
      check(await o.until(`${stored}.then(v => JSON.parse(v).includes('o:${k1}'))`), `by hand: opening the closed ${k1} is stored as o:`);
      await o.ev(`(() => { ${ROW('account/account')}.querySelector(':scope > summary').click(); return 1; })()`);
      check(await o.until(`${stored}.then(v => JSON.parse(v).includes('c:account/account'))`), 'by hand: closing Profil is stored as c:');
      check(await open(o, 'account') && await o.ev(`${ROW(k1)}.open && !${ROW('account/account')}.open`), 'reopened: what was set by hand wins over the start');
      await o.ev(`(() => { ${ROW(k1)}.querySelector(':scope > summary').click(); ${ROW('account/account')}.querySelector(':scope > summary').click(); return 1; })()`);
      check(await o.until(`${stored}.then(v => JSON.parse(v).length === 0)`), 'back to the start: no entry left ' + await o.ev(stored));
    } else check(false, 'Konto: at least one section closed at the start (rare or long)');
  }, false);

  await firefox(async o => {
    await walk(o, 'frida', 412);
    await walk(o, 'frida', 1280);
  }, false);

  for (const l of SUM.filter(x => / 412 /.test(x))) console.log(l);
  console.log(`p7555_settings_open: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
