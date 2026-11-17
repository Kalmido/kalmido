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

[Unreleased]: https://github.com/Kalmido/kalmido/compare/v2.1323.0...HEAD
[2.1323.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1323.0
[2.1318.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1318.0
[2.1314.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1314.0
[2.1311.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1311.0
[2.1310.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1310.0
[2.1307.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1307.0
[2.1304.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1304.0
[2.1301.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1301.0
