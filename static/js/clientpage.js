/* Kalmido web client: Office > Clients in the layout of the contacts (2.47.3, #1734): the list on the left (search, archived,
   the selection mode of #1733), the client's card on the right (phone: the list, then the card). Clients and contacts
   stay apart: the heading "Office > Clients", a "Client" tag and the briefcase on every card (a contact: "Contact" and
   the person), the card shows rate, budget, contact persons, billing details and open invoices.
   Classic script sharing the global scope with the others (load order: index.html, docs/ARCHITECTURE.md). */
'use strict';

const MSC = {items: null, loading: false, seq: 0, q: '', arch: false, pick: null, last: null, inv: null, invLoading: false, trash: false, tItems: null, tDays: 0};
async function ms_clLoad(q) {  // 2.431.0 C (#3602): q = quietly for ms_clLive (no draw)
  const seq = ++MSC.seq;
  MSC.loading = true;
  try { const j = await api('GET', '/api/clients?archived=1'); if (seq === MSC.seq) MSC.items = (j.clients || []).filter(ms_inWs); }
  catch { if (seq === MSC.seq) MSC.items = MSC.items || []; }
  MSC.loading = false;
  if (seq === MSC.seq && !q) ms_clDraw();
}
// open invoices per client (office on); 2.369.0 A (#3200): the open invoices of this client from the server, not filtered here from the newest 500
async function ms_clInvLoad(q, nd) {  // #7399: nd = no draw, a failure counts (ms_clFetch draws once)
  const id = S.route.client; if (!id) return;
  MSC.invLoading = true; MSC.invFor = id;
  try { const rows = await docsAll(`/api/office/docs?kind=invoice&status=open&client_id=${id}`); if (S.route.client === id) MSC.inv = rows; } catch { if (!q) MSC.inv = []; }  // quiet: without an office (400) no section
  MSC.invLoading = false;
  if (!q && !nd) ms_clDraw();
}
// 2.119.1 B (#2086): an address opens the map app on a tap (Apple devices: Apple Maps, else Google Maps); nothing is
// embedded or fetched before the tap (here: the contacts module loads on demand, the client card uses it too)
function ctk_mapLink(t) {
  if (!t) return '';
  const q = encodeURIComponent(t), apple = /iPad|iPhone|iPod|Macintosh/.test(navigator.userAgent);
  const url = apple ? `https://maps.apple.com/?q=${q}` : `https://www.google.com/maps/search/?api=1&query=${q}`;
  return `<a class="ctmap" href="${esc(url)}" target="_blank" rel="noopener noreferrer" title="${esc(tr('Show on the map'))}">${esc(t)}</a>`;
}
// 2.93.0 A (#1927): the client's documents made from templates (office/doctpl.py; admins of the office only, else no section)
function ms_clGdHtml(c) {
  if (typeof officeOn !== 'function' || !officeOn()) return '';
  if (MSC.gd?.id !== c.id) { if (!MSC.gdLoading) setTimeout(() => ms_clGdLoad(c.id), 0); return ''; }
  const ds = MSC.gd.docs; if (!ds) return '';
  const st = {draft: tr('Draft'), final: tr('Finished'), signed: tr('Signed'), declined: tr('Rejected')};
  return `<div class="ctsec"><h4>${tr('Letters & contracts')}</h4>${ds.length ? `<ul class="ctlinks">${ds.map(x => `<li><a class="linkbtn" href="#office/gendocs/${x.id}">${ic('file', 's')} ${esc(x.title || x.kind_label)}</a><span class="muted"> · ${esc([x.list_name, st[x.status] || x.status].filter(Boolean).join(' · '))}</span></li>`).join('')}</ul>` : `<p class="muted">${tr('No letters or contracts yet.')}</p>`}<a class="btn sm" href="#office/gendocs">${ic('plus', 's')} ${tr('New letter or contract')}</a></div>`;  // 2.491.0 (#4020): the texts follow the name of the area (Schreiben & Verträge)
}
async function ms_clGdLoad(id, q) {
  MSC.gdLoading = true;
  try { MSC.gd = {id, docs: (await rawFetch('GET', `/api/office/gen-docs?client_id=${id}&brief=1`)).docs || []}; } catch { MSC.gd = {id, docs: null}; }  // quiet: members (403) see no section
  MSC.gdLoading = false;
  if (!q) ms_clDraw();
}
// 2.153.0 (#2028): the client's letters (office/letters.py; admins of the office only, else no section)
function ms_clLtHtml(c) {
  if (typeof officeOn !== 'function' || !officeOn()) return '';
  if (MSC.lt?.id !== c.id) { if (!MSC.ltLoading) setTimeout(() => ms_clLtLoad(c.id), 0); return ''; }
  const ls = MSC.lt.letters; if (!ls) return '';
  const st = {draft: tr('Draft'), sent: tr('Sent'), delivered: tr('Delivered')};
  return `<div class="ctsec"><h4>${tr('Letters')}</h4>${ls.length ? `<ul class="ctlinks">${ls.slice(0, 20).map(x => `<li><a class="linkbtn" href="#office/letters/${x.id}">${ic('mail', 's')} ${esc(x.subject || x.rcpt_name || tr('Letter'))}</a><span class="muted"> · ${esc([fmtDateLoc(x.letter_date), st[x.status] || x.status].filter(Boolean).join(' · '))}</span></li>`).join('')}</ul>` : `<p class="muted">${tr('No letters yet.')}</p>`}</div>`;
}
async function ms_clLtLoad(id, q) {
  MSC.ltLoading = true;
  try { MSC.lt = {id, letters: (await rawFetch('GET', `/api/office/letters?client_id=${id}&brief=1`)).letters || []}; } catch { MSC.lt = {id, letters: null}; }  // quiet: members (403) see no section
  MSC.ltLoading = false;
  if (!q) ms_clDraw();
}
function ms_clDraw() { if (S.route.mod === 'clients') { const el = $('#view'); if (el) { const ck = ct_scrollKeep(el); keepFocus(el, () => setHtml(el, mg_wrap('clients', viewClients()))); ck(); wso_sync(); } } }  // 2.431.0 C (#3598): + the columns' scroll
// #7399: opening a client loads its card and what the card shows (open invoices, documents, letters, data protection)
// together and draws once; until then the card on screen stays, dimmed (ms_clView), the list, its search and bar stay the
// same nodes (one view, morphed: areas.js ofm_detail keys the path line). Before, every part drew the page on its own.
async function ms_clFetch(id) {
  MSC.opening = id;
  const ofc = typeof officeOn === 'function' && officeOn();
  if (ofc) { MSC.gdLoading = MSC.ltLoading = true; DSB.cl = {id, busy: 1}; }
  // the e-mails and the sign-offs of the card: their modules and data come along (before, each drew the page once more)
  const mod = (n, f) => typeof loadModule === 'function' ? loadModule(n).then(f, () => {}) : null;
  try {
    await Promise.allSettled([clLoad(false, true), ofc && ms_clInvLoad(false, true), ofc && ms_clGdLoad(id, 1), ofc && ms_clLtLoad(id, 1), ofc && dsb_clLoad(id, 1),
      mod('hubmail', () => typeof hbm_load === 'function' && !HBM.s['client:' + id] ? hbm_load('client:' + id, 1) : null),
      mod('videos', () => typeof vdr_load === 'function' ? vdr_load('client_id', id) : null)]);
  }
  finally { if (MSC.opening === id) MSC.opening = null; }
  S.lpN.clOpen = (S.lpN.clOpen || 0) + 1;  // for the tests
  if (S.route.mod === 'clients' && S.route.client === id) ms_clDraw();
}
const ms_clDirty = () => { MSC.items = null; MSC.inv = null; };
// 2.979.0 (#5667): an undo / redo the server did (a move into another workspace taken back): the clients come again
histReloader('clients', () => { if (!MSC.items) return; if (S.route.mod === 'clients') return ms_clLoad(); ms_clDirty(); });
// 2.431.0 C (#3602): a change elsewhere (a full state of the poll, the return to the tab): the page fetches quietly what it
// shows and keeps the old until the new is there; drawn only when the page changed (morphed: scroll, open blocks, selection
// stay). Invoices, documents and letters are fetched again only when the office moved (or what moved is unknown: tab return)
async function ms_clLive() {
  if (S.route.mod !== 'clients') return;
  if (MSC.trash || S.route.client === 'mailhub' || !MSC.items) return clReload();
  const ch = S.lpUnk ? null : [...S.lpPend], off = !ch?.length || ch.includes('office') || ch.includes('other'), id = S.route.client || null;
  await Promise.allSettled([ms_clLoad(1), id && CLV.id === id && clLoad(1), off && MSC.inv && ms_clInvLoad(1), off && id && MSC.gd?.id === id && ms_clGdLoad(id, 1), off && id && MSC.lt?.id === id && ms_clLtLoad(id, 1)]);
  if (S.route.mod !== 'clients' || S.route.client !== id) return;
  const was = MSC.html; viewClients(); S.lpN.clLive = (S.lpN.clLive || 0) + 1;  // clLive / clDraw: for the tests
  if (MSC.html === was) return;  // the same page: nothing drawn
  if (lpBusy()) { S.viewStale = true; return; }  // a field / form in use: drawn once it is left (the poll)
  S.lpN.clDraw = (S.lpN.clDraw || 0) + 1; ms_clDraw();
}
const ms_clShown = () => (MSC.items || []).filter(c => (MSC.arch || !c.archived) && (!MSC.q.trim() || [c.name, c.name_extra, c.display_name, c.label, c.contact, c.email, c.phone, c.note, c.billing?.customer_no]
  .some(v => (v || '').toLowerCase().includes(MSC.q.trim().toLowerCase()))) && dsb_clPass(c));  // 2.154.0 C (#2192): + the data protection filter
// #7292: the list with every location right under its main client (both shown: indented, _site = the main client's label; a
// location whose main client is filtered out stands on its own); its row shows its own part of "main client · location"
function ms_clTree(items) {
  const by = new Map(items.map(c => [c.id, c])), kids = new Map();
  for (const c of items) if (c.parent_id && by.has(c.parent_id)) kids.set(c.parent_id, [...kids.get(c.parent_id) || [], c]);
  const out = [];
  for (const c of items) {
    if (c.parent_id && by.has(c.parent_id)) continue;
    out.push(c);
    for (const k of kids.get(c.id) || []) out.push({...k, _site: cdn_label(c)});
  }
  return out;
}
const ms_clOwn = c => { const l = cdn_label(c), p = c._site ? c._site + ' · ' : ''; return p && l.startsWith(p) ? l.slice(p.length) : l; };
// #7292: archiving / deleting a main client asks about its locations; "Only the main client" (and Esc) leaves them as they are
async function ms_clWithSites(ids, title, okText, keep = () => true) {
  const kids = (S.clients || []).filter(x => ids.includes(x.parent_id) && !ids.includes(x.id) && keep(x));
  if (!kids.length) return ids;
  const yes = await askConfirm(title(kids.length), tr('Locations: {0}', kids.map(cdn_label).join(', ')), {ok: okText, cancel: tr('Only the main client')});
  return yes ? [...ids, ...kids.map(x => x.id)] : ids;
}
const ms_clAv = (c, big) => `<span class="avatar ctav mscav ${big ? 'big' : ''}" style="${cssColor(c.color) ? '--cc:' + cssColor(c.color) : ''}" aria-hidden="true">${c.icon ? clSymHtml(c.icon, big ? '' : 's') : ic('brief', big ? '' : 's')}</span>`;
const ms_tag = (kind) => kind === 'client' ? `<span class="mstag mstag-cl">${ic('brief', 's')}${tr('Client')}</span>` : `<span class="mstag">${ic('user', 's')}${tr('Contact')}</span>`;

// 2.47.3 (#1360): the page follows the workspace of the sidebar like the office (Private = the private clients, an
// organisation = its clients, All = every client one sees)
// 2.1254.0 (#6180): the open client card reports its organisation (wscolor.js); no card open = nothing
wso_open('clients', () => { const id = S.route?.mod === 'clients' ? S.route.client : null; if (!id || id === 'mailhub') return null; const c = (MSC.items || []).find(x => x.id === id) || (CLV.data && CLV.id === id ? CLV.data : null); return c ? {org_id: c.org_id ?? null} : null; });
// 2.1398.0 (#6722): under "All" only the clients of workspaces where Clients is on for me (areas.js mod_entryOn)
const ms_inWs = c => { const ws = typeof wsCur === 'function' ? wsCur() : 'all'; return ws === 'all' ? mod_entryOn(c.org_id || 0, 'office', 'clients') : (ws === 'private' ? c.org_id == null : 'org:' + c.org_id === ws); };
// 2.122.3 A (#2335): the way from a list of the office to its section of Settings > Import legacy data (#office/import/<area>):
// an empty list says "Already have a list? Import from Excel", a filled one ends with a quiet "Import…" (office admins only;
// lives here because the clients view draws it too without the office module loaded; the import page checks again)
function oim_link(area, empty, csv) {
  if (typeof officeOn !== 'function' || !officeOn() || (S.route.mod === 'office' && typeof ofcAdmin === 'function' && !ofcAdmin())) return '';
  const t = empty ? (csv ? tr('Already have a list? Import from CSV') : tr('Already have a list? Import from Excel')) : tr('Import…');
  return `<p class="oimlink ${empty ? 'e' : ''}"><a ${empty ? '' : 'class="btn sm" '}href="#office/import/${area}" data-oim-go="${area}">${empty ? ic('upload', 's') + ' ' : ''}${esc(t)}</a></p>`;  // 2.1211.0 (#6148): the plain "Import…" has the shape of a button
}
function ms_clView() {
  if (MSC.ws !== undefined && MSC.ws !== (typeof wsCur === 'function' ? wsCur() : 'all')) ms_clDirty();
  MSC.ws = typeof wsCur === 'function' ? wsCur() : 'all';
  if (S.route.client === 'mailhub' && typeof hbm_hubView === 'function') {  // 2.84.0 A (#1198)
    const r = S.route;  // 2.754.0 (#5268): mailhub/<id> (the core's open_url of a filed e-mail) opens its reading view once
    if (r.mail && !r.mailShown && typeof hbm_open === 'function') { r.mailShown = true; setTimeout(() => hbm_open(r.mail, 'inbox:0'), 0); }
    return hbm_hubView();
  }
  if (MSC.items === null && !MSC.loading) setTimeout(ms_clLoad, 0);
  const id = S.route.client || null, mob = lsd_one();  // 2.1168.0 (#6117): a phone or a content area too narrow for list + card (render.js)
  if (id && MSC.invFor !== id && !MSC.invLoading) MSC.inv = null;  // 2.369.0 A (#3200): another client
  if (id && (!CLV.data || CLV.id !== id) && !CLV.loading && MSC.opening !== id) { MSC.opening = id; setTimeout(() => ms_clFetch(id), 0); }  // #7399: card + its parts, one draw
  if (id && MSC.inv === null && !MSC.invLoading && MSC.opening !== id && typeof officeOn === 'function' && officeOn()) setTimeout(ms_clInvLoad, 0);
  const d = id && CLV.data && CLV.id === id ? CLV.data : null;
  // #7399: while another client loads, the card on screen stays (dimmed, busy) instead of "Loading…"
  const pick = `<div class="ctcard ctnone ctpick muted">${ic('brief')}${tr('Select a client')}</div>`;
  const dim = h => h.replace(/^<(\w+) class="ctcard /, '<$1 aria-busy="true" class="ctcard ctwait ');
  // #7398: the same client again (its month switched) keeps its card on a phone too
  const was = !d && id ? MSC.cardHtml && (!mob ? $('#view .msclcard[data-ck]') : $(`#view .msclcard[data-ck="${+id}"]`)) ? dim(MSC.cardHtml) : !mob && $('#view .ctcard.ctpick') ? dim(pick) : '' : '';
  const card = !id ? (mob ? '' : pick)
    : !d ? was || `<div class="ctcard ctnone muted">${tr('Loading…')}</div>`
    : d.error ? `<div class="ctcard ctnone muted">${ic('brief')}${tr('This client does not exist or you cannot see it.')}${mob ? `<a class="btn" href="#clients">${tr('All clients')}</a>` : ''}</div>` : (MSC.cardHtml = ms_clCard(d));
  const head = '';  // 2.87.9 (#1917): no "Office › Clients" heading (it looked like a way back); the office menu shows the place, the path only on a client
  const none = !MSC.trash && MSC.items !== null && !MSC.items.length;  // 2.218.0 C (#2804): no clients yet -> only the way to the first one (the empty state below), no filters
  const bar = none ? '' : `<div class="ctbar"><div class="ctsearch">${ic('search', 's')}<input id="mscl-q" type="search" value="${esc(MSC.q)}" placeholder="${esc(tr('Search clients'))}" aria-label="${esc(tr('Search clients'))}" autocomplete="off" enterkeyhint="search"></div>
    <label class="chkl"><input type="checkbox" id="mscl-arch" ${MSC.arch ? 'checked' : ''}> ${tr('Archived')}</label><label class="chkl"><input type="checkbox" id="mscl-trash" ${MSC.trash ? 'checked' : ''}> ${tr('Trash')}</label>${dsb_clFilter()}<span class="spacer"></span>${typeof hbm_hubBtn === 'function' ? hbm_hubBtn() : ''}
    ${(MSC.items || []).length && !MSC.trash ? `<button class="iconbtn ${MSC.pick ? 'on' : ''}" data-mscl="pick" aria-pressed="${!!MSC.pick}" aria-label="${esc(tr(MSC.pick ? 'End selection' : 'Select'))}" title="${esc(tr(MSC.pick ? 'End selection' : 'Select'))}">${ic('select')}</button>` : ''}
    <button class="btn sm pri" data-act="client-new">${ic('plus', 's')}<span class="cdl">${tr('New client')}</span></button></div>`;
  const items = MSC.items === null ? null : ms_clTree(ms_clShown());  // #7292: locations under their main client
  const list = MSC.trash ? ms_clTrashHtml() : items === null ? `<div class="muted ctempty">${tr('Loading…')}</div>`
    : !MSC.items.length ? `<div class="empty nempty eact msclempty">${ic('brief')}<span>${tr('Clients are everyone you write quotations and invoices for: companies or private people.')}</span><button class="btn pri" data-act="client-new">${ic('plus', 's')} ${tr('New client')}</button>${feat('contacts') ? `<a class="btn" href="#contacts">${ic('users', 's')} ${tr('Contacts')}</a>` : ''}${oim_link('master', true)}</div>`
    : !items.length ? `<div class="empty">${ic('brief')}${tr('No client matches.')}</div>`
    : `<ul class="ctlist" role="list" aria-label="${esc(tr('Clients'))}">${items.map(c => `<li><button type="button"${/*html-ok*/ wso_row(c) /* (#6180) */} class="ctrow ${c.id === id ? 'on' : ''} ${MSC.pick?.has(c.id) ? 'picked' : ''} ${c.archived ? 'msarch' : ''} ${c._site ? 'clsite' : ''}" data-clopen="${c.id}" ${MSC.pick ? `aria-pressed="${MSC.pick.has(c.id)}"` : `aria-current="${c.id === id}"`}>${MSC.pick ? `<span class="ctchk ${MSC.pick.has(c.id) ? 'on' : ''}" aria-hidden="true">${MSC.pick.has(c.id) ? ic('check', 's') : ''}</span>` : ''}${ms_clAv(c)}<span class="ctn"><b>${c._site ? `<span class="sr">${esc(tr('Location of {0}:', c._site))} </span>` : ''}${esc(c._site ? ms_clOwn(c) : cdn_label(c))}</b><small class="muted">${esc([cdn_label(c) !== c.name ? c.name : '', c.archived ? tr('archived') : '', c.contact, c.email].filter(Boolean).join(' · '))}</small>${/*html-ok*/ wso_origin(c, 'ctorg') /* (#6180): "All": the origin */}</span>${c.budget && c.budget.level !== 'none' ? `<i class="msbud lv-${c.budget.level}" title="${esc(tr(BUDGET_TXT[c.budget.level]))}"></i>` : ''}</button></li>`).join('')}</ul>`;
  return MSC.html = `<div class="ctview msclients ${id ? 'withcard' : ''} ${MSC.pick ? 'ctpicking' : ''}">${mob && id ? '' : head}${MSC.pick && !(mob && id) ? ms_clBar() : ''}${mob && id ? '' : bar}<div class="ctcols lsd2 lsdfill">${mob && id ? '' : `<div class="ctlistw lsdl">${list}${MSC.items?.length && !MSC.pick ? oim_link('master') : ''}</div>`}${card}</div></div>`;
}
// 2.435.0 A (#3600): the blocks of the client card like the blocks of a list: the office admin switches blocks off for the
// office (office setting client_blocks_off, sent with the client: blocks_off), each person shows / hides the others for
// themselves (the view builder) and folds them open / closed -- kept per person in the opts of view_clients, alike for every
// client. Open by default: details, contact persons, open invoices (and the note); the others closed, with their number.
const MSC_OPEN = ['details', 'persons', 'invoices', 'note', 'sites'];  // #7292: + a main client's locations
const ms_clOff = () => new Set(CLV.data && !CLV.data.error ? CLV.data.blocks_off || [] : []);
const ms_clOpen = k => !!lyOpt('clients', k, 'open', MSC_OPEN.includes(k));
const ms_clFold = (k, html, n) => lyFold('clients', k, html, n, ms_clOpen(k), 'data-mscl="fold"');  // 2.666.0 D (#3624): the shared fold (dashboard.js)
function ms_clFoldAll(c, ks, inv, parts) {
  const st = c.stats || {}, num = {persons: ks.length, invoices: inv.length, month: st.month_seconds ? fmtHours(st.month_seconds) : null,
    lists: (c.per_list || []).length, sites: (c.sites || []).length || null, tickets: (c.tickets || []).length, gendocs: MSC.gd?.id === c.id ? MSC.gd.docs?.length : null,
    letters: MSC.lt?.id === c.id ? MSC.lt.letters?.length : null, privacy: DSB.cl?.id === c.id ? DSB.cl.sheets?.length : null};
  const off = ms_clOff(), out = {};
  for (const [k, h] of Object.entries(parts)) if (!off.has(k)) out[k] = ms_clFold(k, h, num[k]);
  return out;
}
// #7292: the block "Locations" of a main client: the figures of all together (own + every location: hours, amounts, budget)
// and one row per location (a link to it) with its own figures; "Add location" makes a new client that belongs to this one
function ms_clSitesHtml(c) {
  const ss = c.sites || [], g = c.group; if (!ss.length || !g) return '';
  const st = g.stats || {}, mon = st.month;
  const row = (x, own) => `<tr><td>${own ? `<b>${esc(tr('Main client'))}</b>` : `<a href="#client/${esc(String(x.id))}">${esc(cdn_label(x))}</a>${x.archived ? ` <span class="rotag">${tr('Archived')}</span>` : ''}`}</td><td class="n">${esc(hmm(x.stats?.month_seconds || 0))}</td><td class="n">${esc(hmm(x.stats?.seconds || 0))}</td><td class="n">${x.stats?.amount ? esc(fmtMoney(x.stats.amount)) : ''}</td></tr>`;
  return `<section class="stcard clsites"><div class="sthead"><h3>${tr('All locations together')}</h3></div>
    <div class="sttiles"><div><b>${esc(hmm(st.month_seconds || 0))}</b><span>${esc(monthLabel(mon))}</span><small>${st.month_amount ? esc(fmtMoney(st.month_amount)) : ''}</small></div>
      <div><b>${esc(hmm(st.seconds || 0))}</b><span>${tr('in total')}</span><small>${st.amount ? esc(fmtMoney(st.amount)) : ''}</small></div>
      <div><b>${esc(String(ss.length + 1))}</b><span>${tr('Main client and locations')}</span><small></small></div></div>
    ${/*html-ok*/ budgetBar(g) /* clients.js: escaped inside */}
    <table class="ttable cltable"><thead><tr><th>${tr('Client')}</th><th class="n">${esc(monthLabel(mon))}</th><th class="n">${tr('in total')}</th><th class="n">${tr('Amount')}</th></tr></thead>
      <tbody>${/*html-ok*/ row(c, true) + ss.map(x => row(x)).join('') /* rows escaped inside */}</tbody></table>
    <div class="clacts"><button type="button" class="btn sm" data-mscl="siteadd">${ic('plus', 's')} ${tr('Add location')}</button></div></section>`;
}
function ms_clCard(c) {
  const b = c.billing || {}, cur = S.settings.time_currency || '€';  // 2.368.0 C (#2983): amounts through curMoney (i18n.js)
  const ii = k => typeof ux_info === 'function' ? ux_info(k) : '';  // 2.47.3 (D, #1382): the (i) explanations of the office
  const f = (icon, label, val, k) => val ? `<div class="ctf">${ic(icon, 's')}<span class="ctfl muted">${esc(label)}</span><span>${val}</span></div>${k ? ii(k) : ''}` : '';
  const adr = cdn_addrLine(c);  // 2.97.0 B (#1951): the fixed fields only (with the extra line)
  const bud = [c.budget_h ? `${fmtNum(c.budget_h, 1)} h` : '', c.budget_amount ? curMoney(c.budget_amount, cur) : ''].filter(Boolean).join(' · ');
  const inv = (MSC.inv || []).filter(x => x.client_id === c.id && x.open > 0 && !['draft', 'cancelled'].includes(x.status));
  const ks = (c.contacts || []).filter(k => k.name);
  return `<article class="ctcard msclcard" aria-labelledby="mscl-h" data-ck="${c.id}"${/*html-ok*/ wso_row(c) /* 2.1254.0 (#6180) */}>
    <div class="cthead">${lsd_one() ? `<button class="iconbtn" data-mscl="back" aria-label="${esc(tr('Back'))}">${ic('back')}</button>` : ''}${ms_clAv(c, true)}<div class="cthn"><h3 id="mscl-h">${esc(cdn_label(c))}</h3>${cdn_label(c) !== c.name ? `<small class="muted cdnlegal">${esc(c.name)}</small>` : ''}<div class="mstags">${ms_tag('client')}${c.archived ? `<span class="rotag">${tr('Archived')}</span>` : ''}${c.org_name ? `<span class="muted">${esc(c.org_name)}</span>` : ''}${c.parent_id && clientById(c.parent_id) ? `<span class="muted clparent">${ic('mappin', 's')} ${tr('Location of')} <a href="#client/${esc(String(c.parent_id))}">${esc(cdn_label(clientById(c.parent_id)))}</a></span>` : ''}</div></div>
      <span class="ctacts"><button class="btn sm" data-act="client-edit" data-id="${c.id}">${ic('edit', 's')} ${tr('Edit')}</button><button class="iconbtn" data-mscl="cmenu" aria-haspopup="menu" aria-label="${esc(tr('More'))}" title="${esc(tr('More'))}">${ic('dots')}</button></span></div>${/*html-ok*/ ihd_cardHtml(c) /* 2.1384.0 (#6700): escaped inside */}
    <div class="mscly msclstats cldetail">${S.ly.view === 'clients' ? '' : `<div class="lybar"><span class="spacer"></span>${lyCustomBtn('clients')}</div>`}${lyHtml('clients', ms_clFoldAll(c, ks, inv, {  // 2.55.0 (#1067): the card's sections are blocks of the view builder
      details: `<div class="ctfields">
      ${f('money', tr('Hourly rate'), c.rate != null ? esc(curMoney(c.rate, cur)) : '')}
      ${f('chart', tr('Budget'), esc(bud))}
      ${f('at', tr('E-mail'), c.email ? `<a href="mailto:${esc(c.email)}">${esc(c.email)}</a>` : '')}
      ${f('phone', tr('Phone'), c.phone ? `<a href="tel:${esc(c.phone.replace(/[^\d+]/g, ''))}">${esc(c.phone)}</a>` : '')}
      ${f('mappin', tr('Address'), ctk_mapLink(adr))}${''/* 2.119.1 B (#2086): a map link */}
      ${f('hash', tr('Client no.|customer'), esc(b.customer_no || ''), 'cl_customer_no')}
      ${f('receipt', tr('VAT ID'), esc(b.vat_id || ''), 'cl_vat_id')}
      ${f('tag', tr('Buyer reference (e.g. routing ID)'), esc(b.buyer_reference || ''), 'cl_buyer_reference')}
      ${f('send', tr('Peppol ID'), esc(b.peppol_id || ''), 'cl_peppol_id')}${''/* 2.154.0 B (#1960) */}
      ${f('at', tr('E-mail for invoices'), b.email_invoice ? `<a href="mailto:${esc(b.email_invoice)}">${esc(b.email_invoice)}</a>` : '', 'cl_email_invoice')}
      ${f('clock', tr('Payment terms (days)'), b.payment_terms_days != null ? esc(String(b.payment_terms_days)) : '', 'cl_payment_terms_days')}
      ${f('tag', tr('Document language'), esc((S.languages || []).find(L => L.code === b.doc_lang)?.name || ''))}${''/* 2.460.0 (#3767) */}
    </div>`,
      persons: ks.length ? `<div class="ctsec"><h4>${tr('Contact persons')}</h4><ul class="ctlinks msclks">${ks.map(k => `<li>${ic('user', 's')} ${k.contact_id && feat('contacts') ? `<a href="#contacts/${k.contact_id}" title="${esc(tr('Open contact'))}"><b>${esc(k.name)}</b></a>` : `<b>${esc(k.name)}</b>`}${k.role ? ` <span class="muted">${esc(k.role)}</span>` : ''}${k.is_default && ks.length > 1 ? ` <span class="rotag">${tr('Default')}</span>` : ''}${k.email ? ` · <a href="mailto:${esc(k.email)}">${esc(k.email)}</a>` : ''}${k.phone ? ` · <a href="tel:${esc(k.phone.replace(/[^\d+]/g, ''))}">${esc(k.phone)}</a>` : ''}</li>`).join('')}</ul></div>` : '',
      invoices: typeof officeOn === 'function' && officeOn() && MSC.inv !== null ? `<div class="ctsec"><h4>${tr('Open invoices')}</h4>${inv.length ? `<ul class="ctlinks">${inv.map(x => `<li><a class="linkbtn" href="#office/invoices/${x.id}">${ic('receipt', 's')} ${esc(x.number || tr('Draft'))}</a><span class="muted"> · ${esc(x.date ? fmtDateLoc(x.date) : '')} · ${esc(x.open_text || '')} · ${esc(x.status_text || '')}</span></li>`).join('')}</ul>` : `<p class="muted">${tr('No open invoices.')}</p>`}</div>` : '',
      privacy: dsb_clHtml(c),  // 2.154.0 C (#2192): the data protection sheets (office admins)
      tickets: typeof ptl_clientHtml === 'function' ? ptl_clientHtml(c) : '',  // 2.63.0 B (#1513): the client's reports
      gendocs: ms_clGdHtml(c),  // 2.93.0 A (#1927): the documents made from templates (office admins)
      letters: ms_clLtHtml(c),  // 2.153.0 (#2028); 2.435.0 A (#3600): a block of its own
      sites: ms_clSitesHtml(c),  // #7292
      ...clientDetailParts(c)}))}${clm_histHtml(c)}${typeof hbm_clientHtml === 'function' ? hbm_clientHtml(c) : ''}${typeof vdr_clientHtml === 'function' ? vdr_clientHtml(c) : ''}${''/* 2.99.1 A (#1959): video sign-offs */}</div>
  </article>`;
}

// ---- 2.1384.0 (#6700): a client an invoice issuer's key set up or changed (office/isshold.py): its external id and, until a
// person checked them, the hold mark with the fields old -> new; "Client data from the invoice issuer checked" takes it away
// (the rights to change its invoicing fields). The finalise and send dialogs (office_docs.js) show the same list with a tick.
const IHD_FIELDS = {name: N_('Name'), name_extra: N_('Name addition'), street: N_('Street'), address_extra: N_('Address extra'), zip: N_('Postcode'),
  city: N_('City'), country: N_('Country'), vat_id: N_('VAT ID'), email_invoice: N_('E-mail for invoices'), buyer_reference: N_('Buyer reference (e.g. routing ID)')};
function ihd_listHtml(h) {
  const v = x => x ? esc(x) : `<span class="muted">${esc(tr('empty'))}</span>`;
  const rows = (h.fields || []).map(f => `<li><span class="muted">${esc(tr(IHD_FIELDS[f.field] || f.field))}:</span> ${/*html-ok*/ f.hidden ? `<span class="muted">${esc(tr('changed'))}</span>` /* review F4: an invoicing field this person may not see */ : h.new ? v(f.new) : `${/*html-ok*/ v(f.old)} → <b>${/*html-ok*/ v(f.new)}</b>` /* v() escapes */}</li>`);
  const flags = [(h.flags || []).includes('client_lookalike') ? tr('Another client of the office has the same name or VAT ID.') : '',
    (h.flags || []).includes('text_suspicious') ? tr('The name contains a web or e-mail address.') : ''].filter(Boolean);
  return `<p><b>${esc(h.new ? tr('Set up by the invoice issuer {0}; no person has checked the data yet.', h.issuer || '') : tr('Changed by the invoice issuer {0}; no person has checked the changes yet.', h.issuer || ''))}</b></p>`
    + (rows.length ? `<ul class="ihdlist">${/*html-ok*/ rows.join('') /* escaped above */}</ul>` : '') + flags.map(x => `<p>${esc(x)}</p>`).join('');
}
// the box of a dialog: the list and the tick that confirms it (id ofd-ihd-ok); '' without a mark
const ihd_dlgHtml = h => h ? `<div class="ofdwarn ihdbox" role="status">${/*html-ok*/ ihd_listHtml(h)}<label class="chkl"><input type="checkbox" id="ofd-ihd-ok"> ${esc(tr('I checked these client data'))}</label></div>` : '';
function ihd_cardHtml(c) {
  const i = c.issuer; if (!i) return '';
  const ref = i.external_ref ? `<p class="muted ihdref">${esc(tr('Managed by an invoice issuer, external ID {0}', i.external_ref))}</p>` : '';  // review F1: an imported mark has no issuer
  const h = i.client_hold; if (!h) return ref;
  return `${/*html-ok*/ ref}<div class="ofdwarn ihdbox" role="status">${/*html-ok*/ ihd_listHtml(h)}<p>${esc(tr('Until a person checks them, documents to this client are finalised and sent only after a confirmation in the dialog, and never automatically.'))}</p>`
    + `${c.bill_edit ? `<button class="btn sm" data-ihd-ok="${esc(String(c.id))}" data-at="${esc(h.at)}">${ic('check', 's')} ${esc(tr('Client data from the invoice issuer checked'))}</button>` : ''}</div>`;
}
document.addEventListener('click', async e => {
  const b = e.target.closest('#view [data-ihd-ok]'); if (!b) return;
  b.disabled = true;
  try { await api('POST', `/api/clients/${+b.dataset.ihdOk}/issuer-hold`, {at: b.dataset.at}); toast(tr('Checked')); } catch { /* api() said it */ }
  if (typeof ms_clAfter === 'function') await ms_clAfter(); else clReload();
});

// ---- 2.120.0 B (#2088): "Send portal link": the client gets the sign-in link of the customer portal by mail (office/portaldocs.py;
// the office setting "Show documents in the customer portal" must be on, else the server says so)
function kp_menuItem(c) {
  const to = c.billing?.email_invoice || c.email || '';
  if (!to || typeof officeOn !== 'function' || !officeOn() || S.me?.kid) return null;
  return {label: tr('Send portal link'), icon: 'mail', fn: async () => {
    if (!await askConfirm(tr('Send the portal link to {0}?', to), tr('The client sees the sent quotations, invoices and their payment status. The link is valid for 30 minutes.'), {ok: tr('Send|mail')})) return;
    try { const j = await rawFetch('POST', `/api/office/clients/${c.id}/portal-link`, {}); toast(tr('Portal link sent to {0}', j.to || to)); } catch (x) { toast(x.message || ''); }
  }};
}

// ---- #1733: several clients at once (the selection bar of the contacts, multisel.js): Edit (rate, budget, colour,
// a note appended), Archive / Restore, Delete (a client in use is archived instead); one undo step each except Delete
function ms_clBar() {
  const n = MSC.pick.size, sel = (MSC.items || []).filter(c => MSC.pick.has(c.id)), allArch = sel.length && sel.every(c => c.archived);
  const shown = ms_clShown(), allOn = n && shown.every(c => MSC.pick.has(c.id));
  return ms_barHtml('ct-sbar', 'clb', n, tr('Tap clients'), [['all', 'all', allOn ? tr('Select none') : tr('All')], ['edit', 'edit', tr('Edit')],
    ['arch', allArch ? 'undo' : 'archive', allArch ? tr('Restore') : tr('Archive')], ['merge', 'collapse', tr('Merge'), '', 2],
    ...(ofm_can(sel[0]?.org_id ?? null) ? [['move', 'brief', tr('Move to another workspace…')]] : []), ['del', 'trash', tr('Delete'), 'danger']], {words: true});  // 2.1168.0 (#6118): whole words like the contacts; 2.97.0 C (#2049)  // 2.66.0 (#1835): merge from two clients on (min 2)
}
function ms_clClick(id, shift) {
  if (!MSC.pick) { MSC.pick = new Set(); MSC.last = null; }
  if (shift && MSC.last != null) for (const x of ms_range(ms_clShown().map(c => c.id), MSC.last, id)) MSC.pick.add(x);
  else if (MSC.pick.has(id)) MSC.pick.delete(id); else MSC.pick.add(id);
  MSC.last = id; ms_clDraw();
}
const ms_clEnd = () => { MSC.pick = null; MSC.last = null; ms_clDraw(); };
const ms_clSend = body => rawFetch('POST', '/api/clients/bulk', body);
async function ms_clAfter() { ms_clDirty(); CLV.data = null; await load().catch(() => {}); ms_clDraw(); }
async function ms_clAct(k) {
  if (!MSC.pick) return;
  if (k === 'close') { ms_clEnd(); return; }
  const shown = ms_clShown();
  if (k === 'all') { if (MSC.pick.size && shown.every(c => MSC.pick.has(c.id))) MSC.pick.clear(); else for (const c of shown) MSC.pick.add(c.id); ms_clDraw(); return; }
  const ids = [...MSC.pick]; if (!ids.length) return;
  if (k === 'arch') {
    const sel = (MSC.items || []).filter(c => MSC.pick.has(c.id)), action = sel.every(c => c.archived) ? 'unarchive' : 'archive';
    let j; try { j = await ms_clSend({action, ids}); } catch (x) { toast(x.message || ''); return; }
    ms_clEnd(); await ms_clAfter();
    const msg = action === 'archive' ? trn('{0} client archived', '{0} clients archived', j.changed) : trn('{0} client restored', '{0} clients restored', j.changed);
    if (j.changed) ms_hist(msg, msg, async () => { await ms_clSend({action: 'restore', items: j.undo}); await ms_clAfter(); }, async () => { j = await ms_clSend({action, ids}); await ms_clAfter(); });
    else toast(msg);
  } else if (k === 'del') {
    await loadModule('trashui'); await ms_clDel(ids);  // 2.272.0 G (#3038): the dialog lives in trashui.js (start budget)
  } else if (k === 'edit') ms_clEdit(ids);
  else if (k === 'merge') clm_merge(ids);  // 2.66.0 B (#1835)
  else if (k === 'move') ofm_clients(ids);  // 2.97.0 C (#2049)
}
// 2.66.0 B (#1835): merging duplicate clients (multisel.js ms_merge; server team/clientmerge.py): per differing field the value
// that stays, the contact persons are joined; the overview comes from the server (dry); one undo step (and Undo in the history)
function clm_merge(ids) {
  const sel = ids.map(i => (MSC.items || []).find(c => c.id === i)).filter(Boolean);
  if (sel.length < 2) { toast(tr('Select at least two entries to merge')); return; }
  const cur = S.settings.time_currency || '€', num = (v, d, u) => v == null || v === '' ? '' : `${fmtNum(v, d)}${u ? ' ' + u : ''}`;
  const val = (k, fn) => Object.fromEntries(sel.map(c => [c.id, String(fn(c) ?? '')]));
  const fields = [['name', tr('Name'), c => c.name], ['contact', tr('Default contact person'), c => c.contact], ['email', tr('E-mail'), c => c.email],
    ['phone', tr('Phone'), c => c.phone],  // 2.97.0 B (#1951): no free address any more (street etc. below)
    ['rate', tr('Hourly rate'), c => curMoney(c.rate, cur)], ['budget_h', tr('Budget in hours'), c => num(c.budget_h, 1, 'h')],
    ['budget_amount', tr('Budget as an amount'), c => curMoney(c.budget_amount, cur)], ['note', tr('Note'), c => c.note],
    ...OFX_CL_FIELDS.map(([k, n]) => [k, tr(n), c => (c.billing || {})[k]])].map(([k, label, fn]) => ({k, label, vals: val(k, fn)}));
  const send = (target, pick, dry) => rawFetch('POST', '/api/clients/merge', {target, ids, pick, dry});
  ms_merge({title: trn('Merge {0} client', 'Merge {0} clients', sel.length),
    recs: sel.map(c => ({id: c.id, label: cdn_label(c), sub: [c.org_name, c.archived ? tr('Archived') : ''].filter(Boolean).join(' · ')})),
    fields, lists: [{k: 'contacts', label: tr('Contact persons'), vals: Object.fromEntries(sel.map(c => [c.id, (c.contacts || []).map(k => k.name)]))}],
    preview: (target, pick) => send(target, pick, true),
    run: async (target, pick) => {
      let j = await send(target, pick, false);
      ms_clEnd(); await ms_clAfter(); go('client/' + target);
      const msg = trn('{0} client merged', '{0} clients merged', sel.length);
      ms_hist(msg, tr('Clients merged'), async () => { await rawFetch('POST', `/api/clients/merges/${j.run_id}/undo`, {}); await ms_clAfter(); },
        async () => { j = await send(target, pick, false); await ms_clAfter(); });
      return true;
    }});
}
function ms_clEdit(ids) {
  const cur = esc(S.settings.time_currency || '€'), num = (k, unit, lab) => `<span class="lacts"><input id="ms-f-${k}" data-msf="${k}" inputmode="decimal" class="numin" placeholder="–" aria-label="${esc(lab)}"><span class="muted">${unit}</span></span>`;
  ms_sheet(trn('Edit {0} client', 'Edit {0} clients', ids.length), tr('Only what you fill in or tick changes; everything else stays as it is.'), [
    {k: 'rate', label: tr('Hourly rate'), input: num('rate', cur, tr('Hourly rate')), hint: tr('empty = remove')},
    {k: 'budget_h', label: tr('Budget in hours'), input: num('budget_h', 'h', tr('Budget in hours')), hint: tr('empty = remove')},
    {k: 'budget_amount', label: tr('Budget as an amount'), input: num('budget_amount', cur, tr('Budget as an amount')), hint: tr('empty = remove')},
    {k: 'color', label: tr('Colour'), input: `<input type="color" id="ms-f-color" data-msf="color" value="#4f7cff" aria-label="${esc(tr('Colour'))}">`},
    {k: 'note_append', label: tr('Append to the note'), input: `<textarea id="ms-f-note_append" data-msf="note_append" rows="3" maxlength="4000"></textarea>`, fill: true}],
  async v => {
    const body = {action: 'set', ids};
    for (const k of ['rate', 'budget_h', 'budget_amount']) if (k in v) body[k] = numBody(v[k]);  // 2.263.0 (#2976)
    if ('color' in v) body.color = v.color;
    if (v.note_append) body.note_append = v.note_append;
    let j = await ms_clSend(body);
    ms_clEnd(); await ms_clAfter();
    const msg = trn('{0} client changed', '{0} clients changed', j.changed);
    if (j.changed) ms_hist(msg, tr('Clients changed'), async () => { await ms_clSend({action: 'restore', items: j.undo}); await ms_clAfter(); }, async () => { j = await ms_clSend(body); await ms_clAfter(); });
    else toast(msg);
    return true;
  });
}

// ---- events
document.addEventListener('input', e => {
  if (e.target.id !== 'mscl-q') return;
  MSC.q = e.target.value; clearTimeout(MSC.t); MSC.t = setTimeout(ms_clDraw, 120);
});
document.addEventListener('change', e => { if (e.target.id === 'mscl-arch') { MSC.arch = e.target.checked; ms_clDraw(); } else if (e.target.id === 'mscl-trash') { MSC.trash = e.target.checked; MSC.tItems = null; MSC.pick = null; ms_clDraw(); } });
// 2.607.0 (#4612): a long press (phone) / a right click (computer) on a row opens its menu: the name, "Select" (starts the
// selection with it), Open; while the selection runs a long press ticks the row (the click after it does nothing)
function ms_clRowMenu(r) {
  const id = +r.dataset.clopen, c = (MSC.items || []).find(x => x.id === id); if (!c || MSC.trash) return false;
  menu(r, [...cm_selHead(cdn_label(c), () => ms_clClick(id, false)), {label: tr('Open'), icon: 'eye', fn: () => go('client/' + id)}]);
  return true;
}
const ms_clLp = cm_bind('#view .msclients .ctrow[data-clopen]', ms_clRowMenu, r => { if (!MSC.pick) return false; ms_clClick(+r.dataset.clopen, false); return true; });
document.addEventListener('click', e => {
  if (S.route.mod !== 'clients') return;
  const bb = e.target.closest('#ct-sbar [data-clb]');
  if (bb) { ms_clAct(bb.dataset.clb); return; }
  const o = e.target.closest('#view [data-clopen]');
  if (o) {
    e.preventDefault();
    if (ms_lpRecent(ms_clLp)) return;  // the click that ends a long press
    if (MSC.pick || (ms_modClick(e) && !isMobile())) { ms_clClick(+o.dataset.clopen, e.shiftKey); return; }
    go('client/' + o.dataset.clopen); return;
  }
  const b = e.target.closest('#view [data-mscl]'); if (!b) return;
  const k = b.dataset.mscl;
  if (k === 'pick') { MSC.pick = MSC.pick ? null : new Set(); MSC.last = null; ms_clDraw(); }
  else if (k === 'trest' || k === 'tpurge') ms_clTrashAct(k, +b.dataset.id);  // 2.272.0 D (#3029)
  else if (k === 'back') navUp('clients');  // 2.743.0 (#5235)
  else if (k === 'siteadd' && CLV.data?.id) clientModal(null, {org_id: CLV.data.org_id ?? null, parent_id: CLV.data.id});  // #7292
  else if (k === 'fold') {  // 2.435.0 A (#3600): fold a block open / closed (kept per person)
    const bk = b.dataset.k; lyOptSet('clients', bk, 'open', !ms_clOpen(bk)); ms_clDraw();
    setTimeout(() => $(`#view [data-mscl="fold"][data-k="${bk}"]`)?.focus({preventScroll: true}), 0);
  }
  else if (k === 'cmenu' && CLV.data?.id) {
    const c = CLV.data;
    menu(b, [{label: c.archived ? tr('Restore') : tr('Archive'), icon: c.archived ? 'undo' : 'archive', fn: async () => {
      // #7292: a main client asks whether its locations go into the archive too
      const ids = c.archived ? [c.id] : await ms_clWithSites([c.id], n => trn('Archive its {0} location too?', 'Archive its {0} locations too?', n), tr('Archive them too'), x => !x.archived);
      let j; try { j = await ms_clSend({action: c.archived ? 'unarchive' : 'archive', ids}); } catch (x) { toast(x.message || ''); return; }
      await ms_clAfter();
      const msg = c.archived ? trn('{0} client restored', '{0} clients restored', ids.length) : trn('{0} client archived', '{0} clients archived', ids.length);
      if (j.changed) ms_hist(msg, msg, async () => { await ms_clSend({action: 'restore', items: j.undo}); await ms_clAfter(); }, async () => { await ms_clSend({action: c.archived ? 'unarchive' : 'archive', ids}); await ms_clAfter(); });
    }},
    {label: tr('Duplicate'), icon: 'copy', fn: () => ms_clCopy(c, false)},  // #7295
    {label: tr('Add location'), icon: 'mappin', fn: () => ms_clCopy(c, true)},  // #7295 (#7292): of a location = of its main client
    ofm_can(c.org_id ?? null) ? {label: tr('Move to another workspace…'), icon: 'brief', fn: () => ofm_clients([c.id])} : null,  // (#2049)
    typeof tpo_on === 'function' && tpo_on() ? {label: tr('Find a date…'), icon: 'users', fn: () => tpo_forClient(c)} : null,  // 2.98.0 A (#1953)
    formsOn() && !S.me?.kid ? {label: tr('Copy questionnaire link for this client'), icon: 'copy', fn: () => fq_clientLink(c, b)} : null,  // 2.102.0 C (#2201)
    kp_menuItem(c)]);  // 2.120.0 B (#2088)
  }
});
// #7295: "Duplicate" / "Add location" of the client page: one call (POST /api/clients/<id>/copy: name, address, country, rate,
// icon, colour, note; the contact persons only when ticked), one undo step (the new client into the trash, redo = back out of
// it), then the new client opens for editing (a location: its name addition to fill in)
async function ms_clCopy(c, site) {
  const nk = (c.contacts || []).length, main = site && c.parent_id ? clientById(c.parent_id) || null : null;
  let j = null;
  const ok = await askDialog({title: site ? tr('Add a location of {0}', cdn_label(main || c)) : tr('Duplicate {0}', cdn_label(c)),
    html: `<p>${esc(site ? tr('The location takes over the address, country, hourly rate, icon, colour and note. Its name addition stays empty for you to fill in.')
      : tr('The copy takes over the name, address, country, hourly rate, icon, colour and note. Projects, documents, hours, budget and links stay with the original.'))}</p>`
      + (nk ? `<label class="chk"><input type="checkbox" id="clcp-k"> ${esc(trn('Take the contact person along ({0})', 'Take the contact persons along ({0})', nk))}</label>` : ''),
    ok: site ? tr('Add location') : tr('Duplicate'),
    submit: async () => {
      try { j = await rawFetch('POST', `/api/clients/${c.id}/copy`, {as_location: site, contacts: !!$('#clcp-k')?.checked}); return true; }
      catch (x) { toast(x.message || ''); return false; }
    }});
  if (!ok || !j) return;
  const nid = j.id, msg = site ? tr('Location added') : tr('Client duplicated');
  await ms_clAfter();
  go('client/' + nid);
  clientModal(j);
  ms_hist(msg, msg, async () => {  // after the jump: the message belongs to the new client's page
    await rawFetch('DELETE', `/api/clients/${nid}`);
    await ms_clAfter(); if (S.route.mod === 'clients' && +S.route.client === nid) go('client/' + c.id);
  }, async () => { await ms_clSend({action: 'untrash', ids: [nid]}); await ms_clAfter(); });
}
kb_on('view:clients', 'Escape', () => {  // 2.630.0 (#4510): key registry (keys.js): the view's Esc, after an open menu / dialog and before the detail
  if (!(MSC.pick && S.route.mod === 'clients' && !$('.modal, .lightbox') && $('#pop')?.classList.contains('hidden'))) return false; ms_clEnd();
});

// ---- 2.97.0 C (#2049): office data into another workspace (office/officemove.py, POST /api/office/move-space): clients (with
// their contact persons and drafts), drafts, trips, templates. Issued documents stay where they were issued; on request a
// read-only copy goes into the target's archive. One undo step (the same move back); redo = the move again.
const ofm_on = () => typeof officeOn === 'function' && officeOn() && S.me?.kind !== 'agent';
const ofm_can = from => ofm_on() && smv_can(from);
function ofm_officeFrom() {  // the workspace of the office shown (org id | null = the personal office)
  if (typeof OFC !== 'undefined' && OFC.info?.personal) return null;
  const w = typeof wsCur === 'function' ? wsCur() : 'private', ws = S.me?.workspaces || [];
  return w.startsWith('org:') ? +w.slice(4) : w === 'all' && ws.length === 1 ? ws[0].id : null;
}
async function ofm_move({what, ids, from, label, after, only = null}) {  // 2.356.0 A (#2926): only = the possible targets
  const req = (to, extra) => rawFetch('POST', '/api/office/move-space', {what, ids, to: smv_ws(to), ...extra});
  const r = await smv_open({what: label, from, only, option: ['clients', 'office'].includes(what) ? {label: tr('Take issued documents along as a read-only copy')} : null,
    check: (to, _pl, opt) => req(to, {dry: 1, copy_issued: opt ? 1 : 0}),
    run: async (to, _pl, opt) => { try { return {...await req(to, {copy_issued: opt ? 1 : 0}), to, opt}; } catch (e) { toast(e.message); throw e; } }});
  if (!r || !r.ok) return null;
  let mid = r.move_id;
  await after();
  const e = histAdd({label: tr('Moved {0}', label), ids: [], snaps: [], lids: [], wsp: r.space,
    undo: async () => { await rawFetch('POST', '/api/office/move-space', {undo: mid}); await after(); return {skipped: []}; },
    redo: async () => { const b = await req(r.to, {copy_issued: r.opt ? 1 : 0}); mid = b.move_id; await after(); return {skipped: []}; }});
  histToast(tr('Moved to {0}', wsName(r.space)), e);
  return r;
}
function ofm_clients(ids) {
  const sel = ids.map(i => (MSC.items || []).find(c => c.id === i) || (CLV.data?.id === i ? CLV.data : null)).filter(Boolean);
  if (!sel.length) return;
  const from = sel[0].org_id ?? null;
  if (sel.some(c => (c.org_id ?? null) !== from)) { toast(tr('Select items of one workspace')); return; }
  ofm_move({what: 'clients', ids: sel.map(c => c.id), from, label: sel.length === 1 ? qn(sel[0].name) : trn('{0} client', '{0} clients', sel.length),
    after: async () => { if (MSC.pick) ms_clEnd(); await ms_clAfter(); }});
}
// ---- 2.149.0 F (#2518): the e-mail filing (hubmail.js) loads on demand (lazyload.js module hubmail). What the start draws stays
// at start: the link to the mail a task / an event was made from and its click (2.563.0, #4742: moved to lazyload.js, this file
// loads on demand now), the entry in Office > Clients here; the client's card and the project page draw their mail section once
// it has loaded (nothing before the first answer, as before)
// the entry in Office > Clients
const hbm_hubBtn = () => `<a class="btn sm" href="#mailhub" title="${esc(tr('E-mail filing'))}">${ic('inbox', 's')}<span class="cdl">${tr('E-mail filing')}</span></a>`;

// ---- 2.154.0 C (#2192): data protection sheets of the client (office/privacy.py; office admins, else no section / filter):
// the section with each sheet's status and the filter of the list; the dialogs and the menu live in office_doctpl.js
const DSB = {cl: null, all: null, f: '', no: false};  // no = the server said no (a member): no filter
function dsb_clHtml(c) {
  if (typeof officeOn !== 'function' || !officeOn()) return '';
  if (DSB.cl?.id !== c.id) { if (!DSB.cl?.busy) { DSB.cl = {id: c.id, busy: 1}; dsb_clLoad(c.id); } return ''; }
  const ss = DSB.cl.sheets; if (!ss) return '';
  const li = x => `<li data-dsb="row" data-id="${x.id}">${ic('shield', 's')} <b>${esc(x.kind_label)}</b> <span class="rotag dsb-st dsb-st-${esc(x.status)}${x.review ? ' dsb-rev' : ''}">${esc(x.gen_status === 'draft' ? tr('Draft') : x.status_label)}</span><button data-rowmenu="dsbsec" type="button" class="iconbtn" data-dsb="menu" data-id="${x.id}" aria-haspopup="menu" aria-label="${esc(tr('More'))}: ${esc(x.kind_label)}" title="${esc(tr('More'))}">${ic('dots', 's')}</button>${dsb_replyHtml(x.reply)}</li>`;
  return `<div class="ctsec dsbsec"><h4>${tr('Data protection')}</h4>${ss.length ? `<ul class="ctlinks">${ss.map(li).join('')}</ul>` : ''}<button type="button" class="btn sm" data-dsb="new" data-cl="${c.id}">${ic('plus', 's')} ${tr('Data protection sheet')}</button></div>`;
}
// 2.209.0 C (#2589): the newest reply mail that was not filed (e.g. a revocation) at its sheet -- the customer's text, escaped
function dsb_replyHtml(r) {
  if (!r) return '';
  const when = new Date(r.at || '').toLocaleDateString(LOCALE(), {dateStyle: 'medium'});
  return `<div class="dsb-reply muted"><span>${esc(tr('Reply of {0}', when))}${r.from ? ` · ${esc(r.from)}` : ''}${r.subject ? ` · ${esc(r.subject)}` : ''}</span>${r.text ? `<blockquote>${esc(r.text)}</blockquote>` : ''}</div>`;
}
async function dsb_clLoad(id, q) {  // #7399: q = no draw (ms_clFetch draws once)
  let ss = null;
  try { ss = (await rawFetch('GET', `/api/office/privacy-sheets?client_id=${id}&brief=1`)).sheets || []; } catch { ss = null; DSB.no = true; }  // quiet: members (403) see no section
  DSB.cl = {id, sheets: ss};
  if (!q) ms_clDraw();
}
const dsb_clReload = () => { DSB.cl = null; DSB.all = null; ms_clDraw(); };
// the list filter: the newest sheet of each kind counts (open = not yet signed / handed over)
function dsb_clFilter() {
  if (typeof officeOn !== 'function' || !officeOn() || DSB.no) return '';
  const o = [['', tr('Data protection status')], ['dpa', tr('DPA open')], ['consent', tr('Consent open')], ['info', tr('Information not handed over')], ['review', tr('To check')]];
  return `<select id="mscl-dsb" class="dsbflt" aria-label="${esc(tr('Data protection status'))}">${o.map(([k, l]) => `<option value="${k}" ${DSB.f === k ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
}
function dsb_clPass(c) {
  if (!DSB.f) return true;
  if (!DSB.all) return false;
  const ss = DSB.all.filter(x => x.client_id === c.id);
  if (DSB.f === 'review') return ss.some(x => x.review);
  const x = ss.find(y => y.kind === DSB.f);  // newest first
  return !!x && (DSB.f === 'info' ? x.status === 'open' : ['open', 'sent'].includes(x.status));
}
document.addEventListener('change', async e => {
  if (e.target.id !== 'mscl-dsb') return;
  DSB.f = e.target.value;
  if (DSB.f) { try { DSB.all = (await rawFetch('GET', '/api/office/privacy-sheets?brief=1')).sheets || []; } catch { DSB.f = ''; DSB.no = true; } }  // fresh on every choice (another device may have changed a sheet)
  ms_clDraw();
});
ms_rowMenu('#view .dsbsec li[data-dsb="row"]', async r => { await loadModule('office'); dsb_menu(r, (DSB.cl?.sheets || []).find(x => x.id === +r.dataset.id)); });  // 2.452.0 (#3836)
document.addEventListener('click', async e => {
  const b = e.target.closest?.('#view [data-dsb]'); if (!b) return;
  if (b.dataset.dsb === 'row' && (!isMobile() || e.target.closest('a,button'))) return;  // 2.452.0 (#3836): on a phone a tap on the row opens its menu, the dots are hidden
  await loadModule('office');
  if (b.dataset.dsb === 'new') dsb_new(+b.dataset.cl);
  else dsb_menu(b, (DSB.cl?.sheets || []).find(x => x.id === +b.dataset.id));
});

// #7290: the building block list beside detail (.lsd2, start-lsd-4553.css) gets a grip between list and detail: drag it to
// make the list wider or narrower, arrow keys (Shift: 4 rem), Home / End = narrowest / widest, Enter or double-click = the
// standard width. From --w-leiste-min (14rem) to half the pair; remembered per page and device (localStorage lsdW.<page>, in
// rem). For every two-column .lsd2 (contacts, clients, quotations / invoices), not on a phone or a narrow content area (one
// column) and not for the receipts' one-column list (.lsdone). Loaded with contacts, clients and office (lazyload.js LD_NEED).
const lsg_key = () => { const r = S.route || {}; return 'lsdW.' + (r.mod || '') + (r.mod === 'office' && r.tab ? '.' + r.tab : ''); };
const lsg_rem = () => parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
function lsg_lim(p) {
  const min = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--w-leiste-min')) || 14;
  return [min, Math.max(min, Math.floor(p.clientWidth / lsg_rem() / 2 * 4) / 4)];
}
function lsg_set(p, w, save) {  // w in rem; null = the standard width of the building block
  const [min, max] = lsg_lim(p);
  if (w == null) { p.classList.remove('lsdset'); p.style.removeProperty('--lsdW'); if (save) LS.del(lsg_key()); }
  else { w = Math.round(Math.max(min, Math.min(max, w)) * 4) / 4; p.style.setProperty('--lsdW', w + 'rem'); p.classList.add('lsdset'); if (save) LS.set(lsg_key(), w); }
  lsg_place(p);
}
function lsg_place(p) {
  const g = $(':scope > .lsdgrip', p), l = $(':scope > .lsdl', p); if (!g) return;
  // #7376: without the list (a phone or a narrow area draws only the open card) the grip is hidden too, never at the left edge
  const two = !!l && getComputedStyle(p).gridTemplateColumns.trim().split(/\s+/).length > 1 && [...p.children].filter(x => x !== g).length > 1;  // the detail: .lsdr or the card (.ctcard)
  g.hidden = !two; if (!two) return;
  const gap = parseFloat(getComputedStyle(p).columnGap) || 0, w = l.getBoundingClientRect().width;
  g.style.left = (l.offsetLeft + w + gap / 2 - g.offsetWidth / 2) + 'px';
  const [min, max] = lsg_lim(p);
  g.setAttribute('aria-valuemin', String(min)); g.setAttribute('aria-valuemax', String(max)); g.setAttribute('aria-valuenow', String(Math.round(w / lsg_rem() * 4) / 4));
}
let lsg_ro = null;
function lsg_sync() {
  for (const p of $$('#view .lsd2:not(.lsdone)')) {
    if (!document.body.classList.contains('lsgdrag')) {  // a redraw (morph) may drop the class and the variable: the stored width again
      const v = LS.get(lsg_key(), null), on = Number.isFinite(v);
      if (on && p.style.getPropertyValue('--lsdW') !== v + 'rem') p.style.setProperty('--lsdW', v + 'rem');
      if (!on && p.style.getPropertyValue('--lsdW')) p.style.removeProperty('--lsdW');
      if (p.classList.contains('lsdset') !== on) p.classList.toggle('lsdset', on);
    }
    if (!$(':scope > .lsdgrip', p)) {
      p.insertAdjacentHTML('beforeend', `<div class="lsdgrip" tabindex="0" role="separator" aria-orientation="vertical" aria-label="${esc(tr('Width of the list'))}" title="${esc(tr('Drag to resize · double-click: default size'))}"></div>`);
      if (!p._lsg) { p._lsg = 1; lsg_ro?.observe(p); }
    }
    lsg_place(p);
  }
}
if (typeof ResizeObserver !== 'undefined') lsg_ro = new ResizeObserver(es => { for (const e of es) if (e.target.isConnected) lsg_place(e.target); });
domReady(() => { const v = $('#view'); if (!v) return; let q = 0; new MutationObserver(() => { if (!q) q = requestAnimationFrame(() => { q = 0; lsg_sync(); }); }).observe(v, {childList: true, subtree: true}); lsg_sync(); });
document.addEventListener('pointerdown', e => {
  const g = e.target.closest?.('#view .lsd2 > .lsdgrip'); if (!g || e.button !== 0) return;
  const p = g.parentElement, l = $(':scope > .lsdl', p); if (!l) return;
  e.preventDefault(); try { g.setPointerCapture(e.pointerId); } catch { /* gone */ }
  const x0 = e.clientX, w0 = l.getBoundingClientRect().width, rem = lsg_rem(); let w = null;
  g.classList.add('drag'); document.body.classList.add('lsgdrag');
  const mv = rafThrottle(x => { w = (w0 + x - x0) / rem; lsg_set(p, w); });
  const m2 = ev => mv(ev.clientX);
  const up = () => { g.removeEventListener('pointermove', m2); mv.flush(); g.classList.remove('drag'); document.body.classList.remove('lsgdrag');
    if (w != null && Math.abs(w * rem - w0) > 2) lsg_set(p, w, true); };
  g.addEventListener('pointermove', m2); g.addEventListener('pointerup', up, {once: true}); g.addEventListener('pointercancel', up, {once: true});
});
document.addEventListener('dblclick', e => { const g = e.target.closest?.('#view .lsd2 > .lsdgrip'); if (g) { lsg_set(g.parentElement, null, true); announce(tr('Default width')); } });
document.addEventListener('keydown', e => {
  const g = e.target.closest?.('#view .lsd2 > .lsdgrip'); if (!g) return;
  const p = g.parentElement, l = $(':scope > .lsdl', p); if (!l) return;
  const st = e.shiftKey ? 4 : 1, w = l.getBoundingClientRect().width / lsg_rem(), [min, max] = lsg_lim(p);
  const to = {ArrowLeft: w - st, ArrowRight: w + st, Home: min, End: max}[e.key];
  if (to != null) { e.preventDefault(); e.stopPropagation(); lsg_set(p, to, true); announce(tr('{0} rem', String(Math.round(l.getBoundingClientRect().width / lsg_rem() * 4) / 4))); }
  else if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); lsg_set(p, null, true); announce(tr('Default width')); }
});
