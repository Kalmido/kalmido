// 2.1177.0 part B UI test (#6114): uploading into the file store / the documents - one message, checked before sending, the drop frame
// kalmido-suite: fresh
// Own container (start.sh; P21177B_NOSTART=1 / KMT_NOSTART=1: a running server), jsdom for the flows, Firefox for the drop frame
// as a picture. Invented names and files only.
// freelancer-matrix: files of a person without an organisation (frida: her private space)
// #6114 - the cause of the walk-through's open point: the server refuses a form with an empty file as a whole (one 400, nothing
//         stored), so two empty .mp4 / .wav took a good file with them. Now an upload with a good file, two empty ones (.mp4 /
//         .wav) and one above the limit: the good one goes up, ONE message "1 file uploaded · 3 not uploaded" with Undo, no
//         "Uploading … files" toast besides it, a list names the three and why (empty / larger than); the empty ones never reach
//         the server; Undo takes the file back. A new version: "… as a new version" with Undo, Undo brings the old content back.
//         The form asks for the progress bar at any size (upWanted / upBar); a small upload can be cancelled (Cancel in its bar).
//         Files dragged over the list: the frame says "Drop here - lands in “<folder>”" - over a folder row its name.
//         Documents: a .docx and an empty PDF stay out (the button's kinds, a drop too) with the list, 52 files go in portions
//         (all 52 added, none cut at 50).
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21177_b_files_ui', check, shots: 'P21177B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21177B_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const FEATS = 'files,docs';
// a drag of files from the computer onto el (jsdom has no DataTransfer: the event carries a plain stand-in)
const dragFiles = (w, el, type = 'dragover', files = []) => { const e = new w.Event(type, {bubbles: true, cancelable: true}); Object.defineProperty(e, 'dataTransfer', {value: {types: ['Files'], files, dropEffect: 'none', getData: () => ''}}); el.dispatchEvent(e); return e; };
// every text the toast showed (the check "no second message" needs the ones that were replaced)
const watchToasts = w => w.eval(`(() => { window.__toasts = []; const t = document.querySelector('#toast'); new MutationObserver(() => { if (!t.classList.contains('hidden')) window.__toasts.push(t.textContent); }).observe(t, {childList: true, subtree: true, characterData: true, attributes: true}); return 1; })()`);
const txt = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  const st0 = await call(CA, 'GET', '/api/state');
  const feats = [...new Set([...(st0.settings?.features || '').split(','), ...FEATS.split(',')])].filter(Boolean).join(',');
  const u = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(u.http < 300, `setup: frida ${u.http}`);
  const FK = await login('frida');
  await call(FK, 'PATCH', '/api/settings', {tour: 'done', lang: 'en', features: feats, workspace: 'private'});
  check(((await call(FK, 'GET', '/api/state')).me?.workspaces || []).length === 0, 'setup: frida has no organisation');
  const items = async (ck, q) => (await call(ck, 'GET', '/api/files?' + q)).items || [];
  const content = async (ck, id) => (await fetch(B + `api/files/nodes/${id}/content`, {headers: {'X-Requested-With': 'kalmido', Cookie: ck}})).text();
  let w, d;

  // ================= the cause: a form with an empty file is refused as a whole by the server (the client keeps them out)
  {
    const fd = new FormData(); fd.append('file', new Blob(['gut']), 'probe-gut.txt'); fd.append('file', new Blob([]), 'probe-leer.mp4'); fd.append('space', 'private');
    const r = await fetch(B + 'api/files/upload', {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: FK}, body: fd});
    check(r.status === 400 && !(await items(FK, 'space=private')).some(x => /^probe-/.test(x.name)), 'server: good + empty .mp4 in one form = 400, nothing stored (why the client checks first) ' + r.status);
  }

  // ================= #6114 the upload: checked before sending, ONE message, the list of what stayed out
  const BOX = (await call(FK, 'POST', '/api/files/folders', {name: 'Drehorte', space: 'private'})).id;
  check(BOX, 'setup: frida\'s folder Drehorte');
  w = await boot({user: 'frida', hash: 'ablage', ls: {'tasks.abSpace': '"private"'}}); d = w.document;
  check(await until(() => d.querySelector(`#view .abrow[data-abid="${BOX}"]`)), 'frida: her private space shows the folder');
  check(w.eval(`(() => { const fd = new FormData(); fd.append('file', new File(['x'], 'x.txt')); const a = upWanted(fd); fd.upBar = true; return !a && upWanted(fd); })()`), 'a tiny form gets the progress bar when it asks for it (upBar)');
  watchToasts(w);
  w.eval('S.maxFileMb = 1');  // the limit of this check (the server's own stays)
  await w.eval(`ab_upload([new File(['Hallo Welt'], 'motiv.txt', {type: 'text/plain'}), new File([], 'leer.mp4', {type: 'video/mp4'}), new File([], 'leer.wav', {type: 'audio/wav'}),
    new File([new Uint8Array(1200 * 1024)], 'gross.bin')], null)`);
  const out = d.querySelector('#upbars .upout');
  check(out && /3 files were not uploaded/.test(txt(out)), 'the list says 3 files stayed out: ' + txt(out));
  check(out && /leer\.mp4 The file is empty/.test(txt(out)) && /leer\.wav The file is empty/.test(txt(out)), 'the empty .mp4 / .wav are named with "The file is empty"');
  check(out && /gross\.bin Larger than 1 MB/.test(txt(out)), 'the big one is named with "Larger than 1 MB"');
  check(await until(() => /1 file uploaded · 3 not uploaded/.test(txt(d.querySelector('#toast')))), 'ONE message at the end: ' + txt(d.querySelector('#toast')));
  check(/Undo/.test(d.querySelector('#toast button')?.textContent || ''), 'the message offers Undo');
  check(!w.__toasts.some(t => /Uploading \d+ file/.test(t)), 'no "Uploading … files" toast besides the bar: ' + JSON.stringify(w.__toasts));
  check(await until(() => [...d.querySelectorAll('#view .abrow .abname')].some(n => n.textContent === 'motiv.txt')), 'the good file is in the list');
  const names = (await items(FK, 'space=private')).map(x => x.name);
  check(names.includes('motiv.txt') && !names.some(n => /^leer\./.test(n) || n === 'gross.bin'), 'the server got the good file only: ' + names.join());
  const MOT = (await items(FK, 'space=private')).find(x => x.name === 'motiv.txt')?.id;
  d.querySelector('#toast button').click();
  check(await until(async () => (await items(FK, 'space=trash')).some(x => x.id === MOT)), 'Undo takes the upload back (the file in the trash)');
  check(await until(() => ![...d.querySelectorAll('#view .abrow .abname')].some(n => n.textContent === 'motiv.txt')), 'its row leaves the list');
  d.querySelector('#upbars .upout .upoutx').click();
  check(!d.querySelector('#upbars .upout'), 'the list closes with its x');

  // a new version: the message says so and Undo brings the version before back on top
  await w.eval(`ab_upload([new File(['Drehplan Fassung 1'], 'drehplan.txt', {type: 'text/plain'})], null)`);
  const PLAN = await until(async () => (await items(FK, 'space=private')).find(x => x.name === 'drehplan.txt')?.id);
  check(PLAN, 'drehplan.txt uploaded');
  await until(() => [...d.querySelectorAll('#view .abrow .abname')].some(n => n.textContent === 'drehplan.txt'));
  await w.eval(`ab_upload([new File(['Drehplan Fassung 2'], 'drehplan.txt', {type: 'text/plain'})], null)`);
  check(await until(() => /1 uploaded, 1 as a new version/.test(txt(d.querySelector('#toast'))) && /Undo/.test(d.querySelector('#toast button')?.textContent || '')), 'a new version: its message with Undo ' + txt(d.querySelector('#toast')));
  check(await content(FK, PLAN) === 'Drehplan Fassung 2', 'the new version is the content now');
  d.querySelector('#toast button').click();
  check(await until(async () => await content(FK, PLAN) === 'Drehplan Fassung 1'), 'Undo: the version before is on top again');

  // review (2.1177.0): two files of one upload with the same name = one node with two versions: ONE file in the message, Undo
  // takes the new node to the trash (before: "2 uploaded, 2 as a new version", Undo restored version 1 twice)
  await w.eval(`ab_upload([new File(['eins'], 'doppelt.txt', {type: 'text/plain'}), new File(['zwei'], 'doppelt.txt', {type: 'text/plain'})], null)`);
  check(await until(() => /^1 file uploaded/.test(txt(d.querySelector('#toast')))), 'same name twice in one upload: one file in the message ' + txt(d.querySelector('#toast')));
  const DOP = (await items(FK, 'space=private')).find(x => x.name === 'doppelt.txt')?.id;
  d.querySelector('#toast button').click();
  check(DOP && await until(async () => (await items(FK, 'space=trash')).some(x => x.id === DOP)), 'same name twice: Undo puts the new file in the trash');
  // review: a portion the server refuses (400: one bad file) is listed and the next one goes on; Cancel / offline / rights stop
  check(w.eval(`ab_upGoOn({status: 400}) && !ab_upGoOn({status: 403}) && !ab_upGoOn({status: 400, cancelled: true}) && !ab_upGoOn(new Error('offline'))`), 'a refused portion does not stop the next ones, Cancel and rights do');

  // a small upload (below 1 MB): its bar shows while the server works, WITHOUT Cancel (review 2.1177.0: the body is out at once,
  // a Cancel could only stop the waiting and call files cancelled that the server stores anyway); the answer is held here
  const held = w.eval(`(() => { const f0 = window.fetch; window.__f0 = f0; let go; window.__go = new Promise(r => { go = r; }); window.__goNow = go;
    window.fetch = (u, o) => o?.body instanceof FormData ? window.__go.then(() => f0(u, o)) : f0(u, o);
    window.__up = ab_upload([new File(['Notiz'], 'notiz-a.txt', {type: 'text/plain'}), new File(['Notiz'], 'notiz-b.txt', {type: 'text/plain'})], null); return 1; })()`);
  check(held && await until(() => d.querySelector('#upbars .upbar:not(.upout)')), 'a small upload shows its bar');
  const bar = d.querySelector('#upbars .upbar:not(.upout)');
  check(bar && !bar.querySelector('button') && /2 files/.test(txt(bar)), 'the small upload\'s bar names the files and offers no Cancel: ' + txt(bar));
  w.eval('window.__goNow()'); await w.eval('window.__up'); w.eval('window.fetch = window.__f0');
  check(await until(() => !d.querySelector('#upbars .upbar:not(.upout)')), 'the bar leaves with the answer');
  check(await until(async () => (await items(FK, 'space=private')).filter(x => /^notiz-/.test(x.name)).length === 2), 'both small files are stored');
  d.querySelector('#upbars .upout .upoutx')?.click();

  // the drop frame says where the files land
  const view = d.querySelector('#view .abview');
  const e1 = dragFiles(w, d.querySelector('#view .abview .abmain'));
  check(e1.defaultPrevented && view.classList.contains('abdrop') && view.dataset.abdroptxt === 'Drop here - lands in “Private”', 'over the list: the frame "Drop here - lands in “Private”" ' + view.dataset.abdroptxt);
  dragFiles(w, d.querySelector(`#view .abrow[data-abid="${BOX}"] [data-abdrop]`));
  check(view.dataset.abdroptxt === 'Drop here - lands in “Drehorte”', 'over a folder row: its name ' + view.dataset.abdroptxt);
  const cssOk = w.eval(`[...document.styleSheets].some(s => { try { return [...s.cssRules].some(r => /abdroptxt/.test(r.selectorText || '')); } catch { return false; } })`);
  check(cssOk, 'the frame\'s text is drawn by the stylesheet (::after of data-abdroptxt)');
  w.close();

  // ================= #6114 the documents: the same check (the button's kinds, a drop too), portions instead of cutting at 50
  w = await boot({user: 'frida', hash: 'docs'}); d = w.document;
  check(await until(() => d.querySelector('#dc-file'), 80), 'frida: the documents are drawn with "Add documents"');
  check(d.querySelector('#dc-file').getAttribute('accept') === w.eval('DC_ACCEPT'), 'the button offers the kinds of DC_ACCEPT');
  watchToasts(w);
  await w.eval(`dc_upload([new File(['Angebot Drehtag'], 'angebot.txt', {type: 'text/plain'}), new File(['PK'], 'vertrag.docx', {type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}), new File([], 'leer.pdf', {type: 'application/pdf'})])`);
  const dout = d.querySelector('#upbars .upout');
  check(dout && /vertrag\.docx This kind of file cannot be added here/.test(txt(dout)) && /leer\.pdf The file is empty/.test(txt(dout)), 'documents: the .docx and the empty PDF are named and why: ' + txt(dout));
  check(await until(() => /1 document added · 2 not uploaded/.test(txt(d.querySelector('#toast')))), 'documents: ONE message with the count: ' + txt(d.querySelector('#toast')));
  check(!w.__toasts.some(t => /Uploading/.test(t)), 'documents: no second message');
  // a drop takes the same kinds as the button
  dragFiles(w, d.querySelector('.dc-view'), 'drop', [new w.File(['PK'], 'liste.xlsx', {type: 'application/vnd.ms-excel'})]);
  // 2.1247.0 (#6173): each upload its own list - the drop's list stands beside the one before (no longer replaces it)
  check(await until(() => [...d.querySelectorAll('#upbars .upout')].some(x => /liste\.xlsx This kind of file cannot be added here/.test(txt(x)))), 'a drop: the same kinds as the button (the .xlsx stays out, named)');
  const many = await w.eval(`dc_upload(Array.from({length: 52}, (_, i) => new File(['Beleg Nummer ' + i], 'beleg-' + i + '.txt', {type: 'text/plain'})))`);
  check(Array.isArray(many) && many.length === 52, '52 documents at once: all 52 added (portions of 50, nothing cut) ' + (many && many.length));
  w.close();

  // ================= Firefox: the drop frame as a picture
  await firefox(async o => {
    const {cmd, ev, ctx, shot} = o;
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 860}});
    await o.nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); localStorage.setItem('tasks.abSpace', '"private"'); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'frida', password: 'password123'})}).then(r => r.status)`) === 200, 'ff: login');
    const wait = async (js, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(js).catch(() => false)) return true; await sleep(250); } return false; };
    await o.nav(B + '#ablage');
    check(await wait(`!!document.querySelector('#view .abrow[data-abid="${BOX}"]')`), 'ff: the list shows Drehorte');
    await ev(`(() => { const dt = new DataTransfer(); dt.items.add(new File(['x'], 'neu.txt', {type: 'text/plain'})); document.querySelector('#view .abview .abmain').dispatchEvent(new DragEvent('dragover', {bubbles: true, cancelable: true, dataTransfer: dt})); return 1; })()`);
    check(await wait(`getComputedStyle(document.querySelector('#view .abview.abdrop'), '::after').content.includes('Drop here - lands in')`), 'ff: the frame shows "Drop here - lands in …"');
    await shot('p21177b-drop-frame.png');
  });

  console.log(`p21177_b_files_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: exception', e); process.exit(1); });
