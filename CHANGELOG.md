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

[Unreleased]: https://github.com/Kalmido/kalmido/compare/v2.1301.0...HEAD
[2.1301.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1301.0
