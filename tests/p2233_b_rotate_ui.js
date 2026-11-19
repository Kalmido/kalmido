// 2.233.0 B (#3189) UI tests, own container (start.sh): the runtime section "Interim summary" (Zwischenstand).
// jsdom: the admin's agent dialog shows it below "Runtime" with session size, messages, minutes of pause and the existing
// nightly restart moved in as "Daily summary"; every field saves at once (no Save needed), a value out of range is refused in
// the dialog and changes nothing. A person without an organisation (freelancer-matrix: agents) finds it in the permissions
// dialog of the own agent, with its own daily-summary time picker, saved at once. German labels.
// Firefox at 360 and 412 px (touch): the permissions dialog with the section fits (no horizontal overflow, fields inside the
// viewport, at least 40 px high). Screenshots with P2233B_SHOTS=<dir>.
// 2.974.0 (#5668): the model per run - in the admin's "Runtime" a switch below Model shows two model fields (hidden while
// off), Save stores them, the dialog opens with them again; the owner of a personal agent (freelancer) has a section "Model"
// in the permissions dialog with the same switch, saved at once. German: "Modell je Lauf wählen".
// 2.992.0 (#5684): a third model "For reviews" (admin: saved with Save; owner: at once) and below the models the usage per kind
// of the last 7 days (runs, tokens, the costs only when reported). The chat header of the own agent shows "runs with <model of
// the last run>" only while the switch is on; a tap opens the section Model as a dialog of its own (its content: the three
// fields and the usage), switching it off there removes the header's line at once. German: "läuft mit", "Für Prüfungen".
// 2.1394.0 (#7031): the section "Jobs on its computer" (model and effort for build / review jobs) in the owner's dialog, saved at once.
// #7368: every model field is a real choice (Agent default, Fable, Opus, Sonnet, Haiku, Other …): a listed model saves like a
// typed one, "Other …" shows the free field (a new name saves at once, an invalid one comes back, "Fable" typed becomes the
// choice fable), back to a listed model hides it; the effort beside each model (admin: with Save, owner: at once).
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const {idle} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p2233_b_rotate_ui', check, shots: 'P2233B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});  // 2.358.0 (#3286): the shared wait of tests/boot.js (default at least 15 s); an explicit n/ms keeps its window
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const change = (w, el, v) => { el.value = v; el.dispatchEvent(new w.Event('change', {bubbles: true})); };
const lastModal = d => [...d.querySelectorAll('.modal')].pop();

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  await call('PATCH', '/api/settings', {features: 'agents,comments,collab', lang: 'en', tour: 'done'});
  const ag = await call('POST', '/api/admin/agents', {scopes: ['read', 'comments'], username: 'claude', display_name: 'Claude'});
  const adm = async id => (await call('GET', '/api/admin/agents')).agents.find(a => a.id === id);

  // ================= the admin's agent dialog
  let w = await boot({user: 'alice', hash: 'today'}), d = w.document;
  w.eval(`agModal(${JSON.stringify(await adm(ag.id))}, null)`);
  let md = await until(() => d.querySelector('#ag-model')?.closest('.modal'));
  const sec = md && md.querySelector('.agzsec');
  check(sec && /Interim summary/.test(sec.querySelector('h4')?.textContent || ''), 'agent dialog: section Interim summary');
  check(sec && sec.compareDocumentPosition(md.querySelector('#ag-rt-h')) & w.Node.DOCUMENT_POSITION_PRECEDING, 'below the section Runtime');
  check(sec && sec.querySelector('#agz-size').value === 'medium' && sec.querySelector('#agz-runs').value === '60' && sec.querySelector('#agz-idle').value === '45',
    'defaults: medium, 60 messages, 45 minutes');
  check(sec && sec.querySelector('#ag-nr') && /Daily summary/.test(sec.querySelector('#ag-nr').closest('.row').textContent) && md.querySelectorAll('#ag-nr').length === 1,
    'the nightly restart sits in the section as "Daily summary" (one field)');
  check(sec && /forget details/.test(sec.textContent), 'the explanation: saves cost, can forget details');
  change(w, sec.querySelector('#agz-runs'), '120');
  check(await until(async () => (await adm(ag.id)).runtime.rotate_runs === 120), 'messages saved at once (no Save)');
  change(w, sec.querySelector('#agz-size'), 'large');
  check(await until(async () => (await adm(ag.id)).runtime.rotate_size === 'large'), 'size saved at once');
  change(w, sec.querySelector('#agz-idle'), '0');
  check(await until(async () => (await adm(ag.id)).runtime.rotate_idle_min === 0), 'pause 0 = never, saved');
  change(w, sec.querySelector('#agz-runs'), '5'); await idle(w);
  check(sec.querySelector('#agz-runs').value === '120' && /10 to 500/.test(d.querySelector('#toast')?.textContent || ''), 'messages 5: refused in the dialog, the old value back');
  change(w, sec.querySelector('#agz-idle'), '3'); await idle(w);
  check(sec.querySelector('#agz-idle').value === '0' && (await adm(ag.id)).runtime.rotate_runs === 120 && (await adm(ag.id)).runtime.rotate_idle_min === 0, 'pause 3: refused, nothing changed');
  w.eval(`dpSet(document.querySelector('#ag-nr'), '04:30')`);
  check(await until(async () => (await adm(ag.id)).runtime.nightly_reset === '04:30'), 'daily summary time saved at once');
  click(w, md.querySelector('[data-m="close"]'));
  w.close();

  // ================= 2.974.0 (#5668): the model per run in the admin's dialog (saved with Save)
  w = await boot({user: 'alice', hash: 'today'}); d = w.document;
  w.eval(`agModal(${JSON.stringify(await adm(ag.id))}, null)`);
  md = await until(() => d.querySelector('#ag-model')?.closest('.modal'));
  const msw = md.querySelector('#ag-msplit'), msr = () => [...md.querySelectorAll('.ag-msr')];
  check(msw && !msw.checked && msw.closest('.row').previousElementSibling?.querySelector('#ag-model') && /Select the model per run/.test(msw.closest('.row').textContent),
    '#5668: the switch "Select the model per run" right below Model, off');
  check(msr().length === 5 && msr().every(x => x.hidden), '#5668 / #5684: the three model fields, the hint and the usage are hidden while it is off');
  msw.checked = true; msw.dispatchEvent(new w.Event('change', {bubbles: true}));
  check(msr().every(x => !x.hidden) && /For your messages and decisions/.test(md.textContent) && /For routine/.test(md.textContent) && /When in doubt the first/.test(md.textContent),
    '#5668: on = both fields and the explanation show');
  check(/For reviews/.test(md.textContent) && md.querySelector('#ag-mrev-sel')?.options[0].textContent === 'Like messages and decisions'
    && md.querySelector('#ag-mrev').closest('.row').previousElementSibling?.querySelector('#ag-mdec'), '#5684: the review model between the two, empty = like the first');
  check(await until(() => /Last 7 days/.test(md.querySelector('.agmu')?.textContent || '') && /No usage reported yet/.test(md.querySelector('.agmu').textContent)),
    '#5684: the usage per kind below the models (nothing reported yet)');
  // #7368: the choice (one list with Fable) and the effort beside each model, stored with Save like the models
  change(w, md.querySelector('#ag-mdec-sel'), 'opus'); change(w, md.querySelector('#ag-mrou-sel'), 'sonnet'); change(w, md.querySelector('#ag-mrev-sel'), 'fable');
  check(md.querySelector('#ag-mdec').value === 'opus' && md.querySelector('#ag-mdec').hidden && md.querySelector('#ag-mrev').value === 'fable', '#7368: a listed model goes into the field, no free field');
  check([...md.querySelectorAll('#ag-mdec-eff option')].map(o => o.value).join() === ',low,medium,high,xhigh,max' && md.querySelector('#ag-mrev-eff').options[0].textContent === 'Like messages and decisions',
    '#7368: the effort beside the models: default, low ... max; the review effort empty = like the first');
  change(w, md.querySelector('#ag-meff'), 'high'); change(w, md.querySelector('#ag-mrou-eff'), 'low');
  click(w, md.querySelector('[data-m="ok"]'));
  check(await until(async () => { const r = (await adm(ag.id)).runtime; return r.model_split === true && r.model_decide === 'opus' && r.model_routine === 'sonnet' && r.model_review === 'fable'
    && r.effort === 'high' && r.effort_routine === 'low' && r.effort_decide === '' && r.effort_review === ''; }),
    '#5668 / #5684 / #7368: Save stores the switch, the three models and the efforts');
  await until(() => !md.isConnected);
  w.eval(`agModal(${JSON.stringify(await adm(ag.id))}, null)`);
  md = await until(() => d.querySelector('#ag-model')?.closest('.modal'));
  check(md.querySelector('#ag-msplit').checked && md.querySelector('#ag-mdec-sel').value === 'opus' && md.querySelector('#ag-mrou').value === 'sonnet' && md.querySelector('#ag-mrev-sel').value === 'fable'
    && md.querySelector('#ag-meff').value === 'high' && md.querySelector('#ag-mrou-eff').value === 'low'
    && [...md.querySelectorAll('.ag-msr')].every(x => !x.hidden), '#5668: the dialog opens again with the switch on and both models');
  click(w, md.querySelector('[data-m="close"]'));
  w.close();

  // ================= German
  await call('PATCH', '/api/settings', {lang: 'de'});
  w = await boot({user: 'alice', hash: 'today'}); d = w.document;
  w.eval(`agModal(${JSON.stringify(await adm(ag.id))}, null)`);
  md = await until(() => d.querySelector('#ag-model')?.closest('.modal'));
  const sd = md.querySelector('.agzsec');
  check(sd && /Zwischenstand/.test(sd.textContent) && /Sitzungsgröße/.test(sd.textContent) && /Tägliche Zusammenfassung/.test(sd.textContent)
    && sd.querySelector('#agz-size').value === 'large', 'German: Zwischenstand, Sitzungsgröße, Tägliche Zusammenfassung');
  check(/Modell je Lauf wählen/.test(md.textContent) && /Für Routine/.test(md.textContent), '#5668 German: Modell je Lauf wählen, Für Routine');
  w.close();
  await call('PATCH', '/api/settings', {lang: 'en'});

  // ================= a person without an organisation: the own agent's permissions dialog
  await call('PUT', '/api/admin/agent-policy', {user_agents: true, max_per_user: 2});
  const fr = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fr.status < 300, 'a freelancer ' + fr.status);
  const CF = await login('frida');
  await call('PATCH', '/api/settings', {features: 'agents,comments', lang: 'en', tour: 'done'}, CF);
  check(!((await call('GET', '/api/state', null, CF)).me.workspaces || []).length, 'frida has no organisation');
  const FBR = await call('POST', '/api/my/agents', {username: 'fridabot', display_name: 'Fridabot'}, CF), FB = FBR.id;
  const asAgent = (method, url, body) => fetch(B + 'api/v1/' + url, {method, headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + FBR.token}, body: JSON.stringify(body)}).then(r => r.status);  // 2.992.0 (#5684)
  const mine = async () => (await call('GET', '/api/my/agents', null, CF)).agents.find(a => a.id === FB);
  w = await boot({user: 'frida', hash: 'today'}); d = w.document;
  w.eval(`settingsModal('ai')`); await sleep(500);
  await w.eval(`aiSubShow(document.querySelector('.smodal'), 'setup', false)`);
  const prow = await until(() => d.querySelector(`#s-myown [data-myag="${FB}"]`));
  click(w, prow.querySelector('[data-myag-act="perm"]'));
  md = await until(() => lastModal(d)?.querySelector('.agzsec') && lastModal(d));
  const ps = md && md.querySelector('.agzsec');
  check(ps && ps.querySelector('#agz-nr') && /Daily summary/.test(ps.textContent) && ps.compareDocumentPosition(md.querySelector('.foot')) & w.Node.DOCUMENT_POSITION_FOLLOWING,
    'freelancer: the section in the permissions dialog, above its buttons, with its own time picker');
  change(w, ps.querySelector('#agz-runs'), '30');
  check(await until(async () => (await mine()).runtime.rotate_runs === 30), 'freelancer: messages saved at once');
  w.eval(`dpSet(document.querySelector('#agz-nr'), '05:15')`);
  check(await until(async () => (await mine()).runtime.nightly_reset === '05:15'), 'freelancer: daily summary time saved at once');
  // 2.974.0 (#5668): the section "Model" of the own agent: switch on = both fields show, each saved at once
  const ms = md.querySelector('.agzmod');
  check(ms && /Model/.test(ms.querySelector('h4')?.textContent || '') && ms.querySelector('#agm-model') && ms.querySelector('#agm-split') && !ms.querySelector('#agm-split').checked
    && [...ms.querySelectorAll('.agm-r')].every(x => x.hidden), '#5668 freelancer: section Model with the field and the switch (off, fields hidden)');
  const fsw = ms.querySelector('#agm-split'); fsw.checked = true; fsw.dispatchEvent(new w.Event('change', {bubbles: true}));
  check(await until(async () => (await mine()).runtime.model_split === true) && [...ms.querySelectorAll('.agm-r')].every(x => !x.hidden), '#5668 freelancer: switch on, saved at once, fields show');
  change(w, ms.querySelector('#agm-dec-sel'), 'opus');
  check(await until(async () => (await mine()).runtime.model_decide === 'opus') && ms.querySelector('#agm-dec').value === 'opus', '#5668 freelancer: model for own messages saved');
  change(w, ms.querySelector('#agm-rou-sel'), 'sonnet');
  check(await until(async () => (await mine()).runtime.model_routine === 'sonnet'), '#5668 freelancer: model for routine saved');
  // #7368: "Other …" shows the free field; a new name saves at once; an invalid one is refused and the old value comes back;
  // a typed short name in any case becomes the choice again; back to a listed model hides the field
  const rsel = ms.querySelector('#agm-rou-sel'), rin = ms.querySelector('#agm-rou');
  check(rin.hidden && [...rsel.options].map(o => o.textContent).join('|') === 'Agent default|Fable|Opus|Sonnet|Haiku|Other …', '#7368 freelancer: the choice with Fable, no free field');
  change(w, rsel, '__other');
  check(!rin.hidden && rin.value === 'sonnet' && (await mine()).runtime.model_routine === 'sonnet', '#7368 freelancer: Other … shows the free field, nothing saved yet');
  change(w, rin, 'claude-haiku-9');
  check(await until(async () => (await mine()).runtime.model_routine === 'claude-haiku-9') && rsel.value === '__other' && !rin.hidden, '#7368 freelancer: a new model name saved at once, Other … stays');
  change(w, rin, 'bad model'); await idle(w);
  check(await until(() => rin.value === 'claude-haiku-9') && (await mine()).runtime.model_routine === 'claude-haiku-9', '#5668 freelancer: an invalid model is refused, the old value back');
  change(w, rin, 'Fable');
  check(await until(async () => (await mine()).runtime.model_routine === 'fable') && await until(() => rsel.value === 'fable' && rin.hidden), '#7368 freelancer: "Fable" typed = fable, the choice shows it');
  change(w, rsel, 'sonnet');
  check(await until(async () => (await mine()).runtime.model_routine === 'sonnet') && rin.hidden && rin.value === 'sonnet', '#7368 freelancer: back to a listed model, the free field hides');
  // #7368: the effort beside each model saved at once
  change(w, ms.querySelector('#agm-model-eff'), 'max');
  check(await until(async () => (await mine()).runtime.effort === 'max'), '#7368 freelancer: the effort of the one model saved at once');
  change(w, ms.querySelector('#agm-dec-eff'), 'xhigh');
  check(await until(async () => (await mine()).runtime.effort_decide === 'xhigh'), '#7368 freelancer: the effort for own messages saved at once');
  // 2.992.0 (#5684): the review model, saved at once; the usage per kind below (nothing reported yet, no costs)
  check(ms.querySelector('#agm-rev') && !ms.querySelector('#agm-rev').closest('.row').hidden && /For reviews/.test(ms.textContent), '#5684 freelancer: the field For reviews shows');
  change(w, ms.querySelector('#agm-rev-sel'), 'fable');
  check(await until(async () => (await mine()).runtime.model_review === 'fable'), '#5684 freelancer: the review model saved at once');
  check(await until(() => /Last 7 days/.test(ms.querySelector('.agmu')?.textContent || '') && /No usage reported yet/.test(ms.querySelector('.agmu').textContent)
    && /reports no costs/.test(ms.querySelector('.agmu').textContent)), '#5684 freelancer: the usage section, nothing yet, no costs');
  // 2.1394.0 (#7031): the section "Jobs on its computer" of the own agent: model and effort per kind of job, saved at once;
  // an invalid model is refused and the old value comes back; the dialog opens with the saved values again
  const js = md.querySelector('.agzjob');
  check(js && /Jobs on its computer/.test(js.querySelector('h4')?.textContent || '') && js.querySelector('#agj-model') && js.querySelector('#agj-effort')
    && js.querySelector('#agj-amodel') && js.querySelector('#agj-aeffort') && js.querySelector('#agj-effort').value === ''
    && [...js.querySelector('#agj-effort').options].map(o => o.value).join(',') === ',low,medium,high,xhigh,max', '#7031 freelancer: the jobs section with model and effort per kind, default empty');
  check(js.querySelector('#agj-model').hidden && [...js.querySelector('#agj-model-sel').options].map(o => o.value).join() === ',fable,opus,sonnet,haiku,__other', '#7368: the jobs use the same choice');
  change(w, js.querySelector('#agj-model-sel'), 'opus');
  check(await until(async () => (await mine()).runtime.model_job === 'opus') && js.querySelector('#agj-model').value === 'opus', '#7031 freelancer: model for build jobs saved at once');
  change(w, js.querySelector('#agj-aeffort'), 'high');
  check(await until(async () => (await mine()).runtime.effort_audit === 'high'), '#7031 freelancer: effort for review jobs saved at once');
  change(w, js.querySelector('#agj-amodel-sel'), '__other');
  check(!js.querySelector('#agj-amodel').hidden, '#7368: Other … shows the free field in the jobs section');
  change(w, js.querySelector('#agj-amodel'), 'bad model'); await idle(w);
  check(await until(() => js.querySelector('#agj-amodel').value === '') && (await mine()).runtime.model_audit === '', '#7031 freelancer: an invalid model is refused, the old value back');
  w.close();
  w = await boot({user: 'frida', hash: 'today'}); d = w.document;
  w.eval(`settingsModal('ai')`); await sleep(500);
  await w.eval(`aiSubShow(document.querySelector('.smodal'), 'setup', false)`);
  const prow2 = await until(() => d.querySelector(`#s-myown [data-myag="${FB}"]`));
  click(w, prow2.querySelector('[data-myag-act="perm"]'));
  md = await until(() => lastModal(d)?.querySelector('.agzjob') && lastModal(d));
  check(md && md.querySelector('#agj-model').value === 'opus' && md.querySelector('#agj-model-sel').value === 'opus' && md.querySelector('#agj-aeffort').value === 'high' && md.querySelector('#agj-effort').value === '',
    '#7031 freelancer: the dialog opens again with the saved values');
  w.close();

  // ================= 2.992.0 (#5684): the chat header "runs with ..." and its dialog (frida's own agent, model per run on)
  for (const b of [{run_class: 'decide', run_id: 'r1'}, {run_class: 'decide', run_id: 'r1'}, {run_class: 'decide', run_id: 'r2'}, {run_class: 'review', run_id: 'r3'}, {run_class: 'routine', run_id: 'r4'}])
    check(await asAgent('POST', 'agent/usage', {model: 'claude-x', input_tokens: 1000, output_tokens: 500, ...b}) === 201, '#5684 setup: a usage report ' + JSON.stringify(b));
  check(await asAgent('PUT', 'agent/status', {status: 'idle', model: 'claude-opus-5-5'}) === 200, '#5684 setup: the host reports the model of its last run');
  w = await boot({user: 'frida', hash: 'today'}); d = w.document;
  w.eval(`chatOpen(${FB})`);
  const chip = await until(() => d.querySelector('.chath .chl2 .chrunm'));
  check(chip && chip.tagName === 'BUTTON' && chip.textContent === 'runs with claude-opus-5-5' && /Model of the last run: claude-opus-5-5/.test(chip.title),
    '#5684: the header shows "runs with <model of the last run>" as a button for the owner ' + (chip ? chip.outerHTML : ''));
  click(w, chip);
  md = await until(() => [...d.querySelectorAll('.modal')].find(m => /Model of Fridabot/.test(m.querySelector('h3')?.textContent || '')));
  const hm = md && md.querySelector('.agzmod');
  check(hm && hm.querySelector('#agm-split').checked && hm.querySelector('#agm-dec-sel').value === 'opus' && hm.querySelector('#agm-rev-sel').value === 'fable' && hm.querySelector('#agm-rou').value === 'sonnet'
    && hm.querySelector('#agm-dec-eff').value === 'xhigh' && hm.querySelector('#agm-model-eff').value === 'max',
    '#5684: the tap opens the section Model of this agent with its three models');
  const li = await until(() => hm.querySelectorAll('.agmul li').length === 3 && [...hm.querySelectorAll('.agmul li')]);
  check(li && /Messages and decisions/.test(li[0].textContent) && /Runs: 2/.test(li[0].textContent) && /4\.5k tokens/.test(li[0].textContent)
    && /Reviews/.test(li[1].textContent) && /Runs: 1/.test(li[1].textContent) && /Routine/.test(li[2].textContent) && !/\$/.test(hm.querySelector('.agmul').textContent),
    '#5684: the usage of the last 7 days per kind: runs, tokens, no costs (none reported) ' + (li ? li.map(x => x.textContent).join(' | ') : ''));
  const hsw = hm.querySelector('#agm-split'); hsw.checked = false; hsw.dispatchEvent(new w.Event('change', {bubbles: true}));
  check(await until(async () => (await mine()).runtime.model_split === false), '#5684: switched off in the dialog, saved');
  check(await until(() => !d.querySelector('.chath .chrunm')), '#5684: off = the header line is gone at once');
  click(w, md.querySelector('[data-m="close"]'));
  check(await until(() => !md.isConnected), '#5684: Close closes the dialog');
  // #7350: with the switch off the header's menu line "Model: …" opens the same section (the switch is found there)
  const mrow = async () => { click(w, d.querySelector('[data-act="chat-head-menu"]'));
    return until(() => [...d.querySelectorAll('#pop:not(.hidden) [role="menuitem"]')].find(b => /Model: claude-opus-5-5/.test(b.textContent))); };
  let mi = await mrow();
  check(mi && !mi.disabled && mi.classList.contains('chmi-model') && mi.getAttribute('aria-haspopup') === 'menu', '#7350: switch off - the menu line "Model: …" can be tapped ' + (mi ? mi.outerHTML.slice(0, 200) : ''));
  if (mi) click(w, mi);
  md = await until(() => [...d.querySelectorAll('.modal')].find(m => /Model of Fridabot/.test(m.querySelector('h3')?.textContent || '')));
  check(md && md.querySelector('#agm-split') && !md.querySelector('#agm-split').checked, '#7350: the tap opens the section Model with the switch "model per run" (off)');
  if (md) click(w, md.querySelector('[data-m="close"]'));
  check(await until(() => !md?.isConnected && !!d.querySelector('[data-act="chat-head-menu"]')), '#7350: closed, back in the chat');
  mi = await mrow();
  check(!!mi, '#7350: the menu opens again with the line');
  w.close();
  await call('PATCH', `/api/my/agents/${FB}`, {runtime: {model_split: true}}, CF);
  await call('PATCH', '/api/settings', {lang: 'de'}, CF);
  w = await boot({user: 'frida', hash: 'today'}); d = w.document;
  w.eval(`chatOpen(${FB})`);
  check(await until(() => d.querySelector('.chath .chrunm')?.textContent === 'läuft mit claude-opus-5-5'), '#5684 German: läuft mit');
  click(w, d.querySelector('.chath .chrunm'));
  md = await until(() => [...d.querySelectorAll('.modal')].find(m => /Modell von Fridabot/.test(m.textContent)));
  check(md && /Für Prüfungen/.test(md.textContent) && await until(() => /Letzte 7 Tage/.test(md.textContent) && /Nachrichten und Entscheidungen/.test(md.textContent) && /Läufe: 2/.test(md.textContent)),
    '#5684 German: Modell von, Für Prüfungen, Letzte 7 Tage, Läufe');
  w.close();
  await call('PATCH', '/api/settings', {lang: 'en'}, CF);

  // ================= Firefox: 360 and 412 px, touch
  const ffLogin = async ({ev, nav}) => {
    await nav(B + 'static/icon.svg');
    return ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'frida', password: 'password123'})}).then(r => r.status)`);
  };
  const ready = async (ev, n = 30) => { for (let i = 0; i < n && !(await ev(`!!document.querySelector('#top h1')`).catch(() => false)); i++) await sleep(300); await sleep(700); };
  const FIT = `(() => { const m = [...document.querySelectorAll('.modal')].pop(), s = m && m.querySelector('.agzsec'); if (!s) return null; s.scrollIntoView({block: 'center'});
    const f = [...s.querySelectorAll('select, input:not([type=hidden]), [data-dpfor]')].map(x => x.getBoundingClientRect());
    return {over: document.documentElement.scrollWidth - innerWidth, n: f.length, out: f.filter(r => r.right > innerWidth + 1 || r.left < -1).length,
      minH: Math.round(Math.min(...f.map(r => r.height))), top: (() => { const r = s.getBoundingClientRect(), e = document.elementFromPoint(innerWidth / 2, Math.max(1, Math.min(innerHeight - 1, r.top + 10))); return !!e && m.contains(e); })(),
      cls: m.className, z: getComputedStyle(m).zIndex, n2: document.querySelectorAll('.modal').length}; })()`;
  for (const vw of [360, 412]) await firefox(async o => {
    const {cmd, ev, ctx, nav, shot} = o;
    check(await ffLogin(o) === 200, vw + ': login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: vw, height: 800}});
    await nav(B + '#today'); await ready(ev);
    await ev(`(async () => { settingsModal('ai'); await new Promise(r => setTimeout(r, 500)); await aiSubShow(document.querySelector('.smodal'), 'setup', false); return 1; })()`);
    for (let i = 0; i < 20 && !(await ev(`!!document.querySelector('#s-myown [data-myag="${FB}"] [data-myag-act="perm"]')`)); i++) await sleep(300);
    await ev(`(() => { document.querySelector('#s-myown [data-myag="${FB}"] [data-myag-act="perm"]').click(); return 1; })()`);
    let f = null;
    for (let i = 0; i < 20 && !(f = await ev(FIT)); i++) await sleep(300);
    check(f && f.n >= 4 && f.over <= 1 && f.out === 0 && f.top, `${vw}: the section fits and is on top ` + JSON.stringify(f));
    check(f && f.minH >= 40, `${vw}: fields at least 40 px high ` + JSON.stringify(f));
    await sleep(800); await ev(`(() => { [...document.querySelectorAll('.modal')].pop().querySelector('.agzsec').scrollIntoView({block: 'center'}); return 1; })()`);
    await shot(`p2233b-${vw}-perm.png`);
  }, true);

  console.log(`p2233_b_rotate_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
