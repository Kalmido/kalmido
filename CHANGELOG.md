# Changelog

All notable changes to Kalmido are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Kalmido uses
[semantic versioning](https://semver.org/): every published change gets at least a new patch version, new features a
minor one. Releases in which operators have to do something carry a fixed section "Action needed"; the update notice
in Settings > Help shows that section of the target version.

## Older versions

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

## [2.1217.0] - 2026-11-15

Package 2.1192 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Teil 1/6: Sammelpaket: Aufgaben ohne Paket (Dispatcher), CI-only rot: p2458_b_ui u. 7).
### Fixed
- Tests: six phone UI suites followed the phone rows of 2.1151 (#3835: row symbols hidden like screen-reader text, one "…" or a long press instead) - p2190_family_ui and p251_ui / p242_ui no longer count the hidden symbols as touch targets or overflow, p2458_b_ui accepts the hidden read-later buttons, p2150_ui opens a token's permissions through the row's "…" on a phone, p2134_ui opens a section's add sheet by a long press on its head (#4049, #6192, #6190, #5063, #5172, #4791).
- Tests: p5787_queue_gate and p2534_c_hard_shards follow the CI change of #6063 (tests-done needs the plan, an `if:` line before the shard limit) (#5841, #6084).
- Tests: p2162_a_api dates the payment on the invoice's own date - a CI run over midnight dated the invoice a day after the test's start and the payment was refused (#6197).

Package 2.1199 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Teil 1/6: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Weich rot: v11_ui u. 8 weite).

### Fixed
- Lists: a double click on a task title opens the title field again with the caret at the click, also when the first click opened the task and the list moved under the mouse (#5428)
- Documents: in a narrow document view (the right half of the split view) the title keeps at least 12rem and the actions wrap, the longer "Move to the trash" button left the title 0 px wide (#6032)
- Tests: twelve UI suites red in the full CI follow the wanted changes of the polish rounds (wiki page menu always shown, wiki editor in the reading column, wiki list bar in one row, "No grouping", empty-state titles, watcher count, Scan in the files' "..." menu on phones, "Move to the trash", the kept-trash note) - v11_ui, p2138_d_ui, p2891_d_ui, p21121_a_ui, p2554_a_docside_ui, p2528_c_ui, p2473_c_ui, p299_b_ui, p2172_a_edit_ui, p2725_d_ntbar_ui (#5673 #6207 #6210 #6206 #4981 #6208 #5703 #6211 #4725 #6209)
- Tests: p2169_a_ui closes the computer window for the offline phone part (two windows shared one offline copy with different sign-ins) and names the state when it fails (#5909)

## [2.1201.0] - 2026-11-15

Package 2.1174 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).
### Added
- Contacts: the contact editor has a Person / Company switch at the top; a company has no first / last name, its name is the company's. Companies show a building instead of initials in the list, the card and the editor (#6119).
- Contacts: a company's card lists its people (contacts of the same workspace with that company name, no new table); a person's company is a link to the company's card when there is one (#6119).
- Contacts: after an import, "Show imported" clears an active search, group or folder and shows the address book imported into (#6123).
- Phone: the header's "…" menu always has "Recent steps" below Undo / Redo (persons only, not agents); on a computer the menu stays as it was (#6164).
### Changed
- Contacts editor: e-mail, phone (digits, spaces, + - / ( ) only) and website are checked in the field when it is left and before saving - the field is marked with a sentence below it and the dialog stays open, also when the server refuses; "A name or a company" is a field note instead of a toast; the look-alike note stands at the top of the dialog with the focus; Esc / backdrop / Cancel ask only after typing; Ctrl+Enter (Cmd+Enter) saves; a new contact with a company name gets e-mail kind Work; on a phone the remove x of a phone / e-mail stays in its line. Values the contact already has (from an import, a sync, a booking) never block saving (#6120).
- Contacts API: a phone number written through the app, `/api/v1` or MCP holds only digits, spaces, + - / ( ) (400 naming the field "Phone"); numbers the contact already has, imports, CardDAV and bookings stay as they are; a refused website names the field "Website" (#6120).
- Contacts: the header menu has one "Import…" and one "Export…" (book, then format) instead of two rows per address book; the address book menu has one Import and one Export; the address books dialog explains books / folders / groups in one sentence, shows each book with a book symbol and who it is shared with on a second line that wraps; "Delete" is the last entry of a card's menu (#6123).
- Contacts: the CSV import guesses e-mail / address columns as Work when the column name says so or the company column is mostly filled (#6123).
- Contacts: "New contact" and Import no longer create a private address book "Contacts" quietly - a person without a writable book is asked, with "Create your own address book" (#6122).
- Contact history: events are no longer listed there, they stand in the card's Events block (#6119).
### Fixed
- Menus: a menu that fits neither below nor above its button stays as near the button as the window allows (an address book's menu in the dialog opened at the window's top) (#6123).

Package 2.1189 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- One offline sentence in every area: calendar, contacts, chat, notes, office, projects, wiki, files, polls, agents and lists now say "Only available online." instead of "Offline: only works again with a connection" (#6189).

Package 2.1201 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- Quotation PDF: the discount note reads "5 % on the discountable positions" (was "marked positions", the PDF marks nothing); an optional or alternative position below a section heading that already says so ("Optionen", "Alternativen") prints without the prefix "Optional:" / "Alternative:", also on the approval page; section headings of the positions table one step larger (as strong as the subtotals) with a little more air above them (#6175)

[Unreleased]: https://github.com/Kalmido/kalmido/compare/v2.1217.0...HEAD
[2.1217.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1217.0
[2.1201.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1201.0
