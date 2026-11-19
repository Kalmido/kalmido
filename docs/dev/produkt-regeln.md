# Product and UI rules

*For everyone who builds Kalmido (people and agents). Since 2.1436.0 (#7262).*

These are decisions of the product owner that every package keeps. Each rule names the day it was decided and the tasks
that carry it; the task text has the details. A package that would change one of them does not change it silently: it
leaves that part out and puts the conflict before the product owner (a rule once turned round without asking, #322 in
2.24, and twelve decisions were undone without anybody noticing, #6844). The package reader checks a package against this
file. What can be seen in the text of the code is checked by `tools/check_rules.py` as well (last section).

## Principles

- **Kalmido calls no language model itself** and gets no external AI provider; the connected agents do the writing.
- **The tenant boundary is strict**: nothing of one organisation or person reaches another without a share.
- **Usability before features** (02.10.2026): every change is tried in the phone scenarios too (typing while live updates
  arrive, the keyboard, a folding phone). A control people use is never hidden to save space (04.10.2026: Today / Tomorrow,
  the pin beside the priority).
- **Only remove what was decided.** New push kinds can be switched off.
- **One account per person, private and company in one view** (08.10.2026): a freelancer without an organisation is their
  own admin and gets the same functions, agents and office included (12.10.2026); no function is bound to the membership
  of an organisation. All data can move between an organisation and Private; an importer names the target area
  (17.10.2026, #1940, #1941). Every package proves it with a test as a person without an organisation
  (`tests/freelancer_coverage_test.py`).
- **Core, industry pack, single customer** (04.11.2026, #4573): every function belongs to exactly one layer. The core is
  for everybody and neutral in wording, examples and templates. An industry pack only shows with the industry chosen (one
  app-wide switch, default none); film functions carry the list tag of the film industry. A single customer's wish only
  comes as its own pack, never into the core. Every task brief names its layer.
- **New areas stand on the shared core** (05.11.2026): no share table, check function or save path of their own;
  see [kern.md](kern.md). Extend the core instead of building a special way.

## Navigation and layout

- **One navigation** (21.10.2026): a narrow icon bar of the areas plus ONE panel with the area's content; every area
  remembers its last page. Never a second app column ("an app inside the app"). The calendar has its own icon; the office
  groups fold independently; trees show the top level and one more. The phone works the same, the icon row at the top of
  the drawer (23.10.2026).
- **"Project", not "list"** in the interface; internally `list` (21.10.2026, #2624).
- **Projects are lists and their views only** (27.10.2026): under Projects > Views only what shows lists and tasks
  (`SIDE_VIEW_KEYS` in static/js/render.js); notes have their own icon.
- **Every document area works alike** (23.10.2026, 26.10.2026): office, tables, knowledge, files and lists unfold in the
  bar, have folders, are shared with people and agents, and a folder's rights hold for its content like a file system;
  every office area (quotations, invoices ...) unfolds like a list with documents, subfolders, dragging and sharing.
- **One area instead of two surfaces** (06.11.2026, #4885): files and documents are ONE area with one folder tree; folders
  with recognition show the document view, sender / type / tags / number / "to check" are filters below the tree. New
  functions are built for the common area, never for one side only. Title and file name are separate (#4876).
- **Use the space** (06.11.2026, #4840): lists, overviews, dashboards, office and files run over the full width of a large
  screen, no upper limit; exceptions are reading text (the width switch, #4808) and forms (one column, #4833). Lists work
  like a table (#4857): with few columns the title takes the room, with many the title goes up to about 40rem and the
  other columns share the rest, numbers right-aligned, column widths draggable per list; dragging a handle rewraps the
  content live (#4860). Tag fields are pills with their own suggestion list from the first letter, no datalist (#4862).
- **Handles** (06.11.2026, #4829, #4830): every content can be moved with its handle as far as it goes; no fixed caps,
  the only limit is the minimum width of the neighbours.
- **Arrows on rows** (06.11.2026, #4908): › (the icon `right`) opens a view or a form; ˅ (`chev`) only unfolds in place
  (aria-expanded, it turns).
- **Organisation colour everywhere** (14.11.2026, #6179 - #6188): whatever belongs to an organisation carries its colour
  in every area, in the navigation (the entry marked) and in the opened object; Private stays neutral - except in a
  mixed view ("All workspaces"), where Private wears the person's own chosen Private colour, if any (#6957, #7393).

## Touch, gestures and calm

- **The finger decides, not the width** (07.11.2026, #5087): operation (gestures, autofocus and keyboard, draggable,
  hover replacements, keyboard hints, touch CSS) depends on one touch switch (`(pointer:coarse)` or `(hover:none)`);
  `isMobile()` and the width are for layout only. Touch devices of 768 - 1023 px keep the tablet layout (no tab bar at
  the bottom, no plus button, no favourites swipe bar).
- **Long press = the menu, like on tasks** (04.11.2026, #4607, #4608, #4612): an entry with a menu of its own opens it on a
  long press on the phone (a sheet at the bottom) and on a right click on the computer; the click after the press opens
  nothing. Selecting is "Select" at the top, like on tasks (`cm_bind` / `ms_rowMenu` in static/js/multisel.js). Exceptions
  stay where a long press drags (calendar, timeline, roadmap, start tiles, tables).
- **Sheets** (07.11.2026, #5078): a bottom sheet is dragged (bigger, smaller, away) only at its handle at the top; a swipe
  in the content always scrolls, also at the top.
- **A new tab or window only with a mouse** (04.11.2026, #4574): buttons that open a browser tab or a window of their own
  show only with `mw_desk()` (static/js/miniwin.js: hover and a fine pointer), never by screen width. Pictures open in the
  app's preview (`attLightbox`) everywhere. On a touch device nothing leaves the app unasked.
- **Calm view** (08.11.2026, #5223 - #5227): the view moves only when the person caused it and expects it - no scroll jump,
  no automatic scrollIntoView, no redraw or reload that loses the reading place or lets content above it grow. A deliberate
  jump (a link, a search hit, "go to ...") is exactly one calm jump (`tools/check_scrolljump.py`).

## Settings

- **Every settings page like the general menu** (19.10.2026): sub-areas with icons; every field saves itself with a short
  "Saved"; no save bar, no extra side bar. Nested editors get a colour code and a clear heading. A one-time import lives
  centrally under Settings > Import old data (#2335); running exports stay where they are.

## Look

- **Plain and modern** (May 2026): one accent, one text colour, one muted colour; status colours only for a status; bold
  only for a selection and titles. Cool greys, never warm ones (22.10.2026: `#eceef2`, `#5f6673`).
- **App icons instead of emoji** (17.10.2026: `ic(...)`); 👍 and 👎 are the only emoji in texts.

## Words

- **No "chip"** (13.10.2026): "show in the task row", "label".
- **No product names of others for functions** (18.10.2026); a hint at compatibility is fine. Public texts name no
  competitors.
- **The own workspace is "Private"** (04.11.2026, #4605) everywhere, never "My storage", "My area" or "personal office";
  "personal" only for what belongs to one person (a personal agent, API tokens, the licence, a tag).
- **History and activity** (08.11.2026): "history" is what happened to this one thing (a task, a page, a cell); "activity"
  goes across an account or an organisation. Menus rather name what one sees ("Only comments", "Only changes of others",
  "All changes", #5162). Both stand in TRANSLATING.md.
- **The rules of the wording run** stand in #2629 (an ellipsis without a space, min / h, read only, owner, the token,
  e-mail, timeline, British English); the single decisions in #2634 - #2658. A hint line goes behind (i): `infoize()` in
  static/js/icons.js (except `keep`; the office's `ofchint` stays visible).

## News and the bell

- **News across all workspaces** (26.10.2026): the bell and the list always show every workspace, a foreign one with its
  workspace label; no workspace filter.
- **The bell means "please look at this"** (12.11.2026, #5800 - #5808): its number always says how many things wait for
  the person - the same on every device, never dependent on the filter of the window, no dot for the rest. "For you"
  counts what needs attention (mentions, deadlines bundled, approval cards, agents' questions, invitations, "urgent",
  people's comments on my tasks); everything else is calm, folded history without the unread look. A brief for a new kind
  of event says which it is (waits for the person: counts, the server marks it `to_me`; else history: never counts).
  What agents do without anybody having to act writes no entry (#5792).

## Agents and help

- **One source of help** (12.11.2026, #5819, #5820): an agent knows every function of Kalmido and explains it with the
  click path, never guessing a menu; the help for people and for agents come from the same source, no second reference
  kept by hand. A new function brings its click path into that source and a way from the object itself (menu, right click,
  #5821).
- **Agents see only what is shared**, also personal agents (12.11.2026), and the interface shows it and makes it easy:
  "Sees now" and "Share..." in the agent's dialog (#5822), a whole knowledge area shared with one click with single folders
  left out (#5823). An agent's settings are where the agent is seen: the gear on its card (#5825), the model in the chat
  menu, also for server agents (#5824).

## Areas

- **A new area of home and life brings its statistics block** (04.11.2026, #4617): every module of `LIFE_MODS` has its own
  block in the statistics or stands with its reason in the exception list of the test of #4617; the brief names its
  figures.
- **Office documents: addresses only in fixed fields** (18.10.2026, #1951, #2188): a recipient (and a client's master
  data) only in the fixed fields of EN 16931 (name, name addition as its own PDF line, contact person, street, address
  addition, postcode, town, country, VAT id, e-mail, routing id), never a multi-line free text: a document must go one to
  one into XRechnung / ZUGFeRD.

## Checked in the code (`tools/check_rules.py`)

The places of today stand per rule in `tools/rules_baseline.json`; the total of a rule only falls.

| Rule | What it counts | Instead |
|---|---|---|
| `window-open` | `window.open(` in the client code outside static/js/miniwin.js | a tab or window only behind `mw_desk()` (miniwin.js), pictures through `attLightbox` |
| `wording` | "chip" in the English texts, "Meine Ablage" / "Mein Bereich" / "persönliches Büro" in the German ones (static/i18n) | "label", "show in the task row"; "Privat" |
| `emoji` | emoji in the texts of static/i18n other than 👍 and 👎 | an app icon (`ic(...)`) |
