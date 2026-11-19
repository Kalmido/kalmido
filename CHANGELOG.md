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

[Unreleased]: https://github.com/Kalmido/kalmido/compare/v2.1405.0...HEAD
[2.1405.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1405.0
