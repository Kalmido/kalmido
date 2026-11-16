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

## [2.1249.0] - 2026-11-16

Package 2.1225 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).
### Added
- #5862: A private knowledge area can be shared as a whole with a person too (until now agents only): *Can view* or *Can edit*, the same question before (which folders and pages they will see) with the folders to keep out ticked right there, and single folders kept out per person afterwards (*Who sees the whole knowledge area*, *Exclude folders…*, "not for <name>" on the folder). The person finds it under *Shared with me* as the folder "Knowledge" with the owner's name; with *Can edit* they add pages and folders there, also at the top. An organisation's area stays with its agents (guests and the accounting person never get the whole area). Ending the share and making it again (Undo) keeps the exclusions; deleting an account hands on only what the person sees. New column fs_shares.excl (migration 5862, new column only).

Package 2.1230 (Start pflegen: Startgröße senken).
### Changed
- Start care (#4742): the rules of a list (`rules.js`) and the export of an organisation or the own office (`orgexport.js`) load on demand; the start loads 10.8 KB less JavaScript (gzip), 2.2 KB less of the language core and two scripts less. The start ceilings in `tools/perf_budget.json` are lowered by the same amount.

Package 2.1231 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- #5880: Projects: the old column `lists.archived` is gone (stage 3b of the state marker, one-way). A project's archive is its state marker plus `archived_at`; before the drop every start fills `archived_at` for projects archived without a moment (before 1.6.1), clears a stale one and sets the marker once more (`core/liststate.py`); the trigger `kalmido_list_state` reads `archived_at` now. Exports ("my data", account and organisation export) still give the key `archived`, the import takes it from older files, and undo steps from before the change still go back. The database's back limit rises to this version: going back needs a backup from before.

Package 2.1239.0 (Bündel: Chat: kleine graue Fußzeile mit Modell/Effort/Klas).

### Added
- Agent chat: an agent's answer may name the model that wrote it - `run_meta` `{model, effort, klasse, grund}` on `POST /api/v1/agent/chats/{user_id}` (JSON or multipart, MCP `send_chat`); short texts, unknown keys dropped, not an object = 400; given back in the answer and every read of the chat (#6261)
- The app shows it as a small grey text next to the time under the agent's bubble, e.g. "Fable 5.2 · Effort hoch" or "Opus 5.5 · kurz sortiert", the reason as its tooltip; messages without it stay as they were (#6261)

Package 2.1241 (Bündel: Org-Farbe: Kalender und Termine, Org-Farbe: Wiki-Bereiche und Seiten, Org-Farbe: Team-Chat u. 2 weitere).

### Changed
- Organisation colour in the calendar: events of an organisation's calendar wear its stripe next to the calendar colour (month, week, day lists, Today), the event popover and the edit dialog show it, under "All workspaces" event rows say where they come from; the calendar list shows the organisation's dot and name for every member, not only the owner (#6181).
- Organisation colour in the wiki: an organisation's space wears its stripe in the panel, the list of spaces and the overview; the open page of an organisation is marked (stripe, input frames, its tone under "All workspaces") (#6182).
- Organisation colour in the team chat: channels, groups and project chats of an organisation wear its stripe in the panel and the list, with their origin under "All workspaces"; the open conversation's head and input frame are marked; direct messages stay neutral (#6183).
- Organisation colour in files and documents: an organisation's space wears its stripe in the panel and on the phone's space buttons, document cards of an organisation carry the stripe and their origin under "All workspaces", the open space, folder or document is marked (#6184).
- Organisation colour in contacts: contacts of an organisation's address book wear its stripe (the address book's own dot stays) with their origin under "All workspaces", the open card is marked, address books and the panel's spaces carry the stripe (#6185).
- Core: `wso_row(w, style)` keeps an element's own inline style, `wso_mark(el, w)` marks an element already drawn, `sbb_treeHtml` nodes take `wso`, the "All workspaces" overview rows carry their space's stripe (docs/dev/kern.md "Organisation colour").

Package 2.1244 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Fixed
- Calendar: the popover of an event in another time zone shows the date of that zone next to its times (22:00 New York on Sunday no longer says Monday); when your own day differs, your time carries your date (#6263).

Package 2.1224 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).
### Changed
- Tables wear the organisation colour: table and folder cards of an organisation carry its stripe, the group headings its dot, the panel entries their stripe, and an open table marks the page like an open project (#6186).
- Time tracking shows the organisation of each entry and report line (dot + name; other organisations also inside one workspace), the timesheet card wears its colour (#6187).
- Command palette and search hits, the trash, news and the bell (now also under "All workspaces"), project group heads and favourite agents show their organisation's colour (#6188). The core block `wso_origin` has a mixed mode for pages that are mixed in every workspace.
- Files: one "Move to" picker with tree and search for a row, the selection and the file view (no cut after 60 folders, title once, current folder ticked); Share adds a person at once with "Can view", role and end date beside each person, one sentence of explanation, people shared already are not offered again; the file view's Shares tab manages public links (copy, new address, switch off, create); the lock dialog explains in three short sentences (#6113).

## [2.1245.0] - 2026-11-16

Package 2.1214 (Bündel: Kern Stufe 3 Nachlauf: alte Tabellen-Leser von Kal, Sammelpaket: Aufgaben ohne Paket (Dispatcher), Polish Wiki: Wortwahl vereinheitl).
### Changed
- #6117: Contacts and clients put the list beside the card only when the content area (not the window) has room for both (43rem); with the side panel open on a tablet the card opens alone and full width with a back arrow, like on a phone. On a computer the list is wider (about a third, 14-26rem) and long names wrap instead of being cut. Keyboard: arrow keys, Home and End move through the list (down from the search field), opening a contact puts the focus on its name, Esc closes the card at every width.
- #6118: Contacts on a phone - one row on top (search, filter with the number of active filters, new, more); group and address book filters sit behind the filter button; the "Switch on Office & finance" hint only in an empty list or once, never above a card; the card head shows name and position under the picture over the full width with Edit and More in the head row, "Arrange blocks" moved into More, no sideways scrolling, no breadcrumb beside the back arrow. The selection bar of contacts and clients shows whole words under the symbols, what does not fit goes into "...". The page is called "Contacts" instead of "Address book".
- #6091: Knowledge wording (German) - the area is "Wissen" everywhere, "Arbeitsbereich", "Version" instead of "Fassung", "Schlagwort" for tags, du-form in the conflict, the device lock "Bearbeiten sperren (dieses Gerät)", "Verweis kopiert", one/many attached files, "Lesestil"/"Schlicht", no Markdown / ZIP / end-to-end words; help texts and glossary follow.
- #6092: Knowledge - deleting is "Move to the trash" everywhere (page menu, row, selection bar, attachments) without a question and with one toast offering Undo; switching off a public link has Undo instead of a question; a cancelled import in the browser says how many pages went to the trash, with Undo; info windows (import report, file too large, no room) use the shared dialog with OK; in the history the current version is no longer clickable and the hint is plain; the conflict window marks the lines only each version has (one below the other on a phone).
- #6132: Notice bars - offline is one sign (the header chip in words, click to retry), the bottom bar only while changes wait; "New version available", upload bars and the code hint share one stack that covers nothing (under the header on a computer, above the tab bar and the "+" on a phone) and "New version" can be closed; the code hint is for server admins only.
### Fixed
- #4782: A calendar's or address book's share that ran out no longer blocks moving it to another workspace; run-out shares that would not fit the new workspace are taken back the core's way (restorable, in the history) and the share rows are locked during the move. Developer docs: what happens to the nodes when an organisation is dismantled.

Package 2.1213 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).
### Added
- Team chat: "edited" under a message opens its earlier versions, as in the agent chat; kept in the core's history (kind tchat_msg), an encrypted message only as its ciphertext, readable by the room's members; API `GET /api/v1/team/messages/<id>/versions` and MCP tool `team_message_versions` (#6166).
### Changed
- File view: Word / Excel / text show their preview right in the preview column, other kinds (ZIP, video, audio) a file sign with "No preview for this kind of file" and Download; zoom and page bar only where there are pages; on a phone the title has its own row and Back names the folder you came from (#6110).
- Start page: titled "Start" beside the sidebar, two columns without holes at tablet width, entries from another workspace carry its colour dot and name, the Today tile and the line on top count the same (#6126).
- Lists at a middle width or with a task open: archive card, selection bar and breadcrumb stack instead of being squeezed (#6140).
### Fixed
- A list scrolled down and then shown as a calendar opened out of sight of its month name and views: a list keeps its scroll place per view now (#6140, #6168).

Package 2.1218 (Bündel: Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Fixed
- Import: a project whose ticket key another project of the target workspace already uses arrives without a key; its task numbers stay as old keys (APP-3 still finds the moved task) and the import report says so; a key from the file is normalised or dropped when invalid (#6202)

Package 2.1227 (Bündel: CI: Zug-Push fährt nur harte Testteile (Stufe rele).

### Changed
- CI: the train's release push ("X.Y.Z: Live-Zug (...)") runs the new lean stage "release" - Lint, scanners, semgrep, e-invoice validators, ZAP and only the hard test groups (tests/hard_suites.txt, shards "Test suites N/M release hart"); the soft suites run in the nightly full run and by hand. This gives the merge queue its runners back (the full run per train push held up to 16 runners for 3.5-4 h). The release gate (tools/ci_gate.py) counts a green release-stage run like a green full run; release.yml waits at most 150 min instead of 250 (#6253).

## [2.1240.0] - 2026-11-15

Package 2.1216 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- Files and documents: loading, errors and empty states use the shared blocks - a folder, the folder tree, the document list, the file search, a saved view on Today, the History / Sharing tabs, the external links and the scan inboxes show a clear sentence with "Try again" instead of raw server text, an empty spot, a second toast or "No results"; a folder that is gone or not shared shows the no-access block with "Back to the files"; the title of a folder not loaded yet is its name or "Files", never "Organisation" (#6109).
- Uploading files or documents lists the refused files once (the list of what stayed out) without an "Error 400" toast beside it; the 400 of `POST /api/docs` carries the reasons as `error` too (#6109).
- Release tooling: the pull request lint's i18n hint says a build job leaves new texts in the big language file - the merge queue moves them per commit (#6231).

Package 2.1221 (Bündel: Teil 1/6: Sammelpaket: Aufgaben ohne Paket (Dispatcher), Weich rot: p2905_b_docview, Weich rot: parity u. 5 weitere).
### Fixed
- #4736 #6241 #6242 #6243 #6245: Suites that still checked the behaviour before intended changes follow them: a phone's "..." keeps "Recent steps" (#6164), contact events sit in the card's Events block instead of the history (#6119), PDF section headings print in the section-title size (#6175), the offline toast reads "Only available online." (#6189). Tests only, no app change.
- #5642 #6244: Two UI suites that were red only on the slower CI runner wait for the real state: the document view opened by its address before Escape, the office view up to 30 s to load.

Package 2.1211 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- Command search: extra line and kind in the normal font, open tasks with a neutral ring instead of a tick, commands only match whole words, "Nothing found" above "Create as task", own empty sentence when moving; Settings > Help points to the one shortcut overview; the start page search tile uses the same placeholder (#6128)
- Office device dialog: the sections keep their arrow and open as soon as any field inside is filled (serial number, vendor, receipt ...); units (EUR, €, %, days) sit right beside the field; the empty sets list has a symbol and "Import…" looks like a button (#6148)
- Team chat, chat windows and agent chat show loading and failed states from the shared blocks with "Try again", never the raw server text; the input is locked while loading or failed; "Load older" fetches one page at a time without duplicates and shows its error at the button; one offline sentence (#6098)
- Deleting an own team chat message no longer asks first: it is deleted with Undo (also under "Recent steps"); a new group has Undo like a new channel (creator only, within an hour, while empty); "Leave" only asks where you cannot come back yourself and says why; the agent chat shows an error only once (#6099)

### Fixed
- A chat window no longer stays on "Loading…" forever after a load error (#6098)
- The Undo toast of a new channel no longer vanishes when the new conversation opens (#6099)
- Office settings: the number ranges keep their preview and hint under the field (the unit-beside-field rule left them out) (#6148)

Package 2.1228 (Bündel: Angebote: Zuschlag in Prozent auf die Summe als ei).

### Added
- Quotations: a surcharge in percent ("Zuschlag", e.g. "Mehraufwand 15 %") as its own line for every organisation and every person without one, no industry pack needed: switch "Calculate Surcharge" in the quotation's calculation, own line title, on the positions marked for it (new ones are), after the positions, before discount and tax (#6254)
- Agent API / MCP: quotation drafts take `surcharge` `{pct, title?}` (`null` = off) in `create_offer_draft` / `update_offer_draft` (#6254)

### Changed
- Surcharges (also the industry packs' handling costs / markup) carry the tax rate of their positions: one share per rate; the invoice and progress invoices from a quotation take them as one position per rate, so the e-invoice has a line per rate; a quotation finalised before keeps its frozen calculation for its invoices (#6254)
- The default title without a pack is "Zuschlag" / "Surcharge" (#6254)

### Fixed
- A surcharge on a negative sum of marked positions no longer lowers the net without a line (#6254)

## [2.1229.0] - 2026-11-15

Package 2.1212 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).

### Changed
- Calendar sharing uses the same Share dialog as projects and folders: cross on top and "Done", the owner first, the role words "Member" / "Read-only", "Shared" as feedback; taking a person out needs no question and can be undone (toast and Ctrl+Z), the share comes back through the shared core with its role (#6156).
- Calendars window: the calendar name is shown in full and the line "shared with 2 people" (or owner and role) stays visible below it on every width (#6158).
- An event in another time zone names the zone at its times: in the event window "10:00–11:00 New York · 16:00 your time", in the editor next to Starts / Ends (#6158).
- The task an event prepares stands in the editor outside "More options" and is loaded when it is not in memory; it also shows and opens from the event window (#6158).
- Subscribed calendars carry a link mark, own repeating events the repeat mark; "Create task from event" is a quiet button; no availability bar for an existing event without guests (#6158).

### Fixed
- Calendar: loading and errors use the shared blocks (event window, subscription link), failed loads say what failed with "Try again" instead of closing or showing raw server texts; the repeating tasks' dates, the people list and the editor's save error no longer fail silently (#6159).
- Deleting an event, a date of a series, a calendar or a subscription goes into the history, so Ctrl+Z takes it back like the toast (#6159).
- The view choice is a named group, the trash is the last row of the Calendars window, no inline styles or hex values left in the calendar files, "Termin" in the day plan (#6159).

Package 2.1215 (Bündel: Sammelpaket: Aufgaben ohne Paket (Dispatcher)).
### Fixed
- #6095: Team chat on a phone with the keyboard open - the head and the pinned message shrink to one line (no sender, no member line, only the first pin), a focused search replaces the pinned bar; without the keyboard nothing changes.
- #6100: The bell on a phone - an approval or mention entry is one text block (at most three lines) instead of words in columns; an approval shows "X is waiting for your approval" with the question below in normal type; agent texts in the bell and in the message pop-up carry no Markdown marks (**, `, #).

## [2.1226.0] - 2026-11-15

Package 2.1198 (Bündel: Polish Wiki: Seiteninhalt lesbarer - Kopfdaten, Li, Sammelpaket: Aufgaben ohne Paket (Dispatcher)).
### Changed
- #6090: Wiki pages read like text - the front matter shows as fields (key as a word, dates written out, the event of minutes as a link "Open event"), folded into one line in the editor (a click opens it); page links, "Linked from", search hits and tag pages show the page name with its folders quietly beside it; a task link in the editor shows "#1 Title"; a daily note is titled by its date ("Sa, 14. Nov 2026"), the folders "journal" and "Templates" read "Daily notes" / "Templates" in the person's language (the paths stay); a page from an own template drops empty bullets / boxes and the template's front matter (tags stay); search snippets without the title and without raw Markdown; the editor's placeholder without [[...]].
### Fixed
- #3642: The organisation export takes the old ticket keys of tasks (APP-12 after a key change or a move) and the people taken off a project by hand along; the import writes them onto the new tasks and projects, so old keys still find their task and a person taken off stays off. A moved project with a key now counts on from its highest number (a new task got number 1 again).

Package 2.1205 (Bündel: Organisations-Farbe als gemeinsamer Baustein für a, Sammelpaket: Aufgaben ohne Paket (Dispatcher)).
### Added
- The organisation colour is one building block of the shared core (docs/dev/kern.md "Organisation colour", wscolor.js `wso_row`, `wso_origin`, `wso_open`, `wso_sync`): an entry of an organisation in any area gets the stripe on its left edge, an area registers its open object and gets the same marks as an open project (input frames, the organisation's tone under "All workspaces"), also when it draws the object later. Projects use it with unchanged behaviour; the other areas follow (#6180-#6188) (#6179).
### Fixed
- A project address without a project (deleted, no access, a typo) showed an empty project with "+ Section" and an add field that led nowhere; it now shows "This project does not exist (any more) or you have no access" with "To the projects", without add field or + button, and it is no longer remembered as the next start page. An unknown address still opens the Basket, now with the hint "This page does not exist" (#6133).

Package 2.1210 (Bündel: Wackel-Test setup_ui, Weich rot: p21109_a_ui, Weich rot: p21177_a_wiki_polish_ui u. 2 weitere).

### Fixed
- Test suite setup_ui no longer races the login screen of an existing install: it waits until the screen is drawn (the boot screen fades before the login form arrives) (#5504).
- Test suites follow intended changes: p21109_a_ui expects the empty receipts page without heading (#6223), p21177_a_wiki_polish_ui starts Select on a phone through the list's "…" menu (#6224), p2139_c_ui expects the shared error block on a page that fails to load (#6225), p2357_d_wording expects the thank-you as the standard invoice closing (#6226).

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

[Unreleased]: https://github.com/Kalmido/kalmido/compare/v2.1249.0...HEAD
[2.1249.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1249.0
[2.1245.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1245.0
[2.1240.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1240.0
[2.1229.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1229.0
[2.1226.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1226.0
[2.1217.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1217.0
[2.1201.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1201.0
