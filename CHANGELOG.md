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

[Unreleased]: https://github.com/Kalmido/kalmido/compare/v2.1201.0...HEAD
[2.1201.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1201.0
