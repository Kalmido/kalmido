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

[Unreleased]: https://github.com/Kalmido/kalmido/compare/v2.1307.0...HEAD
[2.1307.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1307.0
[2.1304.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1304.0
[2.1301.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1301.0
