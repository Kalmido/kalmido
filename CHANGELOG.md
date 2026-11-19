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

[Unreleased]: https://github.com/Kalmido/kalmido/compare/v2.1412.0...HEAD
[2.1412.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1412.0
[2.1405.0]: https://github.com/Kalmido/kalmido/releases/tag/v2.1405.0
