// 2.1174.0 A UI tests (#6119 company and person, #6120 the contact editor), real layout: own container (start.sh), Firefox.
// kalmido-suite: fresh
// Invented data only (@example.com).
// - #6119 a new contact switched to "Company": first / last name go away, the picture is a building; Ctrl+Enter saves it; the
//   list row and the card show the building; the person with that company links to the company's card, the company's card
//   lists the person under "People" and leads back; the person's event stands under "Events", not again in the history
// - #6120 a wrong e-mail / phone marks its field with a sentence below it when it is left; Save keeps the dialog open and
//   nothing is saved; corrected, Save goes through. A look-alike: the note stands at the top of the dialog and has the focus.
//   Esc in an empty new editor closes it without a question, with typed text it asks (Keep editing / Discard)
// - phone 360 x 740: kind, number and its remove x stand in one line
// freelancer-matrix: n/a (no new route; alice's private address book, no organisation of her own)
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21174_a_contacts_ui', check, shots: 'P21174A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const K = {ctrl: '', enter: '', esc: ''};

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', lang: 'en'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,events,contacts'});
  const BK = await call(CA, 'POST', '/api/books', {name: 'People', org_id: null});
  check(BK.id, 'an address book ' + BK.http);
  const JANA = await call(CA, 'POST', '/api/contacts', {book_id: BK.id, given: 'Jana', family: 'Kruse', org: 'Harbor Works Ltd', emails: [{value: 'jana@example.com', type: ['work']}], phones: [{value: '+49 40 1234', type: ['work']}]});
  check(JANA.id, 'jana ' + JANA.http);
  const EV = await call(CA, 'POST', '/api/events', {title: 'Site visit', start: '2026-09-14T10:00', attendees: [{contact_id: JANA.id}]});
  check(EV.id, 'an event with jana ' + EV.http);
  const onServer = async q => (await call(CA, 'GET', '/api/contacts?limit=50&q=' + encodeURIComponent(q))).items || [];
  const signIn = ev => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);

  await firefox(async ({cmd, ev, ctx, nav, shot, until, idle}) => {
    const keys = (...vs) => cmd('input.performActions', {context: ctx, actions: [{type: 'key', id: 'k', actions: [...vs.map(v => ({type: 'keyDown', value: v})), ...vs.slice().reverse().map(v => ({type: 'keyUp', value: v}))]}]}).then(() => cmd('input.releaseActions', {context: ctx}));
    // a real mouse click in the middle of the element, and the element really is the one under the pointer there
    const click = async sel => {
      const p = await ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e || !e.getClientRects().length) return null; e.scrollIntoView({block: 'nearest'}); const r = e.getBoundingClientRect(); const x = r.left + r.width / 2, y = r.top + r.height / 2;
        const hit = document.elementFromPoint(x, y); return {x, y, hit: !!hit && (hit === e || e.contains(hit))}; })()`);
      if (!p || !p.hit) return false;
      await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm1', parameters: {pointerType: 'mouse'}, actions: [{type: 'pointerMove', x: Math.round(p.x), y: Math.round(p.y)}, {type: 'pointerDown', button: 0}, {type: 'pointerUp', button: 0}]}]});
      await cmd('input.releaseActions', {context: ctx});
      return true;
    };
    // a value typed into a field (the field focused, its value set, the input event as typing gives it)
    const type = (sel, v) => ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return false; e.focus(); e.value = ${JSON.stringify(v)}; e.dispatchEvent(new Event('input', {bubbles: true})); return true; })()`);
    const ED = `document.querySelector('.modal.ctmodal')`;
    const edShown = `!!${ED} && ${ED}.style.display !== 'none' && !!${ED}.getClientRects().length`;
    const shown = sel => `(e => !!e && !!e.getClientRects().length)(document.querySelector(${JSON.stringify(sel)}))`;
    const newEditor = async () => {
      check(await click('#view [data-ct="new"]'), 'the button New contact can be clicked');
      return until(`${edShown} && !!document.querySelector('.modal.ctmodal #ct-given')`);
    };

    // ================= computer 1280 x 900
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 900}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    await signIn(ev);
    await nav(B + '#contacts');
    check(await until(`!!document.querySelector('#view .ctlist .ctrow') && Array.isArray(CT.items)`), 'the contacts view shows jana');

    // ---- #6119 a company through the switch, saved with Ctrl+Enter
    check(await newEditor(), 'the editor opens');
    check(await ev(`!!document.querySelector('.modal .ctkind [data-ctkind="individual"][aria-checked="true"]') && ${shown('.modal #ct-given')}`), '#6119: the editor starts as Person with first name');
    check(await click('.modal .ctkind [data-ctkind="org"]'), '#6119: Company can be clicked');
    check(await until(`!${shown('.modal #ct-given')} && !${shown('.modal #ct-family')} && ${shown('.modal #ct-org')} && document.activeElement?.id === 'ct-org'`), '#6119: Company hides first / last name, the company field has the cursor');
    check(await ev(`!!document.querySelector('.modal #ct-ph .ctav.ctorg svg') && !/[A-Z]/.test(document.querySelector('.modal #ct-ph .ctav').textContent)`), '#6119: the picture is a building, no initials');
    check(await ev(`document.querySelector('.modal select[data-ctk="emails"]')?.value === 'work'`), '#6120: a new company: its e-mail is Work');
    await type('.modal #ct-org', 'Harbor Works Ltd');
    await type('.modal [data-ctm="emails"] input[data-cf="value"]', 'info@example.com');
    await ev(`document.querySelector('.modal #ct-org').focus()`);
    await shot('p21174-a-company-editor.png');
    await keys(K.ctrl, K.enter);
    check(await until(async () => (await onServer('Harbor')).some(x => x.kind === 'org' && x.fn === 'Harbor Works Ltd' && x.email === 'info@example.com')), '#6120: Ctrl+Enter saved the company (kind org, its name, the e-mail)');
    const FIRM = (await onServer('Harbor')).find(x => x.kind === 'org')?.id;
    const firmMail = (await call(CA, 'GET', `/api/contacts/${FIRM}`)).emails?.[0]?.type?.[0];
    check(firmMail === 'work', '#6120: saved as a work e-mail ' + firmMail);
    check(await until(`!document.querySelector('.modal.ctmodal')`), 'the editor closed');
    check(await until(`!!document.querySelector('#view .ctrow[data-ctopen="${FIRM}"] .ctav.ctorg svg')`), '#6119: the list row of the company shows the building');

    // ---- #6119 person -> company -> person
    await nav(B + `#contacts/${JANA.id}`);
    check(await until(`CT.card?.id === ${JANA.id} && !!document.querySelector('#view .ctcard .cthead a.ctporg')`), '#6119: the person\'s company is a link');
    check(await ev(`document.querySelector('#view .ctcard .cthead a.ctporg').getAttribute('href') === '#contacts/${FIRM}' && /Harbor Works Ltd/.test(document.querySelector('#view .ctcard .cthead a.ctporg').textContent)`), '#6119: ... to the company\'s card, named');
    // the event once: in the block Events, not again in the history
    check(await ev(`/Site visit/.test(document.querySelector('#view .ctcard [data-lyk="events"]')?.textContent || '')`), '#6119: the event stands under Events');
    await idle();
    check(await ev(`document.querySelectorAll('#view .ctcard [data-evopen]').length === 1 && !document.querySelector('#view .ctcard .ctkhist [data-evopen]')`), '#6119: the history does not list it again');
    check(await click('#view .ctcard .cthead a.ctporg'), '#6119: the company link can be clicked');
    check(await until(`CT.card?.id === ${FIRM} && !!document.querySelector('#view .ctcard .cthead .ctav.ctorg svg')`), '#6119: the company\'s card opens, with the building');
    check(await until(`/Jana Kruse/.test(document.querySelector('#view .ctcard [data-lyk="people"]')?.textContent || '')`), '#6119: the company\'s card lists jana under People');
    check(await ev(`!document.querySelector('#view .ctcard [data-lyk="tasks"]')`), '#6119: a company without tasks: no block Tasks (0)');
    await shot('p21174-a-company-card.png');
    check(await click(`#view .ctcard [data-lyk="people"] a[href="#contacts/${JANA.id}"]`), '#6119: the person in People can be clicked');
    check(await until(`CT.card?.id === ${JANA.id}`), '#6119: back on jana\'s card');

    // ---- #6120 wrong values at the field, the dialog stays
    check(await click('#view .ctcard [data-ct="edit"]'), 'Edit can be clicked');
    check(await until(`${edShown} && document.querySelector('.modal #ct-given')?.value === 'Jana'`), 'the editor shows jana');
    await type('.modal [data-ctm="emails"] input[data-cf="value"]', 'kurt@@broken');
    // leaving the field checks it (a background window gets no focus events: the focusout as leaving the field gives it)
    const leave = sel => ev(`(() => { document.querySelector(${JSON.stringify(sel)}).dispatchEvent(new FocusEvent('focusout', {bubbles: true})); return 1; })()`);
    await leave('.modal [data-ctm="emails"] input[data-cf="value"]');
    check(await until(`document.querySelector('.modal [data-ctm="emails"] input[data-cf="value"]').getAttribute('aria-invalid') === 'true'`), '#6120: the wrong e-mail is marked when its field is left');
    check(await ev(`(() => { const i = document.querySelector('.modal [data-ctm="emails"] input[data-cf="value"]'), p = document.getElementById(i.getAttribute('aria-describedby')); return !!p && p.getClientRects().length > 0 && /e-mail address like name@example.org/.test(p.textContent); })()`), '#6120: a sentence below it says what is wanted');
    // a background window paints (and restyles) only on demand: each look asks for a picture first
    check(await until(async () => { await cmd('browsingContext.captureScreenshot', {context: ctx}); return (await ev(`(() => { const i = document.querySelector('.modal [data-ctm="emails"] input[data-cf="value"]'), p = document.getElementById(i.getAttribute('aria-describedby')); return !!p && getComputedStyle(i).borderTopColor === getComputedStyle(p).color || [getComputedStyle(i).borderTopColor, getComputedStyle(p).color, getComputedStyle(i).boxShadow].join(' / '); })()`)) === true; }), '#6120: the field itself is marked (its border in the colour of the sentence)');
    await type('.modal [data-ctm="phones"] input[data-cf="value"]', 'call me');
    await leave('.modal [data-ctm="phones"] input[data-cf="value"]');
    check(await until(`document.querySelector('.modal [data-ctm="phones"] input[data-cf="value"]').getAttribute('aria-invalid') === 'true' && /Only digits/.test(document.querySelector('.modal .cterr:not([id="' + document.querySelector('.modal [data-ctm="emails"] input[data-cf="value"]').getAttribute('aria-describedby') + '"])')?.textContent || '')`), '#6120: the wrong phone too');
    await shot('p21174-a-editor-errors.png');
    check(await click('.modal [data-ctm2="save"]'), 'Save can be clicked');
    check(await until(`document.activeElement?.getAttribute('aria-invalid') === 'true'`), '#6120: Save puts the cursor into the first wrong field');
    check(await ev(edShown), '#6120: the dialog stays open');
    const j1 = await call(CA, 'GET', `/api/contacts/${JANA.id}`);
    check(j1.emails[0].value === 'jana@example.com' && j1.phones[0].value === '+49 40 1234', '#6120: nothing was saved');
    await type('.modal [data-ctm="emails"] input[data-cf="value"]', 'jana.kruse@example.com');
    check(await ev(`!document.querySelector('.modal [data-ctm="emails"] input[data-cf="value"]').hasAttribute('aria-invalid')`), '#6120: a corrected e-mail is no longer marked');
    await type('.modal [data-ctm="phones"] input[data-cf="value"]', '+49 (0)40 1234-5');
    check(await click('.modal [data-ctm2="save"]'), 'Save again');
    check(await until(async () => { const j = await call(CA, 'GET', `/api/contacts/${JANA.id}`); return j.emails[0].value === 'jana.kruse@example.com' && j.phones[0].value === '+49 (0)40 1234-5'; }), '#6120: corrected, it saves');
    check(await until(`!document.querySelector('.modal.ctmodal')`), 'the editor closed');

    // ---- review 2.1174.0 (#6120): a number an import brought ("ext. 12") never blocks saving another field of the contact
    {
      const fd = new FormData();
      fd.append('file', new Blob(['BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Olga Old\r\nN:Old;Olga;;;\r\nTEL;TYPE=WORK:ext. 12\r\nEND:VCARD\r\n'], {type: 'text/vcard'}), 'olga.vcf');
      const ri = await fetch(B + `api/books/${BK.id}/import`, {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: CA}, body: fd});
      const rj = await ri.json().catch(() => ({}));
      check(ri.ok, 'review: a vCard with an old number imports ' + ri.status + ' ' + JSON.stringify(rj).slice(0, 200));
      let OLGA = null;
      check(await until(async () => { const o = (await onServer('Olga')).find(x => x.fn === 'Olga Old'); OLGA = o && await call(CA, 'GET', `/api/contacts/${o.id}`); return !!OLGA?.id; }), 'review: olga is there');
      check((OLGA?.phones || [])[0]?.value === 'ext. 12', 'review: the import kept her number as it is');
      await nav(B + `#contacts/${OLGA?.id}`);
      check(await until(`CT.card?.id === ${OLGA?.id}`), 'review: olga\'s card opens');
      check(await click('#view .ctcard [data-ct="edit"]'), 'review: Edit can be clicked');
      check(await until(`${edShown} && document.querySelector('.modal #ct-given')?.value === 'Olga'`), 'review: the editor shows olga');
      await type('.modal #ct-family', 'Older');
      check(await click('.modal [data-ctm2="save"]'), 'review: Save');
      check(await until(async () => { const j = await call(CA, 'GET', `/api/contacts/${OLGA?.id}`); return j.family === 'Older' && j.phones?.[0]?.value === 'ext. 12'; }), 'review: #6120 the name saves, the old number stays (no mark, no refusal)');
      check(await until(`!document.querySelector('.modal.ctmodal')`), 'review: the editor closed');
    }

    // ---- #6120 a look-alike: the note at the top, the eye goes there
    check(await newEditor(), 'a new editor');
    await type('.modal #ct-given', 'Jana'); await type('.modal #ct-family', 'Kruse');
    check(await click('.modal [data-ctm2="save"]'), 'Save');
    check(await until(`!!document.querySelector('.modal .ctxdup')`), '#6120: the look-alike note shows');
    const dupV = await ev(`(() => { const d = document.querySelector('.modal .ctxdup'), h = document.querySelector('.modal .lhdr'), c = d.closest('.card').getBoundingClientRect(), r = d.getBoundingClientRect();
      const v = {next: h.nextElementSibling === d, focus: document.activeElement === d, top: Math.round(r.top), ctop: Math.round(c.top), bot: Math.round(r.bottom), cbot: Math.round(c.bottom), htop: Math.round(h.getBoundingClientRect().top), jana: /Jana Kruse/.test(d.textContent), ae: (a => a ? a.tagName + '.' + a.className + '#' + a.id : '-')(document.activeElement)};
      return v.next && v.focus && v.top >= v.ctop - 1 && v.htop >= v.ctop - 1 && v.bot <= v.cbot + 1 && v.jana ? true : JSON.stringify(v); })()`);
    check(dupV === true, '#6120: it stands at the top of the dialog below its title, in sight, with the focus, naming jana ' + dupV);
    await shot('p21174-a-duplicate.png');
    // ---- #6120 Esc with typed text asks
    await keys(K.esc);
    check(await until(`[...document.querySelectorAll('.modal')].some(m => /Discard changes\\?/.test(m.textContent))`), '#6120: Esc with typed text asks first');
    check(await ev(`(() => { const b = [...document.querySelectorAll('.modal button')].find(x => x.textContent.trim() === 'Keep editing'); if (!b) return false; b.dataset.t6120 = '1'; return true; })()`) && await click('.modal button[data-t6120="1"]'), 'Keep editing can be clicked');
    check(await until(`${edShown} && !/Discard changes\\?/.test(document.body.textContent) && document.querySelector('.modal #ct-given')?.value === 'Jana'`), '#6120: Keep editing: the editor stays with its text');
    await keys(K.esc);
    check(await until(`!![...document.querySelectorAll('.modal button')].find(x => x.textContent.trim() === 'Discard')`), 'the question again');
    await ev(`[...document.querySelectorAll('.modal button')].find(x => x.textContent.trim() === 'Discard').click()`);
    check(await until(`!document.querySelector('.modal')`), '#6120: Discard closes it');
    check((await onServer('Kruse')).length === 1, '#6120: no second jana');
    // ---- #6120 Esc in an empty editor closes without a question
    check(await newEditor(), 'an empty new editor');
    await keys(K.esc);
    check(await until(`!document.querySelector('.modal')`), '#6120: Esc in an empty editor closes it without a question');

    // ================= phone 360 x 740: the phone row with its x in one line
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 360, height: 740}});
    await nav(B + '#contacts');
    check(await until(`Array.isArray(CT.items) && !!document.querySelector('#view .ctlist')`), 'phone: the contacts view');
    await ev(`ctEditor(null).then(() => 1)`);
    check(await until(`${edShown} && !!document.querySelector('.modal [data-ctm="phones"] .ctmi') && !document.querySelector('.modal').getAnimations({subtree: true}).length`), 'phone: the editor opens (and stands still)');
    await type('.modal [data-ctm="phones"] input[data-cf="value"]', '+49 171 1234567');
    const row = await ev(`(() => { const m = document.querySelector('.modal'), card = m.querySelector('.card').getBoundingClientRect();
      return ['phones', 'emails'].map(k => { const r = m.querySelector('[data-ctm="' + k + '"] .ctmi'); const xs = [r.querySelector('select'), r.querySelector('input'), r.querySelector('[data-ctrm]')].map(e => e.getBoundingClientRect());
        return {k, mid: xs.map(x => Math.round(x.top + x.height / 2)), right: Math.round(xs[2].right), card: Math.round(card.right), inW: Math.round(xs[1].width)}; }); })()`);
    console.log('phone rows', JSON.stringify(row));
    for (const r of row || []) {
      check(Math.max(...r.mid) - Math.min(...r.mid) <= 4, `phone: ${r.k}: kind, field and x in one line ${JSON.stringify(r.mid)}`);
      check(r.right <= r.card && r.inW >= 100, `phone: ${r.k}: the x inside the dialog, the field still wide enough (${r.inW} px)`);
    }
    await ev(`document.querySelector('.modal [data-ctm="phones"] .ctmi').scrollIntoView({block: 'center'})`);
    await shot('p21174-a-phone-editor.png');
  });

  console.log(`p21174_a_contacts_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
