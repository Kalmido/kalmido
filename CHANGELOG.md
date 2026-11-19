# Changelog

All notable changes to Kalmido are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Kalmido uses
[semantic versioning](https://semver.org/): every published change gets at least a new patch version, new features a
minor one. Releases in which operators have to do something carry a fixed section "Action needed"; the update notice
in Settings > Help shows that section of the target version.

## Older versions

- [2.1300-2.1399](docs/changelog/2.1300-2.1399.md)
- [2.1200-2.1299](docs/changelog/2.1200-2.1299.md)
- [2.1100-2.1199](docs/changelog/2.1100-2.1199.md)
- [2.1000-2.1099](docs/changelog/2.1000-2.1099.md)
- [2.900-2.999](docs/changelog/2.900-2.999.md)
- [2.800-2.899](docs/changelog/2.800-2.899.md)
- [2.700-2.799](docs/changelog/2.700-2.799.md)
- [2.600-2.699](docs/changelog/2.600-2.699.md)
- [2.500-2.599](docs/changelog/2.500-2.599.md)
- [2.400-2.499](docs/changelog/2.400-2.499.md)
- [2.300-2.399](docs/changelog/2.300-2.399.md)
- [2.200-2.299](docs/changelog/2.200-2.299.md)
- [2.100-2.199](docs/changelog/2.100-2.199.md)
- [2.0-2.99](docs/changelog/2.0-2.99.md)
- [1.x](docs/changelog/1.x.md)

## [2.1441.0] - 2026-11-19

Package 2.1435 (Bündel: Bündel: Büro: Aussteller-Schlüssel - Kunden per externer K, Büro: Zustell-Zustand der Rechnungs-Mail am Beleg , CI: Merge-Queue-Lauf).

### Added
- #6819: Invoices can be issued as paid in the finalise dialog: paid date and method instead of bank details, QR code and due date; the payment is booked with it, the e-invoice carries the matching payment means.
- #6819: An invoice issuer's bank account (holder, IBAN, BIC) and its required payment reference appear on the PDF, in the GiroCode and in the e-invoice (BT-83/84/85); an RF reference with a wrong check digit is refused.
- #6820: Documents remember the delivery state of their e-mail (sent / refused by the mail server / marked "Delivery failed" by hand): tag in the list, note on the document, filter "Delivery failed", history entry; the issuer read routes return `mail {state, at}`.
- #7296: Contacts: "Add a colleague at the same company" in a contact's menu opens a new contact with the company, department, business address, website, landline and address book filled in.
- #7292: Clients with locations: a client can belong to a main client ("Belongs to"); the list shows locations under their main client, the main client's card sums hours, amounts and budget of all locations, pickers show "Main client · Location"; parent_id in API v1 and MCP.

### Changed
- #7291: Quotations: the producing / project management line counts like a position; the subtotal appears only before a surcharge, included raw data or the discount and includes it. Quotations already sent keep their lines.

Package 2.1440 (Bündel: Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Sammelpaket: Aufgaben ).

### Developer
- #5195 CI red p2139_b_api: the channel mention reaches the team agent through a project that opens it to the sender (rule of #6454).
- #5719 CI red p2351_f_review: the accounting role gets 403 on the Documents tree (rule of #6613).
- #7213 #5037 CI red p2125_d_demo: the demo shim answers GET /api/agent-rules.

Package 2.1437 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Added
- One shared grip to resize columns, dividers and window corners (static/js/grip.js, loaded on demand): mouse, touch and keyboard, double-click for the default size, sizes kept per device or through hooks, old stored sizes taken over; no existing grip moved yet (#7293)

### Changed
- The logo always leads to Start; the workspace is switched only with the chip in the header, which is now always shown, also under "All workspaces" (#7299)
- Office without a chosen workspace: "Which workspace? The office always belongs to a workspace." with a button per workspace that has an office (#7297)
- Idempotency keys keep the whole answer only for tasks, habits, time, notes and chat; other routes keep a short answer (ok, ids, updated_at), routes that hand out a secret keep none (#6558)

### Fixed
- The office in a chosen workspace opens with its full menu: every office request names its area, the menu cache is per office area, a workspace switch that could not be saved is taken back with a note, never a silent jump to "All workspaces"; also in the split view (#7297)
- Self-hosting start messages: a wrong number in .env gives a warning with the variable's name instead of a traceback, wrong PORT/TZ a FATAL line, unknown KALMIDO_* variables, too old PostgreSQL and missing extensions are named; an alert when the virus scanner stays unreachable; SMTP without sender, test mail errors, a full disk on upload (507) and a skewed 2FA clock are told in words (#6615)
- Tests: p2661_b_ui knows time.js in the workspace guard (red since 807012f595, #6722)

Package 2.1436 (Bündel: Bündel: Büro: Aussteller-Schlüssel - fertige PDF und XML f, Sammelpaket: Aufgaben ohne Paket (Dispatcher), Produkt- und UI-Regeln al).

### Added
- #6818 Invoice issuer keys fetch the archived PDF or e-invoice XML of their own finalised documents, byte for byte with its SHA-256 in the header `X-Content-SHA256` (`GET /api/v1/issuer/docs/{id}/file?kind=pdf|xml`; ZUGFeRD = the embedded XML, XRechnung = the original XML; a draft or a missing archive file 409 `not_final`, never rendered anew; own rate 10 per minute and issuer, 429; one log line `issuer_read` per fetch; corrections inheriting the issuer included).
- #6385 Admins are alerted when the e-mail server keeps failing: every mail over the instance's SMTP counts in one place, the admin alarms get the branches `smtp` and `mail` (sending and the e-mail import).
- #7262 The product and UI rules every package keeps stand in docs/dev/produkt-regeln.md; `tools/check_rules.py` checks the ones seen in the code text (rules `window-open`, `wording`, `emoji`).

### Changed
- #6344 Ctrl+Z and the undo arrow take back only this window's steps and steps from other devices of the last 2 minutes; otherwise "Recent steps" opens with that step marked and its button focused. Steps over an API key are skipped (`GET /api/undo?skip_api=1`), the message names the device, the arrow's tooltip names exactly the step its click takes back.
- #6385 Organisation admins see a general notice while sending e-mails is disturbed (the same for every address); the instance admin sees "e-mail not sent" per invitation in the people list.

### Fixed
- #6531 A file of a mail, a reply by mail, a request mail, a documents mail or a public form that is not filed (storage full, virus, too large, locked list) is no longer dropped silently: the mail stays in the mailbox, the task (or reply) names the file and why, and the owner gets a News item (also for a documents mail without a task). A mailbox rule keeps a mail as soon as any of its files was refused (state `skipped`).
- #6385 Queued e-mails (invitations, bookings, password resets, security mails, forms, portal, tickets, appointment invitations, polls) are tried again after a passing server failure instead of being lost, without sending a list twice; an invitation counts as sent only once its e-mail went out; a finally failed booking confirmation or invitation tells who triggered it in the News.
- `tools/check_globals.py` says Why / Instead through lintmsg like every other check.

Package 2.1441 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Fixed
- #7298 Clients: a client added under "All workspaces" no longer vanishes from the list. "New client" takes the area the
  office shows, else the only workspace where Clients is on for you; with several the dialog asks for the workspace (required).
  The toast names the workspace. The server never puts a client without `org_id` silently into a workspace where Clients is
  off for the person (area / module switch, the organisation's switched-off areas, the card's cap): the only such workspace,
  else `400` with `code: ws_choose` and the workspaces (also `POST /api/v1/clients`). The contacts editor under "All" offers
  no address book of a workspace where Contacts is off.

## [2.1434.0] - 2026-11-19

Package 2.1433.0 (Bündel: Gegenlesen-Hinweise job/5148: 2 offene Hinweise be, Sammelpaket: Aufgaben ohne Paket (Dispatcher), Bündel: Sammelpaket: Aufgaben ohn).

### Changed
- #7142 Agents without a chosen control level follow the circle rule at level "free": every step still runs without a card, but writing into a wider or public circle, a chat message or a job to a person outside the circle needs a card; status text, progress line and job words reach non-readers empty. A deletion keeps going without the circle check. For every level, a new list of the agent without folder or family and its own private saved view count as read by nobody else. Agent docs (docs/AGENTS.md, docs/AGENT-SETUP.md, mcp/CLAUDE.template.md) and the control dialog say so.
- #6604 Organisation encryption: before a new recovery key is made, the question says that archives downloaded before open only with the earlier key (Cancel is the focused button, the step itself red); after the change the key dialog offers "Create export" for the same organisation or office. No new one-way step: making a new recovery key was already irreversible, the package only warns about it.
- #7181 Background queue: mail and push jobs keep one run (they catch their own send errors; the docs no longer promise 3 runs).

### Fixed
- #6953 Accounting: folders below the documents folder that hold a receipt can be opened (folder only); single check and listing need the receipt's organisation alike; every folder listing (web, API v1 list and folder with children) uses one filter (store.fs_children_visible). Office figures show the weighted pipeline only with the pipeline right; a project's acceptance links show address and signer data by the same rule as quotations; the office log is closed to accounting by prefix.
- #7181 Background queue: on stop the running jobs are released before the stop hooks run (a slow chat note can no longer cost the release); a server agent run taken for lost tells its person once, without naming a server restart, and its own end adds no second message; the "oldest due job" alarm counts only known job kinds and no export waiting behind full long slots.

Package 2.1434.0 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Eigene Formate nicht rundreisefähig: Listen-CSV ko).

### Added
- Floating chat window: resize it by a grip at its top left corner (plus the left and top edges); arrow keys on the focused grip, Home / End = smallest / largest, Enter or double-click = default size; at least about 18 x 20 rem, at most the window; remembered per device next to its position. Phone and full screen unchanged (#7289)
- List beside detail (contacts, clients, quotations / invoices): a grip between the list and the open entry makes the list wider or narrower; from 14 rem to half the area, remembered per page and device, arrow keys, double-click or Enter = standard width; not on phones or narrow content (one column) (#7290)

### Changed
- "Waiting for me" > Blocked shows only what the person can settle: tasks with a waiting note as before, tasks waiting on another task only when assigned to the person. Unassigned tasks of one's own lists that only wait on another task drop out there (the daily briefing keeps them); count and tile follow (#7284)

### Fixed
- Notifications: notify() itself turns a disabled account away (no push, no channel message), a second line behind every caller; the weekly rotation, the contact care push and the fixed-time reminder are tested with a disabled account (#6486)
- Own formats round-trip: re-importing the list CSV keeps done tasks done (state from "Status", the date column as done date), sub-tasks under their parent ("Parent task" / "Hauptaufgabe") and the priority, in every app language; the Markdown import reads the export's tail "(due …, high priority, repeats …)" so titles stay whole; vCard 3.0 marks a company with X-ABShowAs:COMPANY / X-KIND:org and the import reads both (also Apple Contacts cards). Suite p6587_roundtrip_api (new) (#6587)

## [2.1432.0] - 2026-11-19

Package 2.1428 (Bündel: Bündel: Weich rot: p290_ui, Weich rot: perf_ui, Weich rot: p2546_b_locked u. 3 weitere, Weich rot: p2925_a_words, Weich rot: p2240_u).

### Fixed
- Settings > Account: "Sign out" and "App server" stay at the very end of Account, outside the folded "Delete account" section (since the folded sections of #6827 they sat hidden inside it) (#7061).
- Settings: "For advanced users" appears once per tab again; the server admin's hints (mail not set up in Integrations, passkey hint in Account) fold under their own "For server admins", and Account no longer nests the Access fold inside another fold (#7230).
- Phone: switching the workspace from the workspace menu keeps the open sidebar open and shows the new workspace, as decided in #3847 (#7235).
- Ticking off a task: the list waits for the fading row to finish folding before it redraws, so it no longer jumps on a slow device or a late frame (#7231).
- German texts name the office settings "Einstellungen > Firma & Büro" in the e-invoice and invoice issuer key hints; "Briefpapier" instead of "Briefkopf" (#6861).
- Test suites made robust for the CI or moved to the intended app state: p290_ui (#6665), perf_ui (server warm-up before measuring, budget unchanged, #6666), p2190_ride_ui (tap trace, #7232), p2320_a_ui (#7233), p255_d_ui (#7237), p2448_a_lang (#7234), p2525_a_dataattr_ui (#7236), p2615_c_guard (#7238), p7115_dev_profile (reads static/i18n/neu like the app, `kt.lang`, #7239).

Package 2.1423 (Bündel: Weich rot: admin_alerts, Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Added
- Calendar subscriptions: a subscription that could not be fetched for over 24 hours is marked out of date - a warning mark with "Not updated since …" replaces the link mark at its events, a line in the event popover, in the subscription list under "Calendars…" and in the booking page settings; one push + News item (Integrations) when it turns out of date; its old events keep counting as busy for booking page, free/busy and day plan (#6551)

### Changed
- Agents: a proposal a team agent sends to one person (time, shoot, import, object, sheet tasks, general, request, contract notice, layout, rules) carries its title in News and push only for a person inside the agent's circle; outside it reads "{agent} has a proposal for you"; checked at the one output point instead of per route (#7159)

### Fixed
- Own event series starting long ago (e.g. 1900) are no longer walked from their start on every calendar query: the start moves to the shown range by whole periods (daily, weekly, monthly, yearly), COUNT rules are walked with a bound (#6727)
- Tests: admin_alerts waits for both capped switch alerts before the summary part (CI red, #7104); p2410_e_api uses a real chat event with its seq so the team agent gets its request token (main red, #7217)

Package 2.1427 (Bündel: Büro: Aussteller-Schlüssel - Rechnungs-Entwürfe mi).

### Added
- #6701 Invoice issuer drafts (stage 1d of the platform billing): `POST /api/v1/issuer/invoices` makes an invoice draft in the issuer's own number range through the person's own functions (no date, number, range, currency, IBAN or link in the request; at most 50 positions, unit prices up to 4 places, texts with an IBAN, web or e-mail address 400). Kalmido computes each line rounded half up to the cent and the tax per rate on the sum; `expect` must match (409 `totals_mismatch`, nothing made). `client_ref` is kept with the hash of the normalised request: the same request again 200 (also after a person's correction, also at a day's limit), another content 409 `ref_conflict`, withdrawn or purged 410 `withdrawn` for good. Limits `day_docs` / `open_drafts` (429), `over_limit` flag with an alarm over `max_gross` / `day_gross`, flags `client_new`, `client_changed`, `vat_territory` (Büsingen, Heligoland, Canary Islands, Ceuta, Melilla, Livigno, Campione, Mount Athos, Åland, French overseas). The `wish` (paid, sending, payee with `payee_check` - 409 `payee_mismatch` -, reference, due days or due date), `vat_check` and `business_check` are stored sealed, never printed, never proof; a due date under 7 days after the invoice date stops finalising. Read routes with a fixed field list (`GET /api/v1/issuer/docs?changed_since=&cursor=`, `/docs/{id}`, `/docs/by-ref/{client_ref}`; corrections and a person's numbered documents of the range as `origin: manual`), the PDF preview only while the draft is as delivered (409 `edited_by_human`), `POST /docs/{id}/withdraw` into the office trash (`day_withdraw`). Daily alarm for drafts waiting longer than `review_wait_h`. Migration 6701 (same id as the earlier build, free on main): `office_docs.issuer_id`, `issuer_wish` (sealed), `issuer_rev`, `ref_sha256` (additive).
- #6701 The issuer routes' refusal notices (limit, payee mismatch) go through one helper, `isc_notice`.
- #6701 Office: the invoice editor of an issuer's draft shows "Made by the invoice issuer …" with its client_ref and the outside system's unconfirmed statements (paid on … by …, sending wished, payment terms, account, VAT ID check - no proof, over limit, VAT territory); nothing is booked or sent from them. The invoice list gets a filter "number range or invoice issuer" (main range, each range, from invoice issuers, one issuer; API `?range=` / `?issuer=any|<id>`).

### Changed
- #6701 Agent draft routes (quotation, invoice, invoice from a quotation, reminder): the same `client_ref` with another body is now 409 `ref_conflict` instead of silently returning the first draft. Office documents made by an issuer carry `origin: "issuer"`, `untrusted: true` for agents (rules template, in-app rules, docs/AGENTS.md).
- #6701 An issuer's draft never becomes a series template (409), its client can only change to another client of the same issuer (409), a copy never keeps the issuer, a person's correction of an issuer's invoice inherits it.

Package 2.1432 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- #6808: From 2027-01-01 (server setting `KALMIDO_REQ_MAIN_FROM`) the own long-lived token of every team agent reaches only its channel (events, status, jobs, sending messages), also when its starter never asked for a request token; until then *Settings > Agents* names the day on such an agent (run the setup command again). `GET /agent/chats` now needs the request token for a team agent that works per request (`403 request_token_needed` with its own token); the reference starter reads the answered message with the run's token.
- #6399: Live updates: a change in office, files, contacts, calendars, tables, wiki or an agent's status now wakes only the open tabs of the people who can see it (the writer's organisations, shared lists and shares) instead of every tab of every organisation.
- #6196: One offline message everywhere: "Only available online." also in account, settings, bell and the app frame; the old sentence is gone.
- #7169: Lint: `tools/ruff_baseline.py --update` only lowers the baseline, a new finding stays red.

### Fixed
- #6639: Live updates: a focused drop-down no longer blocks changes from other devices; a field left without input for a minute lets them through too, the open task panel follows without closing the keyboard.
- #6831: `tools/check_globals.py` explains its red message with Why / Instead (lint suite p21403_c_suppress).

Package 2.1429 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- Office rights: in a company a person creates herself (Create company, or moving the private office into a company) a new member or read-only person starts in the office group "Staff" (their own receipts, travel expenses, drives, entertainment receipts and times) instead of the silent "Previous access" with quotations, invoices, clients and the office settings; the admins give more under Office settings > Rights. The start is written to the rights log ("joined and starts in the default group"); such a company offers no "Previous access" on the rights page. Organisations of before and the ones the server admin creates keep "Previous access" for their new members (#6527).
- Invite people: below the role a sentence says what the role may in the office of this organisation and that projects are shared one by one (#6527).
- Quote of the day on the sign-in page: the author ("— Hugo Ball") stands in the same line right behind the quote's last word; the name never breaks, it moves to the next line as a whole (#7228).

### Fixed
- Phone: the workspace chip in the header shows the organisation's letter or symbol again; only its name is hidden (the chip was empty) (#7210).
- Phone at 320 px: the PDF bar of the file / receipt view fits its one row (zoom out / in and the percentage give way, a pinch zooms; Width, Whole page, Pages and Full screen stay); on Today the task block's "…" no longer lies over "Columns" of the strip of shown fields (#7211).

## [2.1426.0] - 2026-11-19

Package 2.1422 (Bündel: Versionsdaten beim Abbild-Bau ableiten statt Versi, Sammelpaket: Aufgaben ohne Paket (Dispatcher), Bündel: Wissen-Bildfreigabe am Au).

### Added
- Kalmido AI per organisation (#6363): new switch "Kalmido AI in this organisation" (organisation settings, admins only, not through a support session), off by default. While it is off, no server agent or team AI works with the organisation's content: creating a team AI, its server settings, model list and starter pack answer 403 `org_server_agents_off` (deleting the key still works), a running agent run ends before the next provider call and events from the organisation's projects are left out. Server admins get a security alert on every change (per organisation and value; at most 6 changes an hour per organisation and person, then 429). One-time step at the update: organisations where a team AI with a key or an admin's server agent with a key already worked are switched on, all others start off.
- Release stamping (#6893): `tools/stamp_release.py` derives VERSION, the service-worker cache number (from the version, always rising), the CHANGELOG section and the whatsnew entries from the tag and the changelog.d fragments when the release image is built (release.yml, weekly-release.yml); without effect while VERSION already equals the tag. The CI gate accepts a green "Merge queue gate" of a merge_group run on the tagged commit.

### Changed
- Privacy template, SELF-HOSTING outgoing connections, AGENTS.md and AGENT-SETUP.md (#6363): name the Kalmido AI (server agent, Anthropic, USA), VIES, FinTS, Paperless and Linear; the Git and e-mail rows list all fields; the paragraph saying agents only run at the person's provider is corrected. The update check text says "every 6 hours".
- Admin alerts (#6363): the hourly cap counts per alert kind, so an alert a customer can trigger never silences login rate-limit, new admin or 2FA-off alerts.

### Fixed
- Agent starter (#7141): a bare yes / no without a quote no longer answers a permission question when a newer card of the same person came after it.
- Agent starter and job views (#7162): the wake loop waits while the agent's mode is unknown; the waiting list, chat job cards and job names hide the words of a task job the viewer may not see, like the job detail.
- Issuer text check (#7144, part): an IBAN written with Cyrillic / Greek look-alike letters or O / I / L for digits is found.

Package 2.1425 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Added
- Organisation export: the person who started it gets one News item (and a push) when it is ready or has failed, also for the export of the own office; a new row "Exports" in Settings > Notifications switches both off (#6581)

### Changed
- Organisation export: checks the free disk space before it starts and refuses with a plain message when the files would not fit (as the account export already did); a disk that runs full during the run is named as the reason (#6581)
- Organisation export: one organisation export at a time on a server; a second one answers "Another organisation's export is running on this server" - the export of a person's own office is never held up by it (#6581)

### Fixed
- MCP: a text field made of two fences glued together is no longer half unfenced when an agent writes it back; the cache of trusted accounts keys on the token's hash and drops expired entries; `docs/AGENTS.md` names the limit of the fence for notes and wiki pages (#7197)

Package 2.1424 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- Organisation import (Settings > Data > Import from a Kalmido export): the admin of the target organisation can invite the people of the file that are missing (before: only a server admin). It takes the normal invitation way of Settings > Organisation > People: a new address gets an account with an invitation link by e-mail, the person joins only by accepting with the role confirmed in the preview, the ticked projects are shared then; every typed address counts on the same day limit of invitations (20) before it is looked up, for the whole run before it starts - a run that does not fit counts nothing and names how many are left today (a server admin is not limited, as before), and the e-mail budget applies; an address with an account the admin may not see gets the same answer and a silent invitation, as from the member settings. Into the private space only a server admin invites, as before. Undoing the import ends these invitations and deletes an account it made that was never used, like Withdraw (#6580)
- Import preview: the people of the file with "found: …" / "not found here" and how many were found; with people missing a warning to invite them first and let them accept, then import (assignments, comment authors and times only go to people found here). The steps of "Move to your own server" and SELF-HOSTING.md name the same order (#6580)

Package 2.1426 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Starter-Parität: Dispatcher-Reste I (#4061 #4062 #).

### Added
- Reference starter dispatcher: optional `brief_required` - a task is only built when it carries a bold decision, a "Where" section and a size, otherwise it is marked `needs_brief` (#4062, #7041).
- Reference starter dispatcher: build places come from the work style's `max_parallel`, capped by `places` (default 4, still one place without `max_parallel`) and `KALMIDO_JOB_WORKTREES`; a 409 `slots_full` holds only the next build job (#5199, #7041).
- Reference starter jobs: a hand-over reminder before the time limit (the job writes its hand-over note); no follow-up job starts by itself (#4063, #7041).
- Reference starter: every override of a safeguard at the start (danger guard, a set permission mode) is logged (`override_log` capability) and counted (#4064, #7041).
- Reference starter dispatcher: the day report names the median hours from built to `close_ref`, jobs that ended with open tasks, and overrides (#4061, #7041).

### Fixed
- Security, roles: a personal agent's organisation role is at most its person's current role, checked on every request in one place (`org_roles_cap`); an agent whose person left has no role there. Changing a member to guest or accounting takes their personal agents out of the organisation like leaving does; with read only they stay and only read. The agent exceptions of the read-only checks in wiki, sheets and files are gone (#6605).
- Security, support session: the app's role checks (`org_roles_of`, `user_orgs`, `org_role`) are narrowed to the organisations the support grant covers, per request; a failing notification no longer drops the first log entry of a support grant (#6977).
- Merging clients or contacts moves their links (obj_links) in both directions from the merged record to the kept one through one core function (`mg_olnk_move` in core/merges.py); before, links pointing at the merged record were deleted by its delete trigger and undo did not bring them back. Undo now restores them, including duplicates that fell together. The client merge overview counts links (#6288).
- Reference starter dispatcher: `close_ref` is a plain ref name, never a git option, job branch or bare commit id; waiting line and brief are read in linear time (#7041).

## [2.1420.0] - 2026-11-19

Package 2.1411.0 (Bündel: Starter (mcp): ein gemeinsames Modul für doppelte , Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- MCP server: one data fence for every tool's result (#7151). Instead of field rules in `get_task`, `list_subtasks` and `list_attachments`, `handle()` judges every object of every result by the author it names (`created_by`, `author_id`, `by`, `author {id}`, a message's `user_id` with `body`), by `updated_by` (a text another account rewrote) and by the server's outside mark (`untrusted`, `origin`): texts of accounts other than the token's own, the owner and `KALMIDO_OWNER_IDS` are fenced as data and marked `untrusted: true` - now also in `list_tasks`, the search, the agent chat, the team chat, notes and the wiki. A text field the agent writes back that is exactly one fence loses its fence lines; a quoted fence inside a longer text stays. `fields=compact` of `GET /api/v1/tasks` carries `created_by`, `updated_by` and `by_creator` (and `origin` / `untrusted` when set). An author field of any shape (an object, a list, a name) is judged without breaking the server; a result the fence cannot judge comes back whole as data.
- Reference starter: one shared module `mcp/agent_common.py` (a new starter file, required by both setups) for redact, the API transport (429 retry, new request token after 401), chat parts, kill_tree, multipart and write_json; `defuse_fence` and `env_credentials` come from `kalmido_mcp.py`, which stays a file of its own. About 290 copied lines are gone (#7151).
- Office: reading sealed values takes the organisation key row once per transaction instead of once per row and field, the switch `org_encrypt` too; a sealed list of N rows reads `org_keys` once instead of N times or more. Sealing a new value still reads the key row fresh (#6401).

### Fixed
- Reference starter dispatcher: `GH_REPO` for the pull request is set from `push_url` on any host (GitHub Enterprise with its host, addresses with a user or a port), not only github.com; a `push_url` without owner/repo is named once in the log (#7170).
- Reference starter jobs (`agent_job.py`) mask JWTs, PEM keys, AWS / Slack / GitLab tokens, `user:password@` in URLs and `password=...` pairs in job logs and results like the event runner; before they went through (#7151).

Package 2.1413 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Starter-Dispatcher: Lese-Job prüft das Bündel vor ).

### Fixed
- Retiring an organisation (self-hosting): the retention counts each finalised office document by its kind - invoices and credit notes 8 years, offers, reminders and delivery notes 6 years (plus the operator's buffer) - instead of all as books (10 years), as the retention hint says; the deletion lock of an account or organisation names the same day (#6361).
- Organisation move (read only): background work a writing request starts (emptying a big trash) now runs under the same lock as the request (`bg_jobs.strict`); opening the agreements no longer purges a moving organisation's trash; the retention export's move exception comes after the rights check; an instance admin can end the move of an organisation that has no active admin of its own any more (noted in its history), so no organisation stays read only without an admin; anonymous sources (mail, file request, public form) use at most half of a workspace's hourly text recognition budget, the members' own files keep the rest (#6951).

### Changed
- Starter dispatcher: before the "Ready to merge" card a read-only review job (`agent_job.py start --audit`) reads the pull request; the card goes out when it ended and names its verdict (green / findings / no verdict). `read_pr` (default on) and `read_wait_h` (default 6) are set in the state folder's `KALMIDO-DISPATCH.json` only (#7032).

Package 2.1416 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Added
- Office: missing required details of a draft stand as a list above the document (blocks apart from hints), each line with a jump to its field, the client or Settings > Company & office with the section open; Finalise (and the PDF download) open their dialog only when nothing blocks, "Check again" reads the list anew; the document's GET brings `missing` [{key, text, level}], the agents' invoice API adds `missing_keys` (#6529)
- Office: card "Set up your office" on top of the office (Start and Quotes & invoices) while name, address, tax number or IBAN is missing: five rows with tick and jump (company, tax and small business, bank, numbers, logo), can be hidden per office (#6530)

### Changed
- Office: a quotation is finalised only with the company's name and address (the same list as the invoice); an organisation's office presets its company name from the organisation (#6530)
- Team chat: the room list, unread counts and push badges no longer read every message of a room - newest message per room by index, unread only for rooms with news, the @mention check reads the newest 500 unread messages (#6400)
- tools/check_innerhtml.py keys a finding by its expression without comments, so removing a version mark from a comment is no new finding; baseline re-keyed with the same count per file (#7173)

Package 2.1414 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Added
- First start of a self-registered account (#6519): before the welcome tour one skippable question "Private or with an organisation?"; "For my organisation" with its name creates it and opens the closing step below. Only on servers in the workspaces mode, never for accounts an admin made.
- After adding an organisation (workspace menu, Settings, the first-start question) a closing step "The organisation … is set up" with two next steps: "Enter the organisation's details" (Settings > Company & office, without the office Settings > Organisation) and "Invite people" (the invitation dialog), or "Later" (#6519).
- Settings > Account: a person without an organisation finds "Add an organisation" there (on a phone too); before, the button only showed once one belonged to an organisation (#6519).

### Changed
- Agents (#6455, audit F5): `task_added`, `tasks_added` and `tidy` of a task a person created or moved in who may not address the agent in that project carry `origin: "member"` and `untrusted: true` on the event and its task; the reference starter frames such text as data.
- API v1 (#6455): a received filed mail (`GET /api/v1/mails`, `/mails/{id}`) carries `origin: "mail"`, `untrusted: true`; a document a stranger filled (document mail address, mailbox rule, file request: `GET /api/v1/documents`) carries `origin` `mail` / `file_request` and `untrusted: true` - also for REST users without MCP.

Package 2.1420 (Start pflegen: Startgröße senken).
### Changed
- Start care (#4742): 144 rules of `app.css` that only one area loaded on demand draws move unchanged into that area's stylesheet, ahead of its own rules so the cascade stays. New stylesheets: e-mail hub and mailbox dialog, mail viewer, project dialog, questionnaires, Office > Clients, an agent's proposal card, the habit dialog, the tags overview and folder settings. The start loads 1.6 KB less CSS (gzip); the CSS ceiling in `tools/perf_budget.json` drops from 122163 to 121118 (2.5 percent room).

## [2.1415.0] - 2026-11-19

Package 2.1400 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Starter-Dispatcher: Stopp-Signal nicht verschlucke).

### Added
- Starter: a third rights profile "Programming agent" (`dev`) next to hardened and standard, in `mcp/agent_profiles.json`; chosen with `setup.sh --profile dev`, `setup.ps1 -RightsProfile dev` or the new "Rights profile" field of the setup dialog (Settings > Agents > Set up); `dev` allows editing, committing and the usual build and test commands, a push asks first; it writes the secret paths into `KALMIDO_BLOCK_EXTRA` of the env file (#7115)
- Starter: a project's own block list for the guard, `KALMIDO_BLOCK_EXTRA` in the runner's env file (`host:`, `cmd:`, `path:` entries with `*` / `?`): ssh / scp / rsync targets, deploy commands and secret paths are refused like the fixed list, paths also as Read / Edit deny rules; holds also with `KALMIDO_BLOCK_DANGEROUS=0`; the runner pins it for the jobs its agent starts (#7116)

### Changed
- Starter: the agent can no longer change its own control files: `KALMIDO-DISPATCH.json` is read from the state folder (or `KALMIDO_DISPATCH_CONFIG`), a file in the project folder may only tighten and the person is told once to move it; Edit and Bash on the state folder, the env file, the starter files, `KALMIDO-DISPATCH*` and `.claude/settings*.json` are refused (#7117)
- Starter dispatcher: the check runs on a fresh copy of the job branch's commit, never the job's working copy, and exactly that commit is pushed; `KALMIDO_DISPATCH_PUSH_URL` is required and must equal `git remote get-url --push`; a repository config key outside a short allow list refuses the landing; a stop during a write ends the round (#7057)
- Agent rules: work ends in a pull request, never merged by the agent; the short rules for coding agents name Stop and "write only into the same or a smaller circle" (#7057)

### Fixed
- Documents: whoever sets or changes the webhook address of a document flow becomes its author at once, so the delivery checks that admin's rights (#6875)

Package 2.1403 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- #6944 Project page and start page tiles look calmer: an empty tile's title and its hint sit on one line; two or more half-width tiles in a row stand in two columns on the project page (a short tile no longer stretches, Notes moves up under Important links; on a phone one column in the same order); the resize grip shows only when the pointer is on its corner; logged time ("66 h", "66/103 h") uses the text font; the flow tile's sub-headings ("Open and done over time", "Bug trend") look like the other sub-headings; e-mails and approvals added under "+ Block" use the plain tile row style.
- #6947 A quotation's reference lines (Replaces, Replaced by, From quotation, Invoices for this quotation) sit in the head under the finalised note with the same space above and below, no longer squeezed between two boxes; the approval box keeps space between "Link valid until" and the "Create approval link" button.

### Fixed
- #6402 Office performance: `GET /api/clients` reads lists, contacts and the hours of all clients in a fixed number of shared queries instead of about 13 per client (amounts identical to the cent); a single client's card reads one time report for all its lists; the time report filters the wanted lists in SQL. New `GET /api/clients?brief=1` (names only, no statistics), used by Offers & Invoices for its name check (`/api/v1/clients` unchanged). The office figures tile keeps its cache for 300 s instead of 45 s (longer than its one-minute poll); its fingerprint uses counters and a sum of row hashes instead of md5 over every document. Suite p21403_b_office_perf (new).

### Developer
- #7143 Lint says why and what instead: every own check (tools/check_*.py, ruff and semgrep baselines, .semgrep/sql_ident.yml) ends a red result with "Why", "Instead" (the helper or file to use) and "Do not suppress it and do not build around it" (tools/lintmsg.py). New checks: tools/check_suppress.py (noqa per code, nosemgrep, eslint-disable and the checks' -ok markers, the ones without a reason; baseline tools/suppress_baseline.json, `--update` only lowers) and tools/check_rules.py (rules from audit #5501: os.environ outside core/env.py, history marks like "2.NNNN (#ID)", duplicate top-level names in mcp/*.py, _data_fence calls, SECRET_* pattern alternatives, tracked "generated by" files, client write calls; baseline tools/rules_baseline.json). The ratchet is red per change in tools/pr_lint.py (pull request / merge queue entry, both checks read from the base commit): `suppress` - per marker kind no more markers added than removed, every added marker with its reason in the same comment, no further os.environ read outside core/env.py; `marks` - no added line of app.py, kalmido/ or static/js with a history mark (a pointer to a decided task stays as "(#ID)" without the version). The totals in the lint job run with `--notice`, because they move with every package merged meanwhile. The short rules for coding agents (mcp/CLAUDE.coding.md) say: fix a lint finding at its cause, never suppress it, never raise a baseline. Suite p21403_c_suppress (new).

Package 2.1402 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Fixed
- #6247 Post-calculation: when the invoice from a quotation settles a rest cent and a tax rate has a single hour position, that position stays an hour position (by time, with its actual hours); the rest cent goes on its own "Rounding adjustment" line. Invoices without post-calculation are unchanged.
- #6579 Import (account and organisation): storage is checked against the target before the run - the preview names, per target, the space needed, free and missing and what to do (ask the operator for more storage or a larger plan, or free space); for an organisation the target's pool counts with the people the import invites. Start is refused with 409 quota_exceeded when it does not fit; a limit reached during the run rolls the whole run back (no partial import without files any more). Uploading the archive itself no longer counts against the importing admin's quota.

### Security
- #6978 Agents: a card step with the agent's lasting token holds the route classes of the person who said Yes (organisation / closed routes give 403 run_closed, as with a request token); locking, removing, demoting to guest / read-only or leaving deletes that person's request tokens; request tokens are recognised by their columns (asked_by, slot), no longer by the name "Agent request".

### Changed
- #7120 Docs: the checklist for connecting a coding agent to a project with live clients (docs/AGENT-SECURITY.md) names what is not built in yet and how to secure it by hand; linked from AGENT-SETUP.md, AGENTS.md and the agent setup guide in the app.

Package 2.1407 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Audit 2026-11-17-was-braucht-gentasy-dev-vor-dem-a).

### Added
- #6945 Projects carry the client's PO number (a row "PO number" under the project head, API `po_number`, MCP `update_list`); new quotations and invoices of the project take it as their order reference, drafts without an own one follow a changed project PO, finalised documents never change; an order reference typed into a document gives a project without one its PO number.
- #6945 Quotations show the order reference too (editor and PDF head "Ihre Bestellnummer"); the editor marks a value that differs from the project's PO number.
- #7119 Agent starter: background jobs ask permission questions in the agent's chat like runs (Allow / Deny, only the operator answers, no answer in time = denied; without the runner the step is denied as before).
- #7155 Test: reference XML of 24 invoice cases in five e-invoice forms, compared byte for byte (`p7155_einvoice_golden`).

### Changed
- #6945 The suggested e-mail subject of a document names its PO number ("Rechnung 673 – Ihre Bestellnummer PO-4711"), in the document's language; the office search, the document list and the command palette find documents and projects by their PO number.
- #7155 E-invoice: one EN 16931 value model for ZUGFeRD / XRechnung (CII) and Peppol / UBL; both writers take the same tax breakdown, payment means, line prices and totals - the files stay byte for byte the same.

### Fixed
- #7086 Update floor: the start message, the restore error and the docs name 2.1001.0 (a real release) as the stop on the way through instead of a 2.1000.x that never existed.

Package 2.1415 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- Event invitations by e-mail (#6355): they go out only from a confirmed own address (Settings > Account; without one the save answers 409 and the event editor shows a hint instead of the switch), a new account sends at most 30 a day in its first 30 days (then 200), a cancellation to someone who had an invitation has one spare mail a day beyond the limit per receiving address, and the message after saving or deleting an event or a calendar says how many guests a limit kept from their mail (`invite_held` in the answer of `POST/PATCH/DELETE /api/events` and `DELETE /api/evcals/<id>`).
- Server agents (#6510): the hint "agent added" to the project members and the set-up of an agent on the Kalmido server name where its reading goes - the model provider and host (Anthropic, `api.anthropic.com`, or the address set in `KALMIDO_SRVAGENT_ANTHROPIC_URL`) - instead of the internal mark `kalmido-server`; the safety tip "Know where the data goes" and docs/AGENT-SECURITY.md say that the server agent sends from the server.

### Fixed
- Upload Undo (#6227): restoring an uploaded version that fails (offline, no rights, a locked month, a folder that switches) keeps the step in the history instead of counting it as done; two files of the same name with someone else's version in between are left out of Undo and named like a conflict; a session that ends in the middle of an upload lists the remaining files as "Signed out" and ends with the usual message, Undo and (documents) history entry.
- Support sessions (#7140): the lock on a filed mail's original .eml now sits in the file store's one reader, so the wiki export and the documents ZIP leave it out as well (was only the download and the file store ZIP).

Package 2.1408 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Frontend-Ratsche: Zahl der globalen Namen und der , Audit 2026-11-17-was-braucht-gent).

### Added
- Sidebar: a swipe to the right on the page opens the folded sidebar on touch devices (folded by hand: it comes back; the drawer on a tablet with a task open and on phones: it opens). It follows the finger and opens past a third of its width. Not from the outer 16 px (the phone's Back), not on task rows (their swipe completes), messages, fields, leafing areas (document view, image viewer, calendar grid) or a zoomed page (#6693).
- Background queue: a job whose work raises is tried again with a growing gap (30 s, 60 s; mails and pushes up to 3 runs); pushes waiting over an hour and mails over 24 hours expire instead of going out late; jobs of an unknown kind end after 24 hours; admins get an alert (Storage and health) when more than `KALMIDO_BG_ALARM_FAILED` (10) jobs failed in an hour or the oldest due job waits over 15 minutes; `GET /api/admin/health` shows `failed_1h`, `failed_kinds` and `oldest_wait_s` (#6388).
- Server agents: when a restart cuts off a run, the person it worked for reads "I was interrupted ... Please send it again." in the chat (no second run on its own) (#6388).
- CI: `tools/check_globals.py` - a file that newly writes a key of the app state `S` another file makes is red (compared with the queue entry's / pull request's base); the count of top-level names is shown (#6831).

### Changed
- Sidebar swipe to the left: the icon bar stays visible, the panel glides under it; in the drawer the dimmed background lightens with the finger; a long-press drag of a project, folder or area icon never moves the sidebar (#6693).

### Fixed
- `mcp/starter_sha256.txt` is no longer tracked (generated at the image build since #6887; a re-added copy made packages collide in the merge queue) (#7175).

## [2.1412.0] - 2026-11-19

Package 2.1394 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Starter-Parität: Dispatcher-Reste II (#5200 #5201 , Starter-Parität: Karten, Job-Chat).

### Changed
- Derived starter files are no longer checked in (#6887): `mcp/starter_sha256.txt` is generated at the image build (the server computes the sums itself when the file is missing), the agent chat reads the agent rules from `GET /api/agent-rules` instead of a copied `AG_RULES` constant, and `mcp/launcher_capabilities.json` became a folder `mcp/launcher_capabilities/<id>.json`. Two packages that change a starter, an agent rule or a capability no longer collide.
- Support access (#6862): through an operator's support grant, a client's agent can only be switched on or off; delete, reset, avatar, test event, removing a device and writing work style, rules, control, data lock or work list answer 403. Reading stays allowed.
- Reference starter, thin launcher (#4068): `agent_launcher.sh` and `.ps1` only load the env file, find Python and start `agent_run.py --launch`; the runtime logic lives once in `agent_run.py`.
- Reference starter dispatcher: holds a task while its dependency field names an open task that is not built yet (#5200); a task closed and reopened without a new commit stays held (#5201); optional `same_file` switch bundles ready tasks naming the same source file (#6176).
- Runtime settings: model and effort per job kind (build / review job), section "Jobs on their computer" in the agent dialogs (#7031).

### Added
- Reference starter: a yes / no in words decides the matching approval card, job cards are listed under open approvals, unposted job results are retried with backoff (#4951, #2347); a new job's brief is posted once as `kind=brief` into the job chat (#5237); a missing agent command is reported in the agent's language (#3820).

### Fixed
- Calendar (#6720): an organisation's event opened through a link (`#ev/<id>`) now shows the organisation's stripe, origin and tone; due tasks of an organisation's project carry the same stripe as events in month and week view.

Package 2.1398 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Sicherheit Agenten: Kreis-Regel deckt POST /agent/, Fehler main: p6668_ext_team_agent).

### Changed
- Under "All workspaces" every module (Knowledge, Files, Reading, Tables, Workload / Absences / Disposition, clients, contacts, calendar, time tracking) shows only the workspaces it is switched on in for you, as the office does; one workspace left opens directly and wears its colour. Nothing is deleted - the search and the trash still find everything. (#6722)
- Team agents: a job for a person (POST /agent/jobs with user_id, its title / log) is held by the circle rule like a chat message; a job without a task shows its words only to people who read every place of the agent; rules, playbook and layout proposals are writes into their project (#6863)

### Fixed
- A project that moves to another workspace and back keeps the invoice reference of its billed time: entries billed on a finalised document of the office it left are on that invoice again when the project returns (until then "billed in an earlier organisation", never billable twice). New nullable columns time_entries.billed_moved_doc_id / billed_moved_item_id (migration 6883). (#6883)
- Agent starter: the ps environment guard checks every word again (VAR=x, then/do, timeout / sudo -u / nice -n, -N, ps o e) (#7132)
- Agent starter: a woken or continued job of a team agent gets a request token only when the server's job belongs to that person (#7132)
- Test p6668_ext_team_agent: the dispatcher stand-in names its check_cmd (#7138)
- Agents: a team agent's job or layout proposal with an unreadable user_id (7.0, true, "+7") no longer slips past the circle rule; it asks with a card (#6863)
- Agents: progress steps (/agent/progress) and /tasks/{id}/working lines into a job for a person pass the circle rule like a chat message (#6863)
- Agents: a job without a task no longer shows its title in "Waiting for me" or on the chat's job cards to people outside the agent's circle (#6863)
- Starter: the ps guard reads the word before ps only from the same command and no longer stops at a closing brace (#7132)
- Starter: a job's wake run is no longer lost when the server could not be reached; it waits for the next look (#7132)
- Setup guide: states exactly what the job-file check binds (#7132)
- A team agent's job waiting for approval no longer sends its title as News / push to the task's assignee when that person would not see the job's words in the job list (#6863)
- The agent starter's ps guard refuses in doubt: any letters-only ps argument with an "e" (also an option value such as etime) or a dash block with "E"; use `ps -o pid,etime=` or pgrep (#7132)
- A team agent's job continued after a restart, or woken by a card answer, is tried again on the next look when the server could not be reached yet, instead of being lost; an unknown agent mode no longer counts as checked (#7132)

Package 2.1401 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Handy-Favoritenreihe: Verlauf am rechten (und link).

### Fixed
- #6935 Long lists (e.g. a "Done" list with hundreds of version sections) scroll smoothly again: the windowed list finds each section's spacers once instead of every frame, measures only sections with drawn rows and reads the scrolling box once per pass (Firefox: vl_sync 42 ms -> about 1.5 ms per frame).

### Changed
- #6127 Navigation: one "Switch to" menu for the head bar, the drawer's mark, the phone button and the project badge (organisations, Private, All, then "Add organisation" / "Organisation settings"); personal settings only in the account menu (the update dot sits on the account picture); "organisation" instead of "company" and "sidebar" instead of "panel" in the navigation; the phone's "More" sheet shows only overflowing tabs, Search, Settings and "Customise tab bar", not the drawer's areas again; favourite tiles show their (shortened) name on the phone row and in the head bar while there is room.
- #6983 Phone favourites row over the tab bar: a soft fade at the right edge while more favourites follow, at the left edge once scrolled; no fade at the start / end; without transition with "reduce motion". The computer's head bar is unchanged.
- #6234 Start page under "All workspaces": the Projects and Notes cards mark each row with its workspace (colour dot + name) through the shared organisation-colour building block (wso_origin); hpWsMark uses it too.

Package 2.1405 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Fixed
- Document view: the receipt fields (project, category, VAT rate, reverse charge) send only the changed field with the version the view read; a change made on another device meanwhile is refused (409) and the field shows the current state instead of being overwritten. Undo and redo go back per field and say "Changed elsewhere, not undone" over a newer change (#6998).

### Changed
- AGENTS.md: a copy of a task onto this server carries no origin mark; a task moved to another server is created there with the person's own token and counts as their hand there. Tests prove the empty origin for the copy here and for the 'Rest:' task (#7112).

## [2.1405.0] - 2026-11-19

Package 2.1397 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- #6885 "Add organisation" stands in the workspace menu only while the person is in no organisation (first company stays easy to find); otherwise it lives in Settings > Organisation (workspaces pane, same dialog), and the settings search finds it also by "company".
- #7133 docs/PRIVACY-TEMPLATE.md: the server log row names the days the log is kept (the hosted server: at most 30 days, journald `MaxRetentionSec=30day`), the host and the purpose.

### Fixed
- #6329 Your own text is never dropped without an explicit choice: signing out asks like the account switch (and downloads the text file) when conflict copies or kept input are there, not only with a waiting queue; "All: keep the other version" in the conflicts dialog leaves refused offline changes; closing the knowledge page conflict dialog without a choice or "Take theirs" keeps your text as a waiting draft at the page (the kept-input store of #6286), a note's text waits in the conflicts dialog (not for locked lists).
- #6320 Security: a support session cannot write into an organisation without that organisation's grant on any path - the core access checks (`need_list`, `need_task`, `obj_need`, `need_node`) refuse it with 403 `support_session`; the path table `SGA_PATH_ORG` is gone. Deleting for good without trash (budget files, notepads, the last branch of office docs) is refused for support sessions; filed mails hide their filing addresses and the original .eml (mail file route, file content, ZIP download).
- #7113 Invoice issuer keys (review of job/5377): text checks run after NFKC without control / format characters (IBAN with any separator, web addresses with any ending, VAT ID characters only); the admins' alarm mail names no client; an organisation import rebuilds the client hold mark and a broken mark shows without a 500; one read line per issuer and hour in the office log; the key's client PUT takes the client lock before the row (no lock-order deadlock); the queue guard suite p5787_queue_gate is hard.

Package 2.1391.0 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Bündel: CI: Versions-PR des Live-Zugs in der Merge Queue m, Sammelpaket: Aufgaben ohn).

### Fixed
- #7111 Office: adding an invoice issuer no longer hangs - the password question (sign-in confirmation) lies above every dialog that asks for it, also above the issuer dialog; a number range added, changed, removed or undone turns "Add invoice issuer" on at once (the issuer block asks the server again instead of keeping the old answer until a reload).
- #7080 Post-calculation: the invoice draft checks the rights on the project's times before it frees times bound to a deleted draft (review finding F4 of job/5326; F1 is #6106).

### Changed
- #7089 Workspaces: an organisation without an own symbol shows the first letter of its name in the accent colour everywhere (workspace switch, sidebar, Settings > Organisation, Administration) instead of the briefcase - the same as the "automatic" tile of the organisation dialog.
- #6130 Settings > Account: the sections in the order profile, security and sign-in, devices and data (each a folded section); Sign out also next to the name; a session of a script or tool reads "Program / script" (the raw name as its hint); storage without a limit in plain words ("No files stored yet, no storage limit"); the two password fields one under the other, never cut off on a phone; "For advanced users" instead of "Advanced · for developers"; the passkey hint in everyday words, the HTTPS / IP details folded for server admins; My colour: long workspace names wrap, the swatches stay inside the window.
- #6130 Settings > Notifications in everyday words: "Browser notification", "Notification app", "Channel name"; the ntfy server and topic folded under "For advanced users"; Tasks by e-mail names KALMIDO_* settings only folded for server admins.

### Security
- #6906 Agents (MCP): a file name and a subtask are fenced as data by their own author - another account's file or subtask on the owner's task is data, not an order; list_subtasks and list_attachments are fenced like get_task. A file from a mail or a public form, a file of an unknown uploader and the files of a fenced comment are fenced, too. The API names a task file's uploader (`by` in a task's attachments and in GET /api/v1/tasks/{id}/attachments) and marks a file from a mail or a public form (`untrusted`, new column attachments.outside).

Package 2.1401.0 (Bündel: Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Starter-Parität: Dispatcher-Pflicht - Ende im Pull, Starter-Parität: Regeln u).

### Changed
- #7056 Knowledge shares with pictures: a file store picture embedded in a page goes out through a link or a person share only when it is confirmed for exactly that share - when its embedder puts it into the page while the page is under the share (a later save of a picture already there confirms nothing), or when the share is made with pictures or gets them switched on (its maker shares the pages as they are). Moving a page (rename, the tree, a folder merged into another, the trash and back, another workspace and back) confirms nothing; the old move hooks are gone. Pictures shown before the update stay confirmed. Migration 7056: column `wiki_embeds.shares` (additive).

### Fixed
- #7023 Bell: the section heads "For you" and "History" stand flush at the top of the list while it scrolls, over the full width and opaque - no rows show above or beside them (window and phone sheet).
- #7060 My tasks on the phone: the end of the list leaves room for the + button (its offset, its height and 1rem), so it never covers "New section".
- #7037 Number ranges: a closed range opens again only with a scheme the office accepts; the import cleans a refused scheme; a new range and the import also check the correction scheme; the settings refuse the scheme of a range; moving the personal office refuses a range scheme the organisation already uses.
- #6952 MCP: a test checks that the items of a completed task's subtask copy (`sub_snapshot`, an object) are fenced as data (the fence came with #6906).

[Unreleased]: https://github.com/Kalmido/kalmido/compare/v2.1441.0...HEAD
[2.1441.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1441.0
[2.1434.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1434.0
[2.1432.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1432.0
[2.1426.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1426.0
[2.1420.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1420.0
[2.1415.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1415.0
[2.1412.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1412.0
[2.1405.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1405.0
