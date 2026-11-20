#!/usr/bin/env python3
"""2.362.4 (#3107): no table with people's data goes missing from an export silently. Static (bare Python 3.12, no app import, the CI
lint step): reads kalmido/core/schema.py (CREATE TABLE + the column migrations) and holds every table (2.531.0 #4317: not only
those with a person, organisation, list or task column; a table with nobody's data stands in exportleft.py UMZ_FREE_TABLES) against
 - the account export (accounts/settings.py umz_export_queries, admin/acctexport.py umz_extra_queries / umz_mine_queries / umz_build)
   or admin/exportleft.py UMZ_LEFT_TABLES, with the reason why it stays out
 - the organisation export (admin/orgexport.py OX_AREAS) or OX_LEFT (tables with an organisation or a list column); 2.510.0 (#4286):
   a column named like a secret in such a table is dropped (OX_SECRET_COLS) or named here with its reason (SECRET_OK)
 - the retention export (admin/retexport.py RX_TABLES) or exportleft.py RX_LEFT_TABLES (the office tables)
 - the imports: every part of the account export is read (acctimport.py UMZ_READ) or named as staying behind (UMZ_LEFT), every
   area of the organisation export is mapped (UMZ_ORG_MAP), read by an area of admin/oi_*.py or named (UMZ_ORG_SKIP)
Nothing in a list may be stale either: a reason for a table that is gone or exported meanwhile fails too.
2.1093.0 (#5289, stage Q11): the tables of the core say where their rows go in the export register (kalmido/core/objexport.py:
obj_export(table, ...) for the cross-cutting tables, obj_register(kind, table, ..., export={...}) for a kind's own table); this
reads those calls as they are written and counts them like the hand lists. Every table of the core (obj_*) needs an entry there,
a registered table must not stand in a hand list too (OX_AREAS, OX_LEFT, UMZ_LEFT_TABLES, UMZ_LATER_NAMES, RX_TABLES, RX_WHERE,
RX_LEFT_TABLES; its parts not in UMZ_READ_OWN / UMZ_ORG_MAP_OWN) and no table is registered twice.
2.1097.0 (#5949): + the register's account queries (acct: umz_export_queries, acct_more: umz_extra_queries) count as parts of the
account export (a part never by hand too), their names as UMZ_LEFT (never in UMZ_LEFT_OWN too); a node clause (nodes, the export of
single documents) belongs to an archive of the table's org entries.
2.1334.0 (#6585, audit #4808 T13): a table of the core holds many kinds in one table (obj_links, obj_comments, obj_tags ...), so
"the table is in some export query" let whole kinds go missing silently (the notes of private documents, private links, the
free links of an organisation). For every table of the core with a kind column (CORE_KINDS: the column and the constant of the
core that lists its kinds) each kind needs, in the organisation export and in the account export, a query that takes it (a
where clause of the register or a hand query on the table that names the kind, or none of its kinds at all) or a reason in
KIND_LEFT here; a stale reason (a kind that is gone or exported meanwhile) fails too. A table of the core with a kind column
outside CORE_KINDS goes as a whole (KIND_WHOLE: why its kinds need no look of their own).
usage: python3 tools/check_export_tables.py [-v] [--root DIR]      exit 1 on a finding"""
import ast
import glob
import os
import re
import sys

from check_migrations import schema_src

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TYPES = "BIGINT|TEXT|INTEGER|DOUBLE|NUMERIC|BOOLEAN|JSONB|BYTEA|REAL|SMALLINT|DATE|TIMESTAMP"
PEOPLE = ("user_id", "owner_id", "created_by", "org_id", "list_id", "task_id")
ORG_COLS = ("org_id", "list_id")
# the tables that carry the others (the account's own row, the export's frame): never a finding
FRAME = ("users",)
# 2.510.0 (#4286, audit #2427): a column of an OX_AREAS table named like a secret stays out of the export (OX_SECRET_COLS: _clean
# drops it) or stands here with the reason why it may go along
SECRET_NAME = re.compile(r"secret|token|hash|passw|key|otp|salt|cred|seal|p256dh|endpoint|(^|_)auth(_|$)", re.I)
SECRET_OK = {
    "bookmarks.url_key": "the normalized address, for finding doubles",
    "list_notepads.agent_key": "the name of an agent's block ('status')",
    "lists.ticket_key": "the prefix of the ticket numbers",
    "nl_consent_log.email_hash": "plain hash of an address the organisation holds itself: the proof of the consent moves with the list",
    "nl_suppress.email_hash": "plain hash of an address the organisation holds itself: who unsubscribed stays unsubscribed after a move",
    "office_bank_rule_nos.key": "the name of a rule's entry",
    "task_offer_links.item_key": "2.654.0 (#4585): the quotation position a task came from (i:<position> | s:<part>:<crew row>), not a secret",
    "office_ledger_entries.credit": "the credit account number of a booking (2.666.0, #3461), no credential",
    "office_bank_tx.rkeys": "the matching keys of a bank line",
    "office_bank_tx.key_org": "the organisation the matching key belongs to",
    "office_bank_tx.hash": "fingerprint of a bank line, against importing it twice",
    "office_docs.chain_hash": "2.531.0 (#4497): the SHA-256 link of the hash chain over finalised documents (office/chain.py), not a secret",
    "office_docs.chain_key": "2.531.0 (#4497): the number series a document is chained in",
    "office_num_ranges.credit_suffix": "2.1365.0 (#6698): the ending of a number range's correction numbers (-K), not a credential",
    "office_bookarch_files.content_key": "fingerprint of a file's content, against importing it twice",
    "office_gen_docs.body_hash": "fingerprint of the document's text",
    "office_signoffs.doc_hash": "fingerprint of the document that was signed off (the proof)",
    "office_texts.key": "the name of a text block",
    "portal_tickets.email_hash": "taken out by _ox_dec_row (the token columns by OX_SECRET_COLS)",
    "sched_poll_votes.edit_hash": "kept empty by _ox_dec_row (a voter's edit key never leaves)",
    "sched_poll_votes.ip_hash": "kept empty by _ox_dec_row",
    "ticket_types.key": "the short word of an own ticket type (!key in quick add), no secret (2.609.0, #3372)",
    "org_fields.key": "the name of a schema field the API reads it by (fkey_<key>), no secret (2.959.0, #4031)",
    "template_files.node_key": "the node of the template's tree a file copy hangs on, no secret (2.1334.0, #6585)",
}
# the parts umz_build writes itself: {part of the file: table}
BUILD_PARTS = {"people": None, "server_links": "msv_links", "budgets": None}

# 2.1334.0 (#6585): the kinds of the core's tables -- table: (kind column, file, the constants that list its kinds). The constant
# is the one the core's helper refuses an unknown kind with (ocm_kind, ofl, osn_mark, otg_link, obj_version_add ...); obj_links: the
# areas' relations, every other relation is a free one (people's and agents' links, KIND_FREE)
CORE_KINDS = {
    "obj_comments": ("kind", "kalmido/core/objcomments.py", ("OCM_KINDS",)),
    "obj_reactions": ("target_kind", "kalmido/core/objreact.py", ("ORX_KINDS",)),
    "obj_follow": ("kind", "kalmido/core/objfollow.py", ("OFL_KINDS",)),
    "obj_seen": ("kind", "kalmido/core/objseen.py", ("OSN_KINDS",)),
    "obj_notif_cap": ("kind", "kalmido/core/objnotifcap.py", ("NCAP_KINDS",)),
    "obj_tags": ("scope_kind", "kalmido/core/objtags.py", ("OTG_SCOPES",)),
    "obj_tag_links": ("kind", "kalmido/core/objtags.py", ("OTG_KINDS",)),
    "obj_versions": ("kind", "kalmido/core/objversions.py", ("OBJV_KINDS",)),
    "obj_links": ("rel", "kalmido/core/objhooks.py", ("OLNK_AREA_RELS",)),
}
KIND_FREE = "(free)"  # the kind of every value of a column outside its constant (obj_links: the links people and agents make)
KIND_HAS_FREE = ("obj_links",)
# the tables of the core with a kind column whose rows go as a whole (one where clause or one reason for all their kinds)
KIND_WHOLE = {
    "obj_history": "the change history of every kind: it follows the objects the organisation export carries, a person's own changes in their private space",
    "obj_undo": "the undo steps of 30 days of every kind: working data, never exported",
    "obj_revoked": "the shares removed of every kind: shares are made anew on the target",
    "obj_addr_shares": "who shares an address book: shares are made anew on the target",
    "obj_comment_trash": "the trash texts of comments of every kind: working data until the trash period ends",
    "obj_search": "the search index of every kind: rebuilt from the imported rows",
    "obj_search_words": "the word index of every kind: rebuilt from the imported rows",
}
KIND_COLS = ("kind", "scope_kind", "target_kind", "src_kind", "dst_kind", "rel")
# (table, kind, export) -> the reason why the kind stays out of that export (org = the organisation export, acct = the account
# export); export clauses resolve the placeholders of KIND_FMT (the rest name no kind)
_K_VIEW = "what a person has seen or muted: a personal view state, never exported"
_K_PERSON = "a person's own setting: their account export"
_K_NOROWS = "no rows of its own: the team chat's messages stay in tchat_msgs (only the comment helpers, 2.981.0 #5274)"
KIND_LEFT = {
    ("obj_comments", "tchat", "org"): _K_NOROWS, ("obj_comments", "tchat", "acct"): _K_NOROWS,
    ("obj_follow", "list", "org"): _K_PERSON,
    ("obj_follow", "tchat", "org"): _K_VIEW, ("obj_follow", "tchat", "acct"): _K_VIEW,
    ("obj_follow", "tchat_thread", "org"): _K_VIEW, ("obj_follow", "tchat_thread", "acct"): _K_VIEW,
    ("obj_links", "device", "org"): "a person's own device link: their account export (device_links)",
    ("obj_links", "answers", "acct"): "the letters of an office: their organisation's export, a personal office's in personal-office/",
    ("obj_links", "reply", "acct"): "the letters of an office: their organisation's export, a personal office's in personal-office/",
    ("obj_notif_cap", "list", "org"): _K_PERSON, ("obj_notif_cap", "folder", "org"): _K_PERSON,
    ("obj_reactions", "agent_chat", "org"): "an agent chat is one person's: their account export (reactions)",
    ("obj_tags", "user", "org"): "a person's own tags: their account export (task_tags)",
    ("obj_tags", "org", "acct"): "the labels of an organisation: its export",
    ("obj_versions", "procdoc", "acct"): "the procedure documentation of an office: its organisation's export, a personal office's in personal-office/",
    ("obj_versions", "wiki", "acct"): "not yet in the account export (history of knowledge pages)",
    **{("obj_seen", k, ex): _K_VIEW for k in ("task", "rss", "tchat", "tchat_thread", "due") for ex in ("org", "acct")},
}
KIND_FMT = {"LETTER_LINKS": ("kalmido/admin/orgexport.py", "OX_LETTER_LINKS"),  # a string constant as it is
            "AREA_RELS": ("kalmido/core/objhooks.py", "OLNK_AREA_RELS")}  # a tuple constant as ('a', 'b')


def read(root, *p):
    with open(os.path.join(root, *p), encoding="utf-8") as f:
        return f.read()


def schema_tables(root):
    src = schema_src(root)  # 2.475.0 (#3478): + migrations.d
    tables = {}
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\);", src, re.S):
        body = re.sub(r"--[^\n]*", "", m.group(2))  # a comment at a line's end must not hide the column on the next line
        tables.setdefault(m.group(1), set()).update(re.findall(rf"(?:^|,|\()\s*\"?(\w+)\"?\s+(?:{TYPES})", body))
    for m in re.finditer(r'\("(\w+)", "(\w+)", "ALTER TABLE', src):
        tables.setdefault(m.group(1), set()).add(m.group(2))
    return tables


def text_of(node):
    """The text of a (joined) string node; the {...} parts of an f-string count as nothing."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(text_of(v) for v in node.values)
    return ""


def top_from(sql):
    """The tables after each FROM outside parentheses (a subselect in the column list or the WHERE is no source of the rows)."""
    depth, out = 0, []
    for m in re.finditer(r"[()]|\bFROM\s+(\w+)", sql, re.I):
        if m.group(0) == "(":
            depth += 1
        elif m.group(0) == ")":
            depth -= 1
        elif not depth:
            out.append(m.group(1))
    return out


def queries_in(tree, fn):
    """{part: main tables} of the dict(s) of queries in function fn: the FROM of the query and of each UNION ALL."""
    out = {}
    f = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == fn)
    for d in ast.walk(f):
        if not isinstance(d, ast.Dict):
            continue
        for k, v in zip(d.keys, d.values):
            if isinstance(k, ast.Constant) and isinstance(v, ast.Tuple) and v.elts:
                out[k.value] = top_from(text_of(v.elts[0]))
    return out


def assigned(tree, name):
    return next(n.value for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id == name)


def strings(node):
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def reasons(tree, name):
    """{table: reason} of a dict of reasons in a module of plain assignments (names of other reasons resolved)."""
    names = {n.targets[0].id: n.value.value for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
             and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)}
    d = assigned(tree, name)
    out = {}
    for k, v in zip(d.keys, d.values):
        out[k.value] = v.value if isinstance(v, ast.Constant) else names.get(getattr(v, "id", ""))
    return out


def _value(node, names):
    """A literal of a register call: strings, tuples, None; a name of a plain string assignment of the file resolved."""
    if isinstance(node, ast.Name):
        return names.get(node.id)
    return ast.literal_eval(node)


def register(root):
    """2.1093.0 (#5289): the export register as written -> ({table: {keyword: value, "at": "file:line"}}, [findings])."""
    reg, bad = {}, []
    for path in sorted(glob.glob(os.path.join(root, "kalmido", "**", "*.py"), recursive=True)):
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        if "obj_export(" not in src and "export=" not in src:
            continue
        tree = ast.parse(src)
        names = {n.targets[0].id: n.value.value for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                 and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)}
        rel = os.path.relpath(path, root)
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call) or not isinstance(n.func, ast.Name):
                continue
            if n.func.id == "obj_export" and n.args and all(k.arg for k in n.keywords):  # not obj_register's own call (**export)
                tnode, kws = n.args[0], {k.arg: k.value for k in n.keywords if k.arg != "by"}
            elif n.func.id == "obj_register" and any(k.arg == "export" for k in n.keywords) and len(n.args) > 1:
                tnode, ex = n.args[1], next(k.value for k in n.keywords if k.arg == "export")
                if not isinstance(ex, ast.Dict) or not all(isinstance(k, ast.Constant) for k in ex.keys):
                    bad.append(f"{rel}:{n.lineno}: obj_register export= must be a plain dict literal")
                    continue
                kws = {k.value: v for k, v in zip(ex.keys, ex.values)}
            else:
                continue
            at = f"{rel}:{n.lineno}"
            try:
                t = _value(tnode, names)
                e = {k: _value(v, names) for k, v in kws.items()}
            except ValueError:
                bad.append(f"{at}: an entry of the export register must be plain literals (this check reads it without the app)")
                continue
            if not isinstance(t, str):
                bad.append(f"{at}: the table of an export register entry must be a plain string")
                continue
            if t in reg:
                bad.append(f"{t}: registered twice in the export register ({reg[t]['at']}, {at}): one way per table")
                continue
            e["at"] = at
            if e.get("acct_later"):
                e["acct_left"] = "not yet in the account export"
            reg[t] = e
    return reg, bad


def const_tuple(root, rel, name):
    """The strings of a module-level tuple constant as written (NAME = (...) and every NAME += (...)), read without the app."""
    tree, out, found = ast.parse(read(root, *rel.split("/"))), [], False
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == name for t in n.targets) \
                or isinstance(n, ast.AugAssign) and getattr(n.target, "id", "") == name:
            found = True
            out += [v for v in strings(n.value)]
    return out if found else None


def const_str(root, rel, name):
    return next((n.value.value for n in ast.parse(read(root, *rel.split("/"))).body if isinstance(n, ast.Assign)
                 and getattr(n.targets[0], "id", "") == name and isinstance(n.value, ast.Constant)), None)


_KIND_RE = r"(?<![\w.])(?:\w+\.)?{col}\s*(=|<>|!=|NOT\s+IN|IN)\s*(?:'(\w+)'|\(([^()]*)\))"


def kinds_of(sql, col, kinds):
    """The kinds of col (+ KIND_FREE) a query or where clause takes: all without a condition on col, else what = / IN name
    (a value outside kinds: the free ones) or what <> / NOT IN leave."""
    got = set()
    found = False
    for m in re.finditer(_KIND_RE.format(col=col), sql, re.I):
        found = True
        vals = {m.group(2)} if m.group(2) else set(re.findall(r"'(\w+)'", m.group(3) or ""))
        if m.group(1).upper() in ("=", "IN"):
            got |= vals & set(kinds)
            got |= {KIND_FREE} if vals - set(kinds) else set()
        else:
            got |= (set(kinds) - vals) | {KIND_FREE}
    return got if found else set(kinds) | {KIND_FREE}


def query_texts(tree, fn):
    """{part: the query's text} of the dict(s) of queries in function fn (queries_in with the whole text)."""
    out = {}
    f = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == fn)
    for d in ast.walk(f):
        if isinstance(d, ast.Dict):
            for k, v in zip(d.keys, d.values):
                if isinstance(k, ast.Constant) and isinstance(v, ast.Tuple) and v.elts:
                    out[k.value] = text_of(v.elts[0])
    return out


def check_kinds(root, tables, reg, hand):
    """2.1334.0 (#6585): every kind of every table of the core in both exports (module docstring) -> ([findings], {table: kinds})."""
    bad, seen = [], {}
    fmt = {}
    for k, v in KIND_FMT.items():
        t = const_tuple(root, *v)
        fmt[k] = "(" + ", ".join(f"'{x}'" for x in t) + ")" if t is not None and const_str(root, *v) is None else const_str(root, *v) or ""
    acct_all = [*hand, *(e[1] for r in reg.values() for e in (*(r.get("acct") or ()), *(r.get("acct_more") or ())))]

    def fill(sql):
        return re.sub(r"\{(\w+)\}", lambda m: fmt.get(m.group(1), ""), sql)
    for t in sorted(t for t in tables if t.startswith("obj_")):
        if not any(c in tables[t] for c in KIND_COLS):
            continue
        if t in CORE_KINDS and t in KIND_WHOLE:
            bad.append(f"{t}: in CORE_KINDS and in KIND_WHOLE (tools/check_export_tables.py)")
        if t not in CORE_KINDS and t not in KIND_WHOLE:
            bad.append(f"{t}: a table of the core with a kind column ({'/'.join(c for c in KIND_COLS if c in tables[t])}) neither in "
                       "CORE_KINDS (its kinds, each held against the exports) nor in KIND_WHOLE (tools/check_export_tables.py)")
    for t in sorted(set(KIND_WHOLE) - set(tables)):
        bad.append(f"{t}: stale in KIND_WHOLE (no such table)")
    for t, (col, rel, names) in sorted(CORE_KINDS.items()):
        if t not in tables or col not in tables[t]:
            bad.append(f"{t}: stale in CORE_KINDS (no such table or no column {col})")
            continue
        kinds = []
        for name in names:
            v = const_tuple(root, rel, name)
            if v is None:
                bad.append(f"{t}: CORE_KINDS names {rel} {name}, which is no tuple there")
                v = []
            kinds += [k for k in v if k not in kinds]
        if t in KIND_HAS_FREE:
            kinds.append(KIND_FREE)
        seen[t] = kinds
        r = reg.get(t) or {}
        # org: the where clauses of the table's own entries; acct: its own queries and every other one that reads it (FROM / JOIN)
        # nodes: the documents of a personal office and of a person's private store (admin/orgexport.py ox_doc_parts), both exports
        nodes = [fill(e[1]) for e in r.get("nodes") or ()]
        ways = {"org": [fill(e[1]) for e in r.get("org") or ()] + nodes,
                "acct": [fill(e[1]) for e in (*(r.get("acct") or ()), *(r.get("acct_more") or ()))] + nodes
                + [fill(q) for q in acct_all if re.search(rf"\b(?:FROM|JOIN)\s+{t}\b", q, re.I)]}
        for ex, qs in ways.items():
            got = set()
            for q in qs:
                got |= kinds_of(q, col, kinds)
            for k in kinds:
                why = KIND_LEFT.get((t, k, ex))
                if k in got and why:
                    bad.append(f"{t} {col}={k}: in the {ex} export and named in KIND_LEFT (tools/check_export_tables.py): drop the reason")
                elif k not in got and not why:
                    bad.append(f"{t} {col}={k}: in no query of the {ex} export ({'kalmido/core/objexport.py org=' if ex == 'org' else 'objexport.py acct= / acct_more= or a hand query'}) "
                               "and without a reason in KIND_LEFT (tools/check_export_tables.py)")
    for (t, k, ex), why in sorted(KIND_LEFT.items()):
        if t not in seen or k not in seen[t] or ex not in ("org", "acct"):
            bad.append(f"{t} {k} {ex}: stale in KIND_LEFT (no such table, kind or export)")
        elif not (isinstance(why, str) and why.strip()):
            bad.append(f"{t} {k} {ex}: KIND_LEFT needs a reason")
    return bad, seen


def acct_tables(root):
    """(#6593): the tables of the account export -- the FROM of its queries (umz_export_queries, umz_extra_queries,
    umz_mine_queries, the register's acct / acct_more) and the built parts; tools/check_umz_v.py reads them (check() counts the
    same way)."""
    reg, _bad = register(root)
    parts = dict(queries_in(ast.parse(read(root, "kalmido", "accounts", "settings.py")), "umz_export_queries"))
    acct = ast.parse(read(root, "kalmido", "admin", "acctexport.py"))
    for fn in ("umz_extra_queries", "umz_mine_queries"):
        parts.update(queries_in(acct, fn))
    for r in reg.values():
        for e in (*(r.get("acct") or ()), *(r.get("acct_more") or ())):
            parts[e[0]] = top_from(e[1])
    built = set(ast.literal_eval(assigned(ast.parse(read(root, "kalmido", "admin", "exportleft.py")), "UMZ_BUILD_TABLES")))
    return {t for v in parts.values() for t in v} | {t for t in BUILD_PARTS.values() if t} | built


def check(root):
    tables = schema_tables(root)
    reg, bad = register(root)  # 2.1093.0 (#5289)
    stats = {"tables": len(tables), "register": len(reg)}
    for t in sorted(t for t in tables if t.startswith("obj_") and t not in reg):
        bad.append(f"{t}: a table of the core without an entry in the export register (kalmido/core/objexport.py obj_export, or "
                   "obj_register export= for a kind's own table)")
    for t in sorted(set(reg) - set(tables)):
        bad.append(f"{t}: stale in the export register ({reg[t]['at']}: no such table)")
    r_org = {e[0]: t for t, r in reg.items() for e in r.get("org") or ()}
    r_part = {e[0]: e[2] for r in reg.values() for e in r.get("org") or () if len(e) == 3}
    r_read = {p for r in reg.values() for p in r.get("read") or ()} | set(r_part.values())
    r_rx = {t for t, r in reg.items() if r.get("rx")}
    r_left = {k: {t: r[k] for t, r in reg.items() if r.get(k)} for k in ("org_left", "acct_left", "acct_later")}
    r_acct = {}  # 2.1097.0 (#5949): {part: (table, query, left name or None)}
    for t, r in reg.items():
        for e in (*(r.get("acct") or ()), *(r.get("acct_more") or ())):
            if e[0] in r_acct:
                bad.append(f"{e[0]}: a part of the account export registered twice ({r_acct[e[0]][0]}, {t})")
            r_acct[e[0]] = (t, e[1], e[2] if len(e) > 2 else None)
        for e in r.get("nodes") or ():
            if e[0] not in {o[0] for o in r.get("org") or ()}:
                bad.append(f"{t}: the node clause of {e[0]} names no archive of its org entries ({r['at']})")
    admin = ("kalmido", "admin")
    # ---- account export
    parts = {}
    parts.update(queries_in(ast.parse(read(root, "kalmido", "accounts", "settings.py")), "umz_export_queries"))
    acct = ast.parse(read(root, *admin, "acctexport.py"))
    for fn in ("umz_extra_queries", "umz_mine_queries"):
        parts.update(queries_in(acct, fn))
    for p in sorted(set(parts) & set(r_acct)):  # 2.1097.0 (#5949)
        bad.append(f"{p}: a part of the account export in the export register ({r_acct[p][0]}) and by hand in a query function")
    parts.update({p: top_from(q) for p, (_t, q, _w) in r_acct.items()})
    hand = [q for tr_, fn in ((ast.parse(read(root, "kalmido", "accounts", "settings.py")), "umz_export_queries"),
                              (acct, "umz_extra_queries"), (acct, "umz_mine_queries")) for q in query_texts(tr_, fn).values()]
    kb, kseen = check_kinds(root, tables, reg, hand)  # 2.1334.0 (#6585)
    bad += kb
    stats["kinds"] = sum(len(v) for v in kseen.values())
    left_tree = ast.parse(read(root, *admin, "exportleft.py"))
    left, rx_left = reasons(left_tree, "UMZ_LEFT_TABLES"), reasons(left_tree, "RX_LEFT_TABLES")
    later_own = reasons(left_tree, "UMZ_LATER_NAMES")
    for name, d in (("UMZ_LEFT_TABLES", left), ("UMZ_LATER_NAMES", later_own), ("RX_LEFT_TABLES", rx_left)):
        for t in sorted(set(d) & set(reg)):
            bad.append(f"{t}: in the export register ({reg[t]['at']}) and by hand in {name} (kalmido/admin/exportleft.py)")
    left = {**left, **r_left["acct_left"]}
    inc = {t for v in parts.values() for t in v} | {t for t in BUILD_PARTS.values() if t} | set(ast.literal_eval(assigned(left_tree, "UMZ_BUILD_TABLES")))
    need = {t for t, c in tables.items() if any(x in c for x in PEOPLE) and t not in FRAME}
    stats["account"] = len(need)
    # 2.531.0 (#4317 F12, audit #2425): every table, not only those with a person column (kid_parents, conn_links went missing):
    # exported, named in UMZ_LEFT_TABLES (the manifest's not_included) or, holding nobody's data, in UMZ_FREE_TABLES
    free, later = reasons(left_tree, "UMZ_FREE_TABLES"), {**later_own, **r_left["acct_later"]}
    for t in sorted(set(tables) - set(FRAME) - inc - set(left) - set(free)):
        has = "/".join(x for x in PEOPLE if x in tables[t])
        bad.append(f"{t}: {'has ' + has if has else 'a table'} but is neither in the account export nor in UMZ_LEFT_TABLES "
                   f"(kalmido/admin/exportleft.py){'' if has else ' nor in UMZ_FREE_TABLES'}: export it or name why it stays out")
    for t in sorted(set(left) - set(tables)):
        bad.append(f"{t}: stale in UMZ_LEFT_TABLES (no such table)")
    for t in sorted(set(left) & inc):
        bad.append(f"{t}: in the account export and in UMZ_LEFT_TABLES")
    for t in sorted(set(free) - set(tables)):
        bad.append(f"{t}: stale in UMZ_FREE_TABLES (no such table)")
    for t in sorted(set(free) & (need | inc | set(left))):
        bad.append(f"{t}: in UMZ_FREE_TABLES but it holds a person's data (a person / organisation / list / task column), is exported "
                   "or in UMZ_LEFT_TABLES")
    lt = {t for t in left if left[t] == next((n.value.value for n in left_tree.body if isinstance(n, ast.Assign)
                                               and getattr(n.targets[0], "id", "") == "_LATER"), None)}  # the tables not yet in it
    lt |= set(r_left["acct_later"])  # 2.1093.0 (#5289): the register names it with acct_later
    for t in sorted(lt - set(later)):
        bad.append(f"{t}: not yet in the account export but without a readable name in UMZ_LATER_NAMES (the export page names it)")
    for t in sorted(set(later) - lt):
        bad.append(f"{t}: stale in UMZ_LATER_NAMES (not a table that is not yet in the account export)")
    # ---- organisation export
    ox = ast.parse(read(root, *admin, "orgexport.py"))
    areas = {e.elts[0].value: e.elts[1].value for e in assigned(ox, "OX_AREAS").elts}
    ox_left = reasons(ox, "OX_LEFT")
    for t in sorted((set(areas.values()) | set(ox_left)) & set(reg)):
        bad.append(f"{t}: in the export register ({reg[t]['at']}) and by hand in OX_AREAS / OX_LEFT (kalmido/admin/orgexport.py)")
    for a in sorted(set(areas) & set(r_org)):
        bad.append(f"{a}: a file of the organisation export in OX_AREAS and in the export register")
    areas = {**areas, **r_org}
    ox_left = {**ox_left, **r_left["org_left"]}
    onames = {t for t, c in tables.items() if any(x in c for x in ORG_COLS) and t not in ("orgs", "lists")}
    stats["organisation"] = len(onames)
    for t in sorted(onames - set(areas.values()) - set(ox_left)):
        bad.append(f"{t}: has an organisation / list column but is neither in OX_AREAS nor in OX_LEFT (kalmido/admin/orgexport.py)")
    # 2.1334.0 (#6359, audit #4773 F11): every table, as the account export's guard (not only those with an organisation / list
    # column: a person's table reached over another one, hub_mailbox_rules, went missing): exported, named in OX_LEFT with the
    # reason, or holding nobody's data (UMZ_FREE_TABLES)
    every = set(tables) - set(FRAME) - {"orgs", "lists"} - set(free)
    stats["organisation_all"] = len(every)
    for t in sorted(every - onames - set(areas.values()) - set(ox_left)):
        bad.append(f"{t}: a table neither in the organisation export (OX_AREAS) nor in OX_LEFT (kalmido/admin/orgexport.py): "
                   "export it or name why it stays out")
    for t in sorted(set(ox_left) - set(tables)):
        bad.append(f"{t}: stale in OX_LEFT (no such table)")
    for t in sorted(set(ox_left) & set(areas.values())):
        bad.append(f"{t}: in the organisation export and in OX_LEFT")
    for t in sorted(set(ox_left) & set(free)):
        bad.append(f"{t}: in OX_LEFT and in UMZ_FREE_TABLES (a table with nobody's data is in neither export)")
    secret_cols = strings(assigned(ox, "OX_SECRET_COLS"))  # 2.510.0 (#4286): _rows is SELECT *, _clean only drops these names
    named = {f"{t}.{c}" for t in set(areas.values()) for c in tables.get(t, ()) if SECRET_NAME.search(c) and c not in secret_cols}
    for x in sorted(named - set(SECRET_OK)):
        bad.append(f"{x}: named like a secret, goes along with the organisation export: add it to OX_SECRET_COLS (kalmido/admin/orgexport.py) or to SECRET_OK here with the reason")
    for x in sorted(set(SECRET_OK) - named):
        bad.append(f"{x}: stale in SECRET_OK")
    # ---- retention export
    rx = ast.parse(read(root, *admin, "retexport.py"))
    rx_t = {e.elts[1].value for e in assigned(rx, "RX_TABLES").elts}
    rx_w = {k.value for k in assigned(rx, "RX_WHERE").keys}
    for t in sorted((rx_t | rx_w) & set(reg)):
        bad.append(f"{t}: in the export register ({reg[t]['at']}) and by hand in RX_TABLES / RX_WHERE (kalmido/admin/retexport.py)")
    rx_t |= r_rx
    office = {t for t in tables if t.startswith("office_")}
    stats["retention"] = len(office)
    for t in sorted(office - rx_t - set(rx_left)):
        bad.append(f"{t}: an office table neither in RX_TABLES (kalmido/admin/retexport.py) nor in RX_LEFT_TABLES (exportleft.py)")
    for t in sorted(set(rx_left) - office):
        bad.append(f"{t}: stale in RX_LEFT_TABLES")
    for t in sorted(set(rx_left) & rx_t):
        bad.append(f"{t}: in RX_TABLES and in RX_LEFT_TABLES")
    for t in sorted(rx_t - set(tables)):
        bad.append(f"{t}: in RX_TABLES but not in the schema")
    # ---- imports
    imp = ast.parse(read(root, *admin, "acctimport.py"))
    read_own, omap_own = strings(assigned(imp, "UMZ_READ_OWN")), assigned(imp, "UMZ_ORG_MAP_OWN")
    for p in sorted(read_own & r_read):
        bad.append(f"{p}: a part in the export register and by hand in UMZ_READ_OWN (kalmido/admin/acctimport.py)")
    for p in sorted({k.value for k in omap_own.keys} & set(r_part)):
        bad.append(f"{p}: a file in the export register and by hand in UMZ_ORG_MAP_OWN (kalmido/admin/acctimport.py)")
    left_own = strings(assigned(imp, "UMZ_LEFT_OWN"))  # 2.1097.0 (#5949): + the register's named parts
    r_named = {p for p, (_t, _q, w) in r_acct.items() if w}
    for p in sorted(left_own & r_named):
        bad.append(f"{p}: named in the export register ({r_acct[p][0]}) and by hand in UMZ_LEFT_OWN (kalmido/admin/acctimport.py)")
    known = read_own | r_read | left_own | r_named
    for p in sorted((set(parts) | set(BUILD_PARTS)) - known):
        bad.append(f"{p}: a part of the account export that acctimport.py neither reads (UMZ_READ) nor names (UMZ_LEFT)")
    omap, skip = strings(omap_own) | set(r_part), [e.elts[0].value for e in assigned(imp, "UMZ_ORG_SKIP").elts]
    oit = set()
    for f in glob.glob(os.path.join(root, *admin, "oi_*.py")) + [os.path.join(root, *admin, "orgimport.py")]:
        with open(f, encoding="utf-8") as fh:
            oit.update(re.findall(r'OiT\(\s*"([^"]+)"', fh.read()))
    for p in sorted(areas):
        if p not in omap and p not in oit and not any(p.startswith(x) for x in skip):
            bad.append(f"{p}: an area of the organisation export that the import neither maps (UMZ_ORG_MAP, admin/oi_*.py OiT) nor names (UMZ_ORG_SKIP)")
    return bad, stats


def main():
    a = sys.argv[1:]
    root = a[a.index("--root") + 1] if "--root" in a else ROOT
    bad, st = check(root)
    for b in bad:
        print("check_export_tables:", b)
    print(f"check_export_tables: {st['tables']} tables, {st['account']} with people's data, {st['organisation']} with an organisation or list column, "
          f"(every one of {st['organisation_all']} placed), {st['retention']} office tables, {st['register']} in the export register, {st['kinds']} kinds of the core, {len(bad)} finding(s)")
    return 1 if bad else 0


LINT_WHY = "a table with people's data that no export names goes missing from the export silently"
LINT_INSTEAD = "name the table in the export (account / organisation export) or with its reason in kalmido/admin/exportleft.py"


if __name__ == "__main__":
    import lintmsg  # tools/ is the script's folder, so it is on the path
    with lintmsg.red_hint("check_export_tables", LINT_WHY, LINT_INSTEAD):
        sys.exit(main())
