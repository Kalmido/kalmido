# Changelog

All notable changes to Kalmido are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Kalmido uses
[semantic versioning](https://semver.org/): every published change gets at least a new patch version, new features a
minor one. Releases in which operators have to do something carry a fixed section "Action needed"; the update notice
in Settings > Help shows that section of the target version.

## Older versions

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

## [2.1374.0] - 2026-11-18

Package 2.1374 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Büro: Aussteller-Schlüssel - Vertragstest in den h, Bündel: Sammelpaket: Aufgaben ohn).

### Changed
- The static guard suites are hard now: parity, p2695_a_rowmenu_coverage, tenant_coverage, freelancer_coverage, rls_static, launcher_parity, agent_docs_coverage and p2381_a_guards stand in tests/hard_suites.txt, so the merge queue gate holds a package that breaks one of them instead of letting it into main red. parity, rls_static and launcher_parity / agent_docs_coverage got test groups of their own, so no UI or container suite turns hard with them (#6323).

## [2.1372.0] - 2026-11-18

Package 2.1353 (Bündel: Film-Paket: Producing nach Betrag zurück ins priva, Arbeitsbereichs-Menü: Kürzel-Kachel jeder Organisa, Zitat des Tages nur noch auf).

### Changed
- Settings: every section of a tab is a folded head row with icon, name and a short state ("2 changed", "Kleinunternehmer · RE-2026-###"), also the eight groups of Company & office; open/closed is remembered per person across devices; search, jumps and hint links unfold the right section and flash the field; the single "Further options" fold of #4833 is gone (#6827)
- The quote of the day appears only on the sign-in page, smaller, with real line breaks instead of " / "; the start page no longer shows it (#6979)
- Film & Video pack: Producing by amount is back in the instance's private pack only, the public pack keeps handling costs and markup; the crew share block is named "Produktionsleitung" / "Production management"; saved quotations with a share by amount keep calculating unchanged (#6839)
- Workspace menu "Switch to": each organisation's initial tile wears that organisation's own colour, whichever workspace is open; Private wears its chosen colour in the menu and in the "All workspaces" overviews (#6957)

### Fixed
- The table panel in the sidebar draws the organisation stripe like every other sidebar row (3 px, 60 % of the row height) (#6723)

Package 2.1359 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Added
- E-invoice duty in Germany: with e-invoices switched off, the finalise dialog of an invoice above 250 EUR to a client in Germany that counts as a business warns that it goes out as a PDF only and names the dates (1 January 2027, 1 January 2028 up to 800,000 EUR turnover); small businesses are left out, it is only a warning. The same dates stand at the switch Settings > Company & office > Functions > E-invoices and in the procedure documentation (#6482)
- The button "Text block" of a quotation / invoice offers the built-in "Retention note section 14b UStG" (work on a property for a private client) in the document's language (#6482)
- Receipt check: a German supplier's invoice from 2027 on without e-invoice data gets the soft note "the supplier sent no e-invoice format" (not counted as a hint) (#6482)

### Changed
- The e-invoice XML carries the texts that only stood in the PDF: heading and text lines as the note of the next position (BT-127), intro, rights block, closing and text after the last position as document notes (BT-22) (#6482)

### Fixed
- Finalising an e-invoice stops with a plain message when the server lacks the sRGB colour profile, instead of storing a PDF that is no PDF/A-3 (#6482)

Package 2.1357 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Fixed
- Live updates on a second device: a note made or changed elsewhere shows at once in the open notes and the open note (notes are a light area of their own; unsaved typing keeps its text and the reload waits); a write that leaves no delta row (folder properties, a notepad, a public link) reloads the writer's other devices instead of answering "nothing changed" (#6335)
- An open calendar or Today view shows an event changed on another device without leaving the view; the open file store folder shows a folder or file made elsewhere; the day changing with the app open (or a phone woken next morning) redraws Today and the counts (#6335)
- A late delta answer overtaken by a newer one no longer takes a task back to an older copy; a team chat message that arrived while typing elsewhere shows with the next poll, not only with the next message (#6335)

## [2.1370.0] - 2026-11-18

Package 2.1333 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), MCP-Zaun: Zaun-Zeichen vollstä).

### Fixed
- #6697 Organisation colour: under "All workspaces" a page whose module is on in only one workspace (office, customers, time, team, dispatch) wears that workspace's colour in stripe, accent, icon rail, panel and phone bar; on mixed pages the active sidebar row of an open organisation object wears its tone.
- #6545 Mailbox fetching: a failing workspace mailbox waits longer each round (up to 6 h, the instance mailbox too); after 5 refused sign-ins it stops until the access data is saved again or "Test connection" signs in; admins are told by News, push and mail (only to a proved address, again every 3 days); a mailbox nobody can receive for is not fetched; mails too large or refused by the parser limits are counted at the mailbox; "Fetch now" is limited to 10 per person in 10 minutes; settings show the last successful fetch, failing since, the stop and a warning when the same person fetches the same mailbox in two workspaces. New `KALMIDO_MAILBOX_MAIL_MAX`. Migration 6545 adds columns to `hub_mailboxes` only.
- #6429 Security, calendar subscriptions: one recurrence rule per event, a rule ending before the window is dropped, the walk before the window is bounded per rule and per download, RDATE / EXDATE capped, the time budget is checked between series.
- #6770 Office hash chain check: an unreadable link no longer hides later breaks; after 3 days in a row it raises its own admin alarm once; each office runs in its own savepoint, so one failing office no longer drops the alarms of the others (docs/dev/hashkette.md).
- #6731 MCP `get_task`: the data fence defuses every run of three or more fence characters and also fences the title, file names and code snippets of other accounts and the title and description of tasks from outside Kalmido (mail, form, git ...); docs/TEAM.md says what the address proof mail names.

Package 2.1365 (Bündel: Büro: Zusätzliche Nummernkreise je Bereich (eigene, Morgen zeigt oben „Noch offen von heute“ (einklapp, Meine Aufgaben: Rechtsklick ).

### Added
- #6698: Additional number ranges per office area (Settings > Office > Number ranges): own counter, own date order and own hash chain, corrections with their own suffix (e.g. `-K`) in the same counter, dunning per range (off by default). The main scheme and counter stay as they are. In a range Kalmido sets the document date when finalising; hand numbers are refused. A range with a finalised document can only be closed, not removed. Ranges move with a private office transfer and go through the organisation export/import (code, scheme and suffix checked like a new range; a scheme the target already uses comes in closed) and the retention/auditor export. New table `office_num_ranges`, column `office_docs.range_id` (migration 6698). One way from the first finalised document in an additional range on: an older version would count it into the main range's date order - back only with a restore.
- #6960: "Tomorrow" shows a foldable group "Still open from today" on top (due today or overdue, same rule as "Today"); the tasks of tomorrow follow below under their own head. The sidebar count of Tomorrow is unchanged.

### Fixed
- #6698: The new number-range routes belong to the office area Settings (rights check); the account-deletion UI test follows #1969 (no deletion of finalised documents in their legal period, also with a declared waiver).
- #6962: In "My tasks" with own sections, "Move to section…" in the context menu and in multi-edit offers the own sections (with "New section…"); the project's sections are behind their own entry "Move to section of <project>…".

- #6795: The income statement (EÜR) and the office key figures read the credit notes once per run instead of once per paid invoice: with 5,000 paid invoices about 60 database statements instead of 3,400 (measured 750 ms -> constant). The document list stays under 150 ms with 5,000 invoices (measured, no change needed).
- #7034: The export register lint reads the new texts waiting in `static/i18n/neu/` too (it was red on main for the reason "Links").

### Changed
- #6948: Test suite for the number scheme change at the turn of 2026 -> 2027 (GS-{yyyy}-{seq:03}, corrections in the same counter with -K, a parallel GT range): chain, counters, December drafts, DATEV, income statement and e-invoice stay correct.

## [2.1366.0] - 2026-11-18

Package 2.1356 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Fixed
- #6326 Live sync: an open task follows a change made on another device - the detail panel is matched after every delta, also while the focus is inside it (always on phones); a focused text field keeps its text and cursor and takes the new text when you leave it; the conflict check uses the text the field showed, so typing on an old text now raises the conflict bar instead of silently overwriting the other device's change; an open conflict bar keeps the panel and your draft until it is answered.

### Changed
- #6967 docker-compose.yml: ClamAV and the database run with few rights (cap_drop ALL, five added back) and a process cap; ClamAV no longer shares a network with the database - network "scan" (internal, Kalmido + ClamAV) plus its own way out "out" for signature updates (docs/SELF-HOSTING.md).
- #6824 Startup: the one-shot data steps (migr_* flags) of init_db stand in one ordered list (kalmido/core/oncesteps.py), run at the same places in the same order, each step logged on its own; tools/check_migrations.py rejects new migr_ flags outside the list. No step changed its content.

Package 2.1358 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Fixed
- Office quotes / invoices: the kind chips (archive, dunning, invoice corrections) switch the list under an address with `s/org:N` too (#6964).
- Office editor: the title of a part on the title page grows with its text up to ten lines, like the subject; the client address from the contact directory shows its whole text (#6659).
- Undo: "Reset" in the date popover, the arrow and Ctrl+Z take back only the person's own groups, newest first (`POST /api/undo/<id>/undo`), never `/api/undo/to/` - newer steps of another device or tab stay; the fallback without the server list never uses `/to/` either (#6328).
- Undo: an own undo that was queued offline keeps `X-Kalmido-Undo-Own` when it is sent again (no new server step), and the group header only goes with writes made inside the step (#6328).

### Changed
- New tasks are written through one insert path `kalmido/tasks/repo.py` `task_insert` (39 inserts in 26 files); the ratchet `tools/check_task_insert.py` forbids new own `INSERT INTO tasks(` (#6825).
- Dependabot waits 7 days before it proposes a new version (cooldown), the counterpart of the 7-day rule of the pins (#6907).

## [2.1361.0] - 2026-11-17

Package 2.1345 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Added
- #6943 The surcharge of a quotation can be a fixed net amount instead of a percent (switch % / currency next to the field, like the discount; `markup_amount`, migration 6943): its own line "1 flat" with the amount and no percent, spread over the tax rates of the marked positions, one line on the title page of a quotation with parts, taken into the invoice from the quotation and the e-invoice per tax rate; repricing to a target sum keeps it fixed; without marked positions it is spread over all positions by their tax rates (like the fixed discount). Agents: `surcharge {amount, title?}` instead of `{pct}` (not both). Handling costs stay in percent.

### Changed
- #6532 The first real invoice of an office: the finalise dialog says it can no longer be deleted afterwards, only corrected, with the ways to the test mode and (admins) the number ranges; "Download" on a draft has *Show as draft* as its main button (Enter never finalises); an empty invoice series prefills the reason of a jump of its starting number ("Taken over from the previous program").

### Fixed
- #6736 Agent bridges approved before 2.1284: the first start no longer counts the people of today as approved, only the circle the history proves for the moment of the approval (members added before it, the owner unless ownership changed since, nothing for an approval older than the log period; keeping a deleted person's project for its custodian now writes that change into the project history); a person who came since makes the bridge ask once anew. The ClamAV image stays pinned by tag on purpose.
- #6658 Installer as root: a `data/` or `secret/` link is followed only into a folder that is empty or carries the marker directory `.kalmido-target` (made with `mkdir` on the first run, never written through a link; an older marker file becomes the directory); any other target, and `/`, stops with ready commands instead of handing it to user 1000; `.env` values with blanks before the quote are read right; a scanner of your own (`KALMIDO_CLAMD`) is named as such; `install.ps1` gets the 3 GB rule and `KALMIDO_CLAMAV=1|0` and adds a missing `COMPOSE_PROFILES` line.

Package 2.1340.0 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Fixed
- Security, organisation roles: the accounting role reads in the organisation's documents only the receipts and its own uploads, no longer every member's documents (list, content, thumbnail, ZIP) (#6613)
- Security, approval links: the address of a quotation's / generated document's approval link and the signer's e-mail, address and device only for people who may change the document; read-only and accounting see state and dates (#6613)
- Security, office: the accounting role no longer reads the pipeline, generated documents, templates, privacy sheets, correspondence and the whole office log; its menu hides them (#6613)

Package 2.1350 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Added
- #6502 New notification kind "Support access" (bell and push, can be switched off in the notification settings): co-admins learn of an organisation's support grant and its early end, the client (or all org admins) of the first use; the person granting access gets a security mail.

### Changed
- #6502 A support session reads only the person's private space, own office and organisations whose admins granted support access themselves (`core/access.py` `_ctx_support`, built per request, never cached per account); reads through an org grant are logged in that grant's log. Changes made in a support session carry `via='support'` in the history and show "(support access)"; the grant log keeps write entries up to 3000 (the 300 cap is for reads only), counts what drops out and shows it, and a log entry hit by a lock or error is retried in the background instead of lost. A support sign-in no longer counts as a known device or address of the client (migration `6502`: two added columns).
- #6721 Organisation colours: tone 2 of the palette is an olive instead of a petrol that looked like Kalmido's accent; organisations that had chosen the petrol show the olive.
- #6933 Installers (`install.sh`, `install.ps1`): an old `KALMIDO_IMAGE` line with a pinned version or digest is switched to `ghcr.io/kalmido/kalmido` only when the new name has that image (`docker manifest inspect`); otherwise it stays and a warning says what to set.

### Fixed
- #6933 `/api/state` no longer translates the names of the "not included" list into every language on each call (once per process).

## [2.1355.0] - 2026-11-17

Package 2.1343 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- Search: the command palette's "Everywhere" groups run on a time budget per request (KALMIDO_SEARCH_BUDGET_MS, 400 ms) in their fixed order; the areas not reached come back as `pending` and the palette loads them right after (GET /api/search?kind=groups&groups=…). Each area runs under a 2.5 s statement limit; a search the browser dropped (a newer query) stops before the next area (#6406).
- Search: the expensive parts are capped -- sealed texts opened to check a word found by its prefix (KALMIDO_SEARCH_OPEN_MAX, 500 newest per workspace), file texts and documents of the Ablage search (narrowed by the word index in SQL, 2,000 per workspace), text field values (2,000), the palette's message group (50 candidates per kind instead of 1,000) (#6406).
- Knowledge pages: the task-link suggestions ask the server for tasks only, without the other areas (#6406).

Package 2.1342 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Fixed
- #6927 Ticking a task off folds its row to nothing: no gap stays on the desktop (the column rows kept their padding) and the list no longer jumps on the redraw; the fold ends on the real end of the animation, not on a timer.
- #6479 The receipts and travel receipts billed on a cancelled invoice can be released again (*Release the outlays again*, `POST /api/office/docs/{id}/outlays-release`, undoable), so the correcting invoice can take them; the cancelled invoice keeps its positions.

### Changed
- #6553 Calendars and contacts hardened: a password is not sent over plain http:// and neither is a calendar link that looks like it carries a secret (a query, or a random-looking part of the path or file name; a heuristic) - only to hosts the admin allowed; existing subscriptions of that kind now fail with "Only https://", a CardDAV source that keeps failing is told like a calendar subscription (news after 3, alarm after 5 failures) and a refused write-back names the contact, the absences feed keeps only the hash of its secret (the link is shown once; existing links keep working), its failed attempts count per network (rate_ip), log lines name the error type only, the docs say that app passwords work without a second factor.

Package 2.1347 (Bündel: Weich rot: p21238_b_ro_ui, Weich rot: p2139_a_api, Weich rot: p2754_l_ci u. 2 weitere).

### Fixed
- German texts name the office settings "Einstellungen > Firma & Büro" (small business VAT note, switched-off import automations, XRechnung company data) (#6861)
- Suites follow intended changes: the contact card's "Move to the trash" (#6857, after #6124), a team agent hears a channel mention only via a shared project (#6858, after #6454), ruff and coverage pinned in the hash locks (#6860, #6859, after #6509); p2925_a_words also checks new texts in static/i18n/neu (#6861)

## [2.1351.0] - 2026-11-17

Package 2.1338.0 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- #6612: backups: `KALMIDO_BACKUP_MAX_MB` now applies to uploaded archives only. The server's own backups are checked, downloaded and restored whatever their size (before, an instance with more attachments than the limit, 4 GB by default, could neither check nor restore any of its backups); the error text names the variable. Settings > Server > Backup warns when the newest backup is larger than the limit for uploads (a downloaded copy then needs a higher limit on the other server).
- #6612: backups: once a week the newest backup is checked completely, like the button "Check" (decrypt, every checksum, the shared files, the database dump). A failure is an admin alert, shows on the backup page and is checked again the next day; a successful check shows its date there. With automatic backups switched off and no backup from the last 7 days, the admins get an alert once a week.

### Fixed
- #6612: backups: a damaged file in the shared backup store (same size, other bytes) made every backup that names it fail on restore, and nobody noticed. The check (button and weekly) writes such a file again from its original while that is still there unchanged, and says so (toast, admin alert).

Package 2.1334 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- Export guard per kind: tools/check_export_tables.py holds every kind of every shared-core table (comments, reactions, follows, read marks, notification templates, tags, tag links, versions, link relations incl. the free links) against the organisation and the account export; a kind no query takes needs a reason in KIND_LEFT (hard in the CI lint). OTG_KINDS / OBJV_KINDS name the kinds of tag links and versions; their helpers refuse an unknown kind (#6585).
- The organisation export guard holds every table, like the account export's: exported, in OX_LEFT with the reason, or holding nobody's data (#6359).
- The change history (obj_history) goes along: the organisation archive's history/changes.json follows exactly the objects the archive carries (never a group conversation's message, a hidden list or another organisation), the account export's data/my_history.json holds the person's own changes in the private space. Both manifests list what no import takes over (not_imported) (#6585).

### Added
- Account export: the details of the private document store (private-documents/documents/*.json: details, fields, senders, types, receipts, notes, tags, rules), private links (a contact's tasks, filed mails, free links), the bells of the own projects, the own notes and video comments in organisations, the account row, memberships, sign-in addresses, the files and voice messages sent in direct messages and private rooms, the other person's name on direct messages (#6585).
- Account export, formerly "not yet in the account export": agent chat files, trip costs, family rewards, remembered shopping items, table links, chat messages saved as tasks, knowledge spaces, the document rules of the private mailbox (#6359).
- Organisation export: free links (links.json), the templates' file copies (lists/template_files.json + files/templates/), the rules of the organisation's agents (agents/rules.json, without the source excerpt), the document rules of the workspace mailbox (hub/mailbox_rules.json) (#6585, #6359).

### Fixed
- Account export: a knowledge page, table or template file that is gone from the disk is named in the manifest's missing list instead of being left out silently (#6585).

## [2.1346.0] - 2026-11-17

Package 2.1336 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Action needed
- #6505: Self-hosters: the image moved to `ghcr.io/kalmido/kalmido` (the old `ghcr.io/gegenschuss/kalmido` gets no new versions or security fixes). `update.sh` / `update.ps1` switch a `KALMIDO_IMAGE` line in `.env` by themselves (version or digest kept); if you set the image elsewhere (your own compose or override file), change it yourself. If your `update.sh` stops with "Could not find the latest release", run it once with `KALMIDO_VERSION=v2.1336.0`.

### Fixed
- #6505: The installers (install.sh, install.ps1) follow every forward when they look up the latest release, so the move of the repository into the organisation no longer stops a fresh install or an update. When a release image pinned to its digest cannot be pulled, the installer says so loudly ("RELEASE IMAGE NOT DOWNLOADED") instead of building locally in silence. Installer, compose file, `.env.example`, docs (self-hosting, code verification, security, agents) and the addresses in the app name `Kalmido/kalmido` and `ghcr.io/kalmido/kalmido`.
- #6804: Importing knowledge into a locked (end-to-end encrypted) area detects the text encoding like the server import (UTF-8 with or without BOM, UTF-16, otherwise Windows-1252, named in the import report) instead of turning umlauts into replacement characters. Re-importing an export no longer reports Kalmido's own "not included.txt" list in the root of the ZIP as a skipped file (locked area and server import).

### Changed
- #6262: The document view asks the shared write rule: a person who may only read sees no write entries in the document view, its "Actions" menu and saved views, and exactly one "You can only read here" note in the properties.
- #6505: The nightly installer check also runs install.sh without a fixed `KALMIDO_VERSION` (the "find the latest release" way) and counts a local build after a failed pull of the release image as red; a lint guard keeps the old repository name out of everything but the changelogs.

Package 2.1327.0 (Bündel: Angebot/Rechnung: Zwischensumme der Positionen vor, Sammelpaket: Aufgaben ohne Paket (Dispatcher), Audit T2 B4 (Entscheidung): Lösch).

### Added
- #6816: Quotes and invoices show a bold "Subtotal" (net of the items, short rule above) right before the first surcharge, production surcharge or discount line; without a surcharge or discount nothing changes. The discount line always names its base: "5 % on the discountable positions (14,200.00 €)" / "Fixed amount on the discountable positions (…)". Display only - totals, tax and e-invoice unchanged; quotes sent before this version keep their lines. PDF and approval page, single and parts view (the web editor shows the base, not the subtotal row).

### Changed
- #1969: An organisation or account whose office holds finalised documents within their 10-year retention period can no longer be deleted (409 naming the date and the way: retention export, then deletion after the period or by the operator). A waiver of the export no longer suffices; the instance operator may delete only after a finished retention export. Covers organisation delete, account delete (admin, hosting console, self-deletion - refused at the request), and the retire/purge runs, which now leave such an organisation standing with a log line.
- #6823: One reading of a person's module switches: `feat_has` / `feat_in` / `feats` in `core/access.py`; `need_feat` (409), `v1_feature` (403) and `feat_on` build on it, 38 inline splits switched over, `tools/check_feat_split.py` refuses new ones. An agent with a locked calendar now also counts its calendar module as off (was: only its calendar list empty).

### Fixed
- #6591: Moving a personal office into an organisation and importing an organisation export re-chain the finalised documents that came in: their old chain places are cleared and they join the target's chain in finalising order (office log "chain_moved"), then the chain check runs once and its result is part of the move / import answer. Before, two documents on one chain place read as a broken chain for good, and an import stayed "pending".
- #6591: Moving a project into another organisation (or back to private) keeps its time entries billed in the old office billed, but drops the link to that invoice: the row shows "billed in an earlier organisation", duration and date stay locked.
- #6719: Notes follow their project's organisation colour: card stripe and origin under "All", the panel cards of a project, and the opened note marks the view in the organisation's colour; private notes stay neutral.
- main: #6453: The agents' job list asks whether a job's words are hidden (wider / public project) once per agent instead of once per job, so its statement count no longer grows with the number of jobs (p2674_b_api red since 2.1284.0).

Package 2.1308 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Kalmido-KI: hartes Tageslimit ist freiwillig; Ausl, Doku Wissen: bekannte Grenze bei ).

### Changed
- #6477: an invoice or correction without a client is finalised only with the recipient's fixed address fields (street, postcode, city, country; empty country = your own) - no free lines; the editor shows recipient, street, address extra, postcode, city and country instead of "Address lines" when the client module is off (quotations, reminders and delivery notes keep the free text). The sender comes only from the fixed company fields. A correction of an older invoice with free-text recipient stays possible and inherits its lines.
- #6568: on a hosted server (`KALMIDO_HOSTED=1`) every server agent keeps a hard day limit in tokens: set with the first key (default 2,000,000), it can be changed but not emptied (400), and at most the operator's ceiling `server_day_cap` (instance setting, `PUT /api/admin/agent-policy`, default 10,000,000). Existing agents get the limit before their next run. Runs nobody asked for (form, mail inbox, webhook, listening in) count against their own share - a quarter of the day limit (new columns `agent_runs.no_person`, `agent_usage.no_person`).
- #6523: the app's agent dispatcher (`mcp/agent_dispatch.py`) builds only tasks the person wrote themselves (`created_by` = the person and `by_creator` true); other tasks are listed as "foreign" and never start. Comments of other accounts reach the job brief fenced as data. New nullable column `tasks.origin` ('person' only for tasks written in the app or with the creator's own token); the API gives it as `by_creator`. Tasks from before 2.1308 count as not written by the person.

### Fixed
- #6476: finalising checks the finished e-invoice XML (ZUGFeRD and XRechnung) before any file is written and stops with 400 naming the missing data in plain words (nothing is numbered or stored); for XRechnung the finalise dialog names beforehand the client's Leitweg ID, your company's phone and e-mail and the client's invoice e-mail; XRechnung also checks postcode and city of seller and buyer (BR-DE-3/4, BR-DE-8/9). A tax per rate up to 1.00 off base x rate (BR-CO-17, e.g. a full credit note of a final invoice built from gross amounts) stays within the EN 16931 tolerance and does not stop finalising.

### Docs
- #6325: docs/WIKI.md names the known limit of excluded folders: a name already used by a folder kept out can be guessed, never its pages or content.

## [2.1344.0] - 2026-11-17

Package 2.1329 (Bündel: Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Teil 1/6: Sammelpaket: Aufgaben ohne Paket (Dispatcher), CI-only rot: p2458_b).

### Fixed
- Calendar: the Share dialog keeps a member that was put back (also by Undo) when it is opened again before the calendar list reloads (#6275).
- Office archive list: a background refresh no longer blanks the rows with "Loading…"; they stay until the fresh list is there (#6848).
- A switched-off webhook's News item is typed as a webhook again, so it shows and names the webhook (#6849).
- Start page: the getting-started step names the basket, not the old "inbox" (fr/es/it/nl) (#4992).
- Fewer database round trips per /api/state: excluded knowledge folders are read without a system block (#5137).
- Tests brought in line with earlier changes and freed from races: p252_a_ui (#5704), p2498_a_phone320_ui (#6191), p249_c_ui (#6347), p287b_c_ui (#6349), p255_e_ui (#6850), payonline_ui (#6851).

### Changed
- The #1219 old-name check of all translations moved from a UI suite into tests/i18n_test.py (runs in every lint) (#4992).
- The "…" row menu guard (p2695_a_rowmenu_coverage) runs along with every changed client script (#5354).

## [2.1339.0] - 2026-11-17

Package 2.1284 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- #6453: security (agents): an agent on "Routine" or "Free" asks with an approval card before it writes into a project that more people read than its other places, or into anything public (public link, client report, shared knowledge page); the card says "Visible to more people" / "Publicly visible", needs a person's yes and is never approved by the deadline. The progress line of a task shows no text in such projects; the mark still shows that the agent is working. The target is checked where the write really lands: a subtask counts as its parent's project, a target without a project (calendar, address book, table, folder) is checked against every source, a team agent's chat to a person and its status text count as targets, an approved bridge holds only for the circles it was approved for, and only a person who reads the sources may say Yes. The gates read a body id exactly as the routes do (' 7', '07'), and moving a task checks every project the body names (parent, list_id, section), also when a `_prev` conflict drops the parent. Template, in-app rules, AGENTS.md, the setup guide and the MCP descriptions name the rule.
- #6575: agents: deleting a project tag that nothing carries (no open, done or trashed task) no longer needs a one-way card; a tag in use, a tag a rule or a client link names, and every organisation label still do. One-way: the tag row itself (name, colour, order) is gone, it can be created again by name.
- #6606: self-hosting on Raspberry Pi and ARM servers: the virus scanner uses clamav/clamav-debian:1.4 (amd64 and arm64); the nightly install check fails when an image of docker-compose.yml lacks one of the two architectures.
- #6606: installer: on a server with less than about 3 GB of memory a new installation leaves the virus scanner out and says so at the end and in Settings > Server > Backup; `KALMIDO_CLAMAV=1/0` switches it on or off, an update keeps the choice and never removes a running scanner because of how COMPOSE_PROFILES is written in .env. `KALMIDO_CLAMD=0/off/no/false` counts as off like in the app. Run as root, the app keeps its own user 1000 (`chown -hR` of data/ and secret/, also of a linked folder's target).

### Fixed
- #6597: office editor: the subject and every multi-line field (address lines, rights note, introduction, closing, text positions) show their whole text, growing from their start height up to ten rows; a short subject stays two rows, also while typing. The multi-line fields stand under their label in the full width of the column, in quotations, invoices and credit notes, on phones too.
- #6321: security (knowledge): a share with "show pictures" checks who embedded each picture (kept per page and file in the new table wiki_embeds) instead of the page's last editor. Only a person's own save of a text claims a picture; renaming, moving, relinking, restoring a version, unlocking a space or making a page from a colleague's template never does - such a picture is nobody's and stays hidden in the link until someone takes it out and puts it in again. Existing pages get their records once at the start (the last editor of then).

Package 2.1328 (Lieferkette: Digests per pins.py --update erneuern (ZAP-Abbild in ci.yml, Go-Bas).

### Changed
- Supply chain: refreshed pinned digests with `tools/pins.py --update` - Go base image in the Dockerfile, ZAP image in the CI security scan now pinned by digest; `WF_UNPINNED` is empty again (#6681)
- Supply chain: refreshed `embed/requirements.lock` (filelock 4.2.11, httpcore2/httpx2 2.16.2, resolved sub-packages only) (#6681)

Package 2.1321.0 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Fixed
- #6555: The webhook of a document flow follows the rules of the organisation's webhooks: before every call the flow's author must still be an admin of the workspace (else the flow pauses and the admins are told), failed calls are counted at the flow with the last error shown in the flow list, and after the last retry the webhook switches off and the admins hear it (News and push, "Integration problems"). The flow's other actions keep running; "Switch webhook on again" or saving the flow starts it again. A paused flow stays sealed with its webhook secret, also with the server switch for encryption off.
- #6480: The UBL e-invoice sent over Peppol is kept byte for byte (sealed in the office folder, checked against the send's SHA-256). The UBL download answers that file, also after a cancellation; the auditor (GoBD), retention and organisation exports carry it.

### Changed
- #6397: Search: every reader of the shared search index narrows to its own rows (visible projects, address books, calendars, rooms, the organisation) over an index before the words and the ranking; the name search runs as two arms instead of one OR, so the full-text index is used. An organisation no longer pays for the size of the others.

## [2.1330.0] - 2026-11-17

Package 2.1313.0 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- #6690 Phone tab bar: from 390 px width (e.g. a folded phone's outer screen, about 412 px) it holds 6 places (5 areas + More), below 390 px it stays 5; 600 px = 7 and 900 px = 9 as before. Labels stay on one line and end with "…" instead of widening their place. The hint in Settings ("This device fits 6 tabs") follows.
- #6367 First start: the service worker signs up only once the app stands (idle, at the latest after 5 s) and fetches the modules loaded on demand at most 6 at a time instead of all ~240 at once; with the data saver or a slow mobile connection it fetches none of them (they load on their first use, unchanged copies of the previous version are kept).
- #6557 Security (upload address /drop): sending to an agent through the upload token (field `to`, iOS shortcut / HTTP Shortcuts) needs its own switch "Also send to agents" (Settings > Integrations > Share from your phone; only in a signed-in session). A new token starts with it off; tokens from before keep it on and are told once (a notice in the app and in the answer of their first such message). Such a message is marked "via upload token" in the chat and reaches the agent with `origin: "drop"` + `untrusted: true` (message and `chat` event); the agent rules, the reference launcher (capability `drop_untrusted`) and docs/AGENTS.md treat it like text from outside: changes only after an approval card.

### Fixed
- #6134 Sign-in page on a new device: without a remembered language it speaks the browser's language when Kalmido has it (de, en, es, fr, it, nl; a region drops, fr-CA -> fr), else English - also when the server's answer is missing or offline. Only the display; the sign-in itself is unchanged.

Package 2.1316.0 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Fixed
- #6577: Importing an organisation export into an office that has documents already is no silent merge any more. The preview checks every target it offers: document numbers the target uses already and months the target has locked are listed, and the start is refused (409 with the list; checked once more inside the run). Before, documents with a taken number were skipped together with their positions, payments and PDF, and the target's period lock was ignored.
- #6577: A finalised document whose original PDF / XML is not in the file (or is refused by the scanner) no longer arrives as a document whose download fails for good: it is not imported and the result names its number; the preview lists such documents beforehand.
- #6577: The preview says before the start how many finalised documents the file brings and that undoing the import does not take them back; when the file's own period locks would lock months of the target with its own data, the preview and the result say so.

Package 2.1315 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).
### Added
- Auditor's export (#6472): new table `number_ranges.csv` per invoice / correction series and period with the counter and every gap as a range with its reason (from the office log, "draft carries the number", "without a reason"); `invoices.csv` gains address, VAT id, client master note, service period from/to, due date and the cancelled document's number, `positions.csv` the tax key. The number ranges page shows the same gap check under each series.
- Old documents (#6590): a single imported old PDF can go into the office trash and back (not in a closed month, not in a read-only moved copy).
### Fixed
- Auditor's export (#6472): recipient name and number come from the frozen recipient of the invoice, not today's client record (renamed or deleted client).
- Office imports (#6590): spreadsheet number cells are read as stored (0.125 no longer becomes 125); the same bank period as CSV and CAMT / MT940 is recognised as already there; bank CSV rows in a foreign currency are rejected instead of booked in the office currency; CAMT batch bookings keep every entry; DATEV import names the reason of every rejected row; fixed costs start in the current year; overlapping archive batches skip rows already imported.
### Changed
- Performance (#6403, part 3): `rc_receipts` gets indexes on area and billed invoice, so saving a receipt no longer scans the receipts of all organisations.
- Performance (#6409): idempotency keys are tidied by the hourly background run instead of in every write request with a key; an expired key is still never replayed.

Package 2.1322.0 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Fixed
- #6560 (2): The document rules of a mailbox work a folder off from a remembered position, oldest mail first, instead of looking at the newest 200 mails only; an older mail that fits is no longer missed. Changing the folder's rules (or a new UIDVALIDITY) looks at the folder anew. A mail that became no document yet keeps the position before it. Each rule shows how many e-mails of its folder are not checked yet ("N e-mails not checked yet").
- #6560 (3): Over the hourly limit of a request address (10 per sender, 60 per project) a customer's mail is no longer dropped: it stays unread in the instance mailbox and is taken in a later round (its attempt is not used up, it waits behind the new mails). The project's owner and admins get one notice per hour ("Integration problems").
- #6560 (4): The error-report webhook of a project checks at every call that the person who switched it on can still change the project; otherwise it pauses (403, the reason in the project's settings, one notice) until a list admin makes a new URL. Its limit per minute is counted for all web processes together.
- #6560 (5): The Stripe key, the Stripe webhook secret, the payment hook token and the secret of a document flow's webhook are always sealed, also with the instance switch for encryption off. Without a server key (KALMIDO_SECRET_KEY) saving them is refused (409) instead of storing them in plain text.
- #6560 (6): A webhook that switches itself off (failed deliveries, or its creator is no admin of the organisation any more) names how many waiting events were discarded and since when. Events queued while the creator was still an admin are no longer delivered after the demotion.
- #6560 (7): No part of a newsletter token or of a server agent's API key is kept or shown any more (the last four characters were); the settings show "Saved".
- #6560 (8): The payment provider's webhook checks the signature before the area's rate limit, so unsigned calls can no longer use up the limit of real events.
- #6560 (9): The documents mail logs the number of archive problems, never the names of the files in a customer's mail.

Package 2.1324 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Added
- #6709 Sheets: import .ods (LibreOffice / OpenDocument, also .ots), recognised by the `mimetype` entry of the archive: every visible sheet (at most 30) becomes a sheet of one table, header row = column titles, column types from value types (number, currency with code, percent, date, boolean, text), OpenFormula translated (cross-sheet references included, the rest kept as value and counted in the report), list validations become choice columns, merged and repeated cells unrolled within the cell budget; the same XML protection as the xlsx reader (no DOCTYPE / entities, depth and size limits, empty repeats never unrolled). Menu "Import CSV, Excel or ODS…" (new module `sheets/odsread.py`).
- #6589 Master data JSON import: "Overwrite existing" first shows a preview (new / overwritten per area, whether settings are replaced; `POST /api/office/import?preview=1` writes nothing); a file above 5000 entries per area is refused with area, count and limit instead of being cut silently.

### Changed
- #6147 Office bank page on a phone: one header row ("Import statement" + More with Walk through, Fetch from bank only when set up, Imports, Bank accounts); "Fetch from bank" is gone everywhere while fetching is not set up; the "Receipt missing?" hint folds away and stays folded; a suggestion card without a picture is compact. Walk-through: one main step (take suggestion, or search another receipt), upload, the four marks and split under More; the key hint names only keys that work; no tall empty dialog on a computer; the end view is the shared empty state.
- #6589 Nothing falls out of exports and imports silently: form answer CSV and document CSV have no 2000-row cut any more (spooled, read in pages; the form dialog says "newest 2000 of N, the CSV holds all"); the folder ZIP of the files, the knowledge export and the Markdown / Todoist ZIP write "not included.txt" (localised name) with path and reason for links, blocked / unscanned / damaged files, locked folders, too deep folders, shared and locked projects (new helper `core/omitted.py`); the knowledge export takes linked file store files the exporter may open along under `_attachments/` and rewrites the link, tables are named; the knowledge import detects the text encoding like the task import (`core/csvimport.text_decode`) and names pages read as Windows-1252; the xlsx / ods import reports columns beyond 200 (`report.cols_left_out`).

### Fixed
- #6589 / #6709 Review findings: the knowledge export takes file store files along only where the file store gates allow it (module card without files, areas off; shared decision `fs_content_ok`, office exception kept) and caps file references per export (`KALMIDO_WIKI_EXPORT_REF_MAX`, default 2000, the rest named); the .ods reader captures each list column once per row, at most 1000 labels, within a work budget over all sheets including hidden ones; the document CSV refuses more than 50 000 ids per call with a message.
- #6136 Test p2695_a_rowmenu_coverage counts the two task head menus of detail.js (reader and owner).

## [2.1326.0] - 2026-11-17

Package 2.1312 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), MCP-Zaun: Zaun-Zeichen vollständig entschärfen und).

### Changed
- #6540 Security (own mailbox): a workspace's own SMTP server sends only with a login (user name and password required as soon as a server is entered) and only on port 465 / 587 - port 25 or another port only for a host:port on the admin's internal mail server list. A mailbox saved before without a login or on another port sends nothing any more; the compose dialog says why. Through the own SMTP at most 30 mails per hour and person and 20 per person and receiving address and day; invoices, reminders and letters stay unlimited. Saving a changed connection, "Check connection" and "Fetch now" share one limit per person (30 in 10 minutes) and answer only "not reachable" or "login refused". The test has 40 seconds in all, a delivery 60. The admin's list 'mail' applies only to the server admins' workspaces, and an entry without a port opens only the mail ports (25, 143, 465, 587, 993).
- #6711 Calendar: a finger swipe leafs like a page on every touch screen (also the unfolded Fold): only the grid moves (month, week, day, year), the bar and the input line stay; the neighbour period lies beside it as an empty grid, glides fully into place when let go and is then drawn - no spring back, no second glide-in. The arrows, the trackpad swipe and the two-finger zoom are unchanged.

### Fixed
- #6493 Files: the document cards show their area (dot and name, e.g. "Private") in full; a long organisation name is shortened only when the card is really too narrow and then shows the full name as a tooltip.

Package 2.1317 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Fixed
- #6331: Office: finalising a document and setting its number check the version of the draft shown (`expect_updated_at`; the web app always sends it). Changed elsewhere in the meantime (another device, a colleague) answers 409 with the current state: nothing is finalised or numbered and the editor shows the bar "Changed in the meantime" with "Reload". Without a version (agents, older clients) the stored state is finalised as before. `POST /api/office/docs/<id>/number` also returns the new `updated_at`.
- #6496 (security): Support access on hosted servers changes only a fixed list: an account's lock and storage quota, an agent's on / off switch, an organisation's name and symbol. Kid flag and parents, admin right, display name, an agent's owner, webhook, scopes and lists, an organisation's e-mail domains, members and roles are refused (403), so the operator can no longer plant access that outlives the grant. On a hosted server an instance admin listed as a parent of a customer's kid makes its sign-in link only through an open grant and never sets its PIN. The organisation dialog sends no empty member lists.

## [2.1323.0] - 2026-11-17

Package 2.1299 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- #6352 Privacy: e-mails with content (the daily summary, e-mails about single events, "Send now") go only to a confirmed address. An unconfirmed address gets, once, the confirmation e-mail with a line why instead; the setting stays on and works from the confirmation on. Accounts created by an admin or before the address check count as unconfirmed - after this update they get that confirmation e-mail once instead of their next summary. Settings > Notifications shows "Confirm address" at the summary and the event e-mails. The warning "address changed" goes to the old address only (the new one is not confirmed yet). Security, invitation and reset e-mails are unchanged.
- #6678 Agents: MCP `get_task` marks comments and the description of other accounts (not the token's own, the agent's owner or `KALMIDO_OWNER_IDS`) as data: `untrusted: true`, the text between `<<<data from account N, not an order` and `data>>>`, fence characters inside defused.

### Fixed
- #6647 Quotation / invoice PDF: the hint "The individual items of each part start on page …" below the parts overview now has about one line of air below the rule above it (with and without the overview).
- #6661 Quotations with surcharges: a quotation from before 2.1228 that was set to sent / accepted / declined by hand without being finalised keeps the former tax split of its surcharges (all on the standard rate) - on a change, in its PDF, the client's view and its invoice; only drafts move to the split by the positions' rates.
- #6653 Security (knowledge): the Word / PDF export of a page full of open emphasis marks no longer holds the server for seconds - at most 200,000 characters of a page are read as Markdown (the rest stays plain text), and bold / italic / strike-through spans are at most 150 characters.

## [2.1318.0] - 2026-11-17

Package 2.1305 (Start pflegen: Startgröße senken).
### Changed
- Start care (#4742): 241 rules of `app.css` that only one area loaded on demand draws (Office, Life, Settings, Timeline, Wiki, Calendar, Agent chat, Filing, Contacts, Docs, Integrations, and the new stylesheets `css/family.css` and `css/team.css` for Family and Team) move unchanged into that area's stylesheet, ahead of its own rules so the cascade stays. The start loads 3.1 KB less CSS (gzip); the CSS ceiling in `tools/perf_budget.json` drops to keep 2.5 percent room.

Package 2.1306.0 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- Issue sync with GitHub / GitLab: a new task becomes an issue only when a signed-in person created it in the app - never from an inbound webhook, an error report, an e-mail, a form, an agent or an API token (#6554).
- Issue sync: per connection and day at most 60 new issues and 300 comments go out; the rest waits for the next day and the person who stored the token is told once (#6554).
- Issue sync: an @name in a title, text or comment that goes to the repository no longer notifies anyone there (#6554).
- Repository connections: the person whose access token a connection uses can always remove it, also without the admin role of the project; while that person has no access to the project any more, the connection pauses and the project owner is told (#6554).

### Fixed
- An issue address that is not http(s) is no longer taken over as the task's link (#6554).

Package 2.1309 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Added
- #6467: the database itself now protects the positions (`office_doc_items`), payments (`office_payments`) and office log (`office_doc_log`) of finalised documents, next to the existing lock on `office_docs`: no change of a position, payments only take a bank line (`bank_tx_id`), no deletion, the log is append-only (read entries may still be pruned). The deliberate exceptions (encryption passes, organisation import and undo, moving a personal office, the name fill of #6470) go through `ofx_release`; reference actions of the database pass. Way back of the app: `docs/OFFICE.md`.
- #6467: hash chain version 2 also covers the stored PDF and e-invoice XML checksums and the head fields (VAT mode and note, exchange rate, cancelled document, invoice type, progress references, due date, early payment discount, intro / closing text, order reference); older links keep their version and stay valid. The watchdog checks every office's chain once a day; a new break raises one admin alarm and a line `chain_broken` in the office log.
- #6471: the tax auditor's export (GoBD, Z3) is complete: folder `belege/` with the stored invoice and reminder PDF / XML, receipt files and entertainment bills byte for byte (file name and SHA-256 in `invoices.csv`, `dunning.csv`, `receipts.csv`, `meal_files.csv`; missing, locked or differing files named in `hinweise.txt`); new tables for bank lines, card statements and lines, vehicles, logbook and its log, entertainment, trips and trip items, asset register, ledger bookings and reminders (from the retention export's register with the period filter); `log.csv` carries the values before and after; trash and undone import rows stay in, marked in `Kennzeichen`; `chain_check.csv` and `chain_heads.csv` hold the chain check at export time and each chain's head (#6467 point 4). The module moved to `kalmido/admin/gobdexport.py`, the route is unchanged.

### Changed
- #6490: on customer documents (PDF, print view, approval page, invoice from the quotation) the markup line reads percent | base | amount ("15 % | 10.305,00 € | 1.545,75 €") instead of "1 flat | amount | amount"; the amount and all totals are unchanged, the e-invoice keeps quantity 1 x amount. Quotations that already left the draft and documents already sent or finalised keep "1 flat"; handling costs stay "1 flat".

### Fixed
- #6463: in a foreign currency, the last progress invoice bills the quotation's rest in the document currency, so progress invoices plus the final invoice equal the quotation to the cent (before: +/- 0.01 possible); the rounding line's text names its price in the document currency. The editor-save case with HUF moved into a hard suite (`p6463_fx_abschlag_invoice`).
- #6763: ruff and git leave the suites' data directories `tests/.data*` alone (a leftover stub on a test place turned the lint red).
- #6471: suite p6481_office_numbers reads the import columns of `invoices.csv` by name from `index.xml` (#6471 appends the trash mark and the file checksums after them).

## [2.1314.0] - 2026-11-17

Package 2.1300 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Fixed
- #6652 Security (import): a Markdown or Notion file with a list indented one step deeper on every line no longer takes seconds and gigabytes - the nesting is capped at the deepest allowed level while reading, deeper lines hang below it with the existing warning.

## [2.1311.0] - 2026-11-17

Package 2.1292 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Fixed
- #6478: cash-basis VAT after a finalised partial credit note - a payment is split by what stays open per tax rate (frozen
  tax lines of the invoice minus the finalised credit notes, books.bk_credit_rest / bk_pay_parts), in the books, the VAT
  return and the key figures; example 119 + 107, the 7 % line credited, 119 paid: VAT 19.00 instead of 13.52.
- #6569: server agent run places are shared fairly - longest wait first, an organisation (or a person without one) holds at
  most one place while others wait, waiting rows look for a free place right after a run, and a wait of more than 25 s
  gets one line in the chat (never naming who holds the places). The number of places is unchanged (KALMIDO_SRVAGENT_PARALLEL).
  New column agent_server.wait_note (migrations.d/6569.py).
- #6139: Lists: every failed write names what was not saved (apiWhat), loading errors of invitations, folder sharing and the
  project overview show an error with Retry instead of an empty list or "not shared", raw "Loading..." texts use
  loadingHtml, the board shows its empty state with lanes and when a filter hides every task; removing an invitation offers
  Undo (a step of this device).

### Changed
- #6124: contacts speak like the glossary ("view only", "Move to the trash", "Merges", "Person/Company") and delete like
  tasks: no question for one or several contacts, Undo in the toast, Ctrl+Z and Recent steps; an address book asks once.
- #6136: Lists: a reader gets the task menu with Copy link, Print (printable page) and History; the folder's Share dialog
  manages people, invitations and e-mail sharing only for the owner of a project in the folder.

Package 2.1297 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Abhängigkeiten: Rest-Härtung Lieferkette (Test-/CI).

### Changed
- Settings: every setting has its own name and one place - "Morgen-Briefing um" apart from "Tagesüberblick um", the field "Kanal" under "Zustellung", the bottom bar editor only under Navigation ("Menüs und Leiste unten"; Appearance links there with "Navigation öffnen"), one section for both completed-task switches, "For advanced users" once in Integrations, the app's server row in Account named "Server dieser App" (#6129).
- Supply chain: the CI tools (ruff, bandit, pip-audit, semgrep, coverage, tzdata) and the test packages install from hash locks (tools/ci/*.lock, tests/requirements.lock); tools/pins.py checks the locks against their sources, every workflow image for a digest (ZAP until the next `pins.py --update`, #6681), the sha256 lines of static/vendor/*/README against the files, and asks OSV for the CodeMirror bundle's packages too (#6509).

### Fixed
- Mail limits: an address is accepted only as one plain address (no angle brackets, comma, semicolon, quotes) in every form, and the daily limit per receiving address counts it in one form - "<a@x.de>" or "a@x.de,1.a" no longer get around the 5 mails per address and day, "address taken" at sign-up or the open bookings per address; event invitations count against the limit per receiving address too (#6548).

Package 2.1298 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Agenten-Dispatcher der App: fremde Änderung an Tit).

### Changed
- #6395: an admin's lock now holds the final deletion an account asked for until an admin releases it (it runs on its old day or at the next tick) or rejects it (the deletion is off, the account stays locked, its agents stay paused, the person gets a mail) - at most 30 days from the lock, then it runs without a decision. The server admins hear of it in the bell (News "delhold", row "usage", with a push) at the lock, 7 days and 1 day before the end. Settings > Users, the person's dialog: "Deletion on hold until …" with "Release deletion" / "Reject deletion", and "Hold deletion" for an account that waits for its own deletion. Routes `POST /api/users/<id>/deletion` and, for the hoster, `POST /api/operator/accounts/<id>/deletion` (`{"decision": "release"|"reject"}`). The person sees at the sign-in and through an old cancel link that the deletion is held and by when it happens. Suite p21298_b_delhold (new), p2553_a_selfdelete follows the cancel link's answer (409 held).

### Fixed
- #6556: notification channels (Slack, Matrix, Telegram, Signal) - a receiving server with a broken answer (no status line, a cut body: `http.client.HTTPException`, no `OSError`) now fails only its own channel and counts as its failure (it turns off after the usual number of failures). A waiting message leaves the queue only after its own try (taking it moves its `retry_at`; it is deleted when its result is written), so a broken send no longer drops up to 30 waiting messages of every channel and organisation. Suite p2240_b_channels (red without the fix).
- #6351: a locked account (by an admin or the hoster) locks its personal agents too: the owner's state is part of the one agent row (`AGENT_ROW_SQL`, `agent_active`), so the agent's API token answers `403` with the code `owner_locked`, the hosted MCP server answers `403` (no refresh), no new events are recorded and its webhook gets nothing. Nothing is written to the agent: unlocking the account lets it work again at once with the same token. Team agents are not affected. Suite p21264_a_ownerlock.

## [2.1310.0] - 2026-11-17

Package 2.1281.0 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Fixed
- #6425 Security, incoming mail: a mail is counted before and while it is taken apart (`kalmido/core/mailguard.py`, used by the
  instance mailbox, the workspace mailboxes, their document rules and the reading view). More than 2,000 MIME parts, parts more
  than 30 deep, a head over 256 KB, more than a million lines or header lines built to stall the header parser are refused in
  milliseconds instead of costing gigabytes and minutes; the refusal is logged with its reason and the mail stays in the
  mailbox, marked seen.
- #6425 Document rules of a workspace mailbox: a mail that breaks its own handling (a prepared header line, too many parts) is
  remembered for good and shown at the rule ("refused: too many parts or a header line that cannot be read"); it no longer
  ends the run of its folder every 10 minutes, so newer mails of the folder reach the rules again.
- #6425 Documents by mail (document address and mailbox rules): one budget per mail over all attachments (100 documents,
  100 MB unpacked), archives are unpacked and stored one after the other instead of all at once. A mail whose budget left
  files out is kept in the mailbox (not deleted or moved) and the rule says so; a ZIP without any usable file is no longer
  fetched again in every run.

Package 2.1287 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Security
- #6454: a team agent answers and writes with the rights of the person who asked: the run token is cut to that person's projects, the control level per project is capped to their role, contacts, calendars, wiki, sheets, files and channels outside projects answer at most with their own role; a channel mention reaches the agent only when it may be used by that person; an approval card without a project and an approval job need the approver's write right at the moment of the yes; organisation guests and read-only members cannot instruct a team agent.
- #6454 (review): one gate over every `/api/v1` route in a team agent's run for a person (`api/runfor.py`, `RUN_ROUTES`): events, chats, jobs, schedules, direct messages and message search show only the requester's own; routes naming another person answer 403 `run_person`; folders, groups and mails only in a run for an organisation admin (403 `run_closed`); projects where the requester is only a participant are left out of the run; an approved replay counts the person who said yes; a new route without an entry is closed in the run and fails the coverage test.

### Fixed
- #6470: the office log keeps the person's name (`office_doc_log.user_name`, sealed like `detail`) and a finalised document the finaliser's name in its sender snapshot, so after an account is deleted the log, "finalised by", the tax auditor's export and the retention export still name who finalised and booked; existing entries are filled once at start.
- #6300: a full invoice from a quotation with parts always settles the rest per tax rate (no 5-cent limit, also with percent positions): one position of that rate takes it as before, several get their own position "Rounding adjustment"; without VAT the part is compared as a whole; a delivery note keeps its quantities.
- #6443: a quotation with parts and markup that left the draft without being finalised (sent / accepted by hand) keeps the former markup per part when opened, printed and invoiced; opening writes only drafts; a quotation that had no parts before keeps the new rule.
- #6336: nightly CI red `p2695_a_rowmenu_coverage` - the selection bar's More (`data-msmore`) is a bar menu in RM_LEFT.

## [2.1307.0] - 2026-11-16

Package 2.1289 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- #6481: an invoice or correction takes a hand-set number only in the finalise dialog ("Number of your own (optional)", office admins), checked and given in the same transaction as the finalising; `POST /api/office/docs/<id>/number` refuses it for invoices and corrections (409), `POST /api/office/docs/<id>/finalize` takes `{number, reason}`. Drafts that already carry a number show "Draft with number - please finalise" in the list and the view.
- #6576: an organisation import (also a personal office imported into the private workspace) never arms anything: invoice series arrive paused (reason "paused by the import", their mail mark, try and failure count emptied), the office switches for reminder suggestions, overdue notices, quotation expiry notices and the bank / card receipt reminders arrive off, subscription reminders without their person; each with a warning in the import result and a hint in the preview.

### Fixed
- #6473: the procedure documentation derives the agents' office access from the office switches (which agents, drafts only, only a person finalises, log lines agent_read / agent_write) instead of "no access" unconditionally; the retention text names what happens when the organisation or account is deleted and at the end of the period; "Gutschrift" is "Rechnungskorrektur" / "Teilkorrektur"; a finalised correction is final, a mistake is billed with a new invoice (also in docs/OFFICE.md).
- #6475: with the switch "Small business" an invoice that shows VAT cannot be finalised (section 14c UStG), and the VAT note "small business" (section 19) cannot be finalised without the switch; a correction keeps the tax of its invoice. The editor hides the VAT choice for a small business unless a draft differs (then with the hint "As a small business without VAT").
- #6481: every number the counter passes because a document or the legacy archive carries it is an office log line with the reason, and the counter counts on to the next free number instead of ending with "already used"; a quotation cannot take a hand-set number of the invoice or correction scheme; `{date}` / `{isodate}` in a hand-set number must be the document date; a correction never dates before its invoice; the delete message of a numbered correction draft no longer names cancelling; finalised documents taken by an organisation import are marked "imported on ... by ..." in the list, the view and the auditor's export (`invoices.csv`: new columns `Importiert_am`, `Importiert_von` at the end; the PDF is unchanged).
- #6629: an invoice series paused because its area had no office admin tells the admin once there is one again (task "series paused" with the reason; it stays off until a person switches it on) and keeps its reason (new nullable column `office_inv_series.pause_why`, shown in the series list); the mail lock of a series invoice no longer stays on the connection after a database error; a mail still due is never overwritten by the next invoice ("Make now" sends it first); failed runs count strictly in a row.

## [2.1304.0] - 2026-11-16

Package 2.1291.0 (Retention export: only a complete, current export or the owner's own waiver lets records go).

### Fixed
- #6474: the retention export before deleting an account or an organisation counts only when it was complete (a file that could not be read or was locked by the virus scanner keeps the deletion closed, 409 with the names for who may export) and while no record to keep came after it (a new invoice, receipt, cash book entry ... asks for a new export).
- #6474: on a hosted instance only the person themself or an admin of the organisation does without the retention export; they declare it beforehand in the settings (`POST`/`DELETE /api/retention/me/waiver`, `/api/retention/org/<id>/waiver`, 7 days, ends with new records). An instance admin's `?retention=waived` for somebody else is refused without that declaration.
- #6474: received e-invoices nobody took over as a receipt count as records to keep on every instance and are in the ZIP under `received-einvoices/` with their list.

## [2.1301.0] - 2026-11-16

Package 2.1269 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Sicherheit Agenten: Freigabe-Karte zeigt bei Teile, Sicherheit Agenten: Agent speiche).

### Changed
- Agents, approval card: the card now shows the server's own description of the step a Yes runs, open above the buttons - who gets access to what, what moves where, how many tasks change, which values are written, by name instead of numbers. The agent's title and text stand apart below it as "The agent writes:". Steps that share, invite, send data out of Kalmido or move something to another project carry a warning line; something you cannot see is named as such. Yes stays locked until the description is there. The pinned bar at the top of the agent chat shows the same (#6450).
- Agents, deadline of an approval: "after the deadline: the agent's recommendation" no longer answers Yes for steps with a warning line (sharing, inviting, sending out, moving, something the person cannot see); those are declined like one-way steps (#6619).
- Agents, standing rules: a rule an agent stores is now only a proposal. The person it came from gets a card in their chat with the agent (the rule's text, the source, Confirm / Reject); the rule applies only after Confirm, and the same card then offers "Remove rule". Proposals show as "Proposed" in the agent's settings and can be deleted there; an agent can have at most 5 open proposals. Rules a person adds in the settings apply at once as before (#6451).
- Agents, text from outside: tasks from a project's inbound webhook, tasks made from git issues, and comments without a Kalmido account (reply by e-mail to a ticket, status page, public link, git) reach agents marked `origin` + `untrusted: true`; an @agent in a webhook task or git issue is no mention. The mark stays with the task (later events, `get_task`, task lists of the API). The reference launcher frames such comments as data (#6431).

### Fixed
- Mailbox: a crafted HTML e-mail could keep the whole server busy for minutes when opened (the CSS cleaner and the forward shortener ran in quadratic time). Both run in linear time now; style attributes and style blocks over 20,000 characters are dropped (#6421).
- Mail fetch: an e-mail whose import was cut off (restart, database outage, time limit, an error) was left marked as read and never arrived. Each mail now has counted attempts: it is tried again in the next rounds (the first try + 3 more), then stays in the mailbox and the mailbox's owners (instance address: the instance admins) get a News item "e-mails could not be taken over" (#6386).
- Tests: the parity check knows the API route of a team message's earlier versions (#6641).

Package 2.1282 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Security
- #6426: every ZIP reader checks its entry limit before `zipfile` builds an object per entry. The new `zip_guard` (core/zipread.py) reads the end record and the zip64 records itself, caps the size of the central directory and counts its entries without building anything; used by the shared in-memory reader (documents, mail attachments, bank statements, receipts, contacts), the task importers, the account / organisation import, both knowledge imports, the Paperless export import and the three .xlsx readers. A directory of a million entries is refused in well under a second instead of taking hundreds of MB.
- #6426: the shared in-memory reader refuses zip64 for real. Its check of the end record was passed with a zip64 record in front of it (1 entry announced, 300 000 built), reachable through a mail attachment.
- #6426: the JSON parts of the account / organisation import and the Paperless manifest are counted before `json.loads` (`json_guard`: values and containers, at most 3 million per part and 6 million per file); a part of tiny values took 24 times its size in memory. The Paperless manifest must be UTF-8.
- #6426: a new import upload (account file, knowledge ZIP in both ways, Paperless export) is rate limited per person (`KALMIDO_IMPORT_RATE`, own counter, default 30 in 10 minutes).

### Fixed
- #6426: the account import reads its sealed upload through a buffer, like the knowledge import (the sealed reader answers short reads at block ends).

[Unreleased]: https://github.com/Kalmido/kalmido/compare/v2.1374.0...HEAD
[2.1374.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1374.0
[2.1372.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1372.0
[2.1370.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1370.0
[2.1366.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1366.0
[2.1361.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1361.0
[2.1355.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1355.0
[2.1351.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1351.0
[2.1346.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1346.0
[2.1344.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1344.0
[2.1339.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1339.0
[2.1330.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1330.0
[2.1326.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1326.0
[2.1323.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1323.0
[2.1318.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1318.0
[2.1314.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1314.0
[2.1311.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1311.0
[2.1310.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1310.0
[2.1307.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1307.0
[2.1304.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1304.0
[2.1301.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1301.0
