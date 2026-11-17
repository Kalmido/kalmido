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

[Unreleased]: https://github.com/Kalmido/kalmido/compare/v2.1344.0...HEAD
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
