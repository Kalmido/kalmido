#!/usr/bin/env python3
"""Lint of a pull request / merge queue entry (#4006, GitHub step 3 of 6 from the check #1826; decision 29.10.2026).

The release tooling checks these points before a package lands on main (einreihen); a pull request or an entry of the
merge queue gets the same checks here, as a CI step on the commits of the change (BASE..HEAD, merges left out):

  subject     every commit subject names its task as #<id> (the dispatcher reads what is built from it). Accepted without
              one: the release tooling's own commits ("2.588.0: ...", "README for the live train ...", "changelog fragment
              ...", a job number "job/<n>") and reverts.
  changelog   a change of the app code (app.py, kalmido/, static/, mcp/) brings its changelog part: a changelog.d/*.md
              added or changed, or CHANGELOG.md itself (the release commit folds the fragments in).
  privacy     added lines and new file names against the private patterns, the commit identities against the allowed
              addresses. The patterns are private themselves (host names, addresses), so they never stand in this public
              repo: they come from the environment (the CI secrets KALMIDO_PRIVACY_DENY / KALMIDO_PRIVACY_ALLOW /
              KALMIDO_PRIVACY_IDENT / KALMIDO_ALLOWED_EMAILS; each a regular expression, the e-mails a comma list). Without
              KALMIDO_PRIVACY_DENY (a pull request from a fork gets no secrets) the scan of the lines is skipped with a
              notice. Commit identities: the noreply addresses (project, GitHub) and the ones in KALMIDO_ALLOWED_EMAILS.
  i18n        2.1188.0 (#6194): a change of static/i18n/<code>.json adds no key (changing or deleting a text is fine): the new
              texts of a package go into static/i18n/neu/<KID>.json (kalmido/core/i18nfrag.py), so two entries of the merge
              queue never conflict at the end of the big language files (GitHub merges without the merge drivers). A key that
              stood in a fragment at the base may move into the big file (folding the fragments in).
              2.1216.0 (#6231): a build job does not move its texts itself, the release tooling's merge queue does it for
              every replayed commit (a job's own move commit met the queue's fragment as an add/add conflict).
  marks       an added line of the server or client code (app.py, kalmido/, static/js, static/*.js) carries no version mark
              "2.<n>[.<n>] (#<n>)" (#7143, rule 12c of audit #5501): the history is in git, a comment says what holds and
              why; a pointer to a decided task stays as "(#<id>)" without the version.
  suppress    the ratchets of #7143 per change: per marker kind of tools/check_suppress.py the change adds no more markers
              than it removes, a marker it adds carries its reason in the same comment (net per kind), and it adds no
              more os.environ reads outside kalmido/core/env.py than it removes (tools/check_rules.py, rule env).
              marks and suppress count only the lines the change adds and removes, so the stock of today and what packages
              merged meanwhile brought never make an entry red (the totals of check_suppress / check_rules in the lint job
              are notices for that reason). Both read the two checks from the BASE commit, like this file itself; a base
              without them is a notice.
  griff       #7294: a CSS rule the change adds (static/app.css, static/css/*.css) that gives a panel, a column or a floating
              window a fixed size without the one grip (grip.js; it reads var(--g-<key>, ...)) is red - a fixed column of at
              least 12rem beside an fr column, flex: 0 0 <fixed>, a floating box with a written width / height of 12rem or more;
              the way out is /* griff-ok: REASON */ at the rule. Only added declarations count (a rule moved unchanged is not
              new); the stock goes through the audit tasks. The rules are tools/griff_lint.py of the BASE (like marks).
  oneway      the one-way rules (destructive SQL, a schema version bump, a migration step that deletes, a sign-in route
              added / removed, the registration modes changed): a note (GitHub warning annotation), never red - a one-way
              step is a note while the switch "einbahn_braucht_ja" of the release tooling is off; --strict makes it red.

  python3 tools/pr_lint.py --base BASE [--head HEAD] [--only subject,changelog,privacy,i18n,marks,suppress,griff,oneway] [--strict] [--repo DIR]
Exit 0 clean (notes allowed), 1 a check failed (listed), 2 usage / git error. Python standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = [ROOT]  # --repo (the self test runs on a temporary repository)
CHECKS = ("subject", "changelog", "privacy", "i18n", "marks", "suppress", "griff", "oneway")

# subjects the release tooling writes itself (kalmido-livezug.py): the version commit, the README / changelog fold, a job's
# changelog fragment, a job number; a revert keeps the subject of the reverted commit in quotes
SUBJECT_OK = re.compile(r"#\d+|\bjob/\d+\b|^\d+\.\d+\.\d+:|^README for the live train\b|^changelog fragment\b|^Revert \"")
APP_CODE = re.compile(r"^(app\.py$|kalmido/|static/|mcp/)")
CHANGELOG = re.compile(r"^(changelog\.d/[^/]+\.md|CHANGELOG\.md)$")
NOREPLY = re.compile(r"^(noreply@kalmido\.com|\d+\+[a-z0-9-]+@users\.noreply\.github\.com|noreply@github\.com)$", re.I)
COMMENT = re.compile(r"^\s*(#|--)")
I18N_BASE = re.compile(r"^static/i18n/([a-z]{2,3}(?:-[A-Za-z0-9]{2,8})?)\.json$")  # the big language files
I18N_FRAG = re.compile(r"^static/i18n/neu/[\w.-]+\.json$")  # the fragments of the packages (#6194)

# The one-way rules (the same as the release tooling's defaults): side "+" added lines, "weg" removed lines that were not
# added back unchanged, "geaendert" = "weg" + added lines that were not there before, "+-" both sides.
ONEWAY = [
    {"name": "table / column dropped or renamed, type changed", "files": r"^kalmido/.*\.py$",
     "except": r"^kalmido/admin/(backup|migrate)\.py$", "side": "+",
     "rx": r"\bDROP\s+(TABLE|COLUMN)\b|\bRENAME\s+(COLUMN|TO)\b|\bALTER\s+COLUMN\s+\S+\s+(SET\s+DATA\s+)?TYPE\b|\bTRUNCATE\s+(TABLE\s+)?[a-z_]",
     "except_line": r"\b\w+_fts\b"},  # search indexes are rebuilt from the data
    {"name": "schema version raised (older versions cannot read the backups)", "files": r"^kalmido/core/schema\.py$",
     "side": "+", "rx": r"^SCHEMA_VERSION\s*="},
    {"name": "migration step deletes data", "files": r"^kalmido/core/(schema\.py|migrations\.d/[^/]+\.py)$", "side": "+",
     "rx": r"^\s*\(\"[a-z_0-9]+\",\s*\"[a-z_0-9]+\",.*\b(DELETE\s+FROM|DROP|TRUNCATE)\b"},
    {"name": "sign-in / registration route added or removed", "files": r"^kalmido/.*\.py$", "side": "geaendert",
     "rx": r"@app\.(get|post|put|patch|delete|route)\(\s*[\"']/api/auth/"},
    {"name": "registration modes changed", "files": r"^kalmido/accounts/signup\.py$", "side": "+-", "rx": r"^SIGNUP_MODES\s*="},
]


def git(*args: str) -> str:
    p = subprocess.run(["git", "-C", REPO[0], *args], capture_output=True, text=True, errors="replace")
    if p.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout


def commits(base: str, head: str) -> list[tuple[str, str, str, str]]:
    """[(sha, subject, author e-mail, committer e-mail)] of BASE..HEAD without merges, oldest first."""
    out = git("log", "--no-merges", "--reverse", "--format=%H%x1f%s%x1f%ae%x1f%ce", f"{base}..{head}")
    return [tuple(ln.split("\x1f")) for ln in out.splitlines() if ln]  # type: ignore[misc]


def idents(base: str, head: str) -> list[tuple[str, str, str]]:
    """review F8: the identities of EVERY commit of BASE..HEAD, merges included -> [(sha, author, committer)]."""
    out = git("log", "--format=%H%x1f%ae%x1f%ce", f"{base}..{head}")
    return [tuple(ln.split("\x1f")) for ln in out.splitlines() if ln]  # type: ignore[misc]


def names(base: str, head: str) -> list[str]:
    """review F8: every new / changed / renamed / copied path of base...head, raw (-z: umlauts and special characters as
    they are, never quoted), empty and binary files included."""
    out = git("-c", "core.quotePath=false", "diff", "-z", "--name-only", "--diff-filter=ACMRT", "--find-renames", f"{base}...{head}")
    return [p for p in out.split("\0") if p]


HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


def diff_files(base: str, head: str) -> dict[str, dict[str, list[str]]]:
    """{path: {"+": lines, "-": lines}} of base...head (merge base); a deleted file under its old path. review F8: the hunk
    header's counts say how many lines belong to the hunk (-U0, no context), so an added line that reads "++ b/x" never
    starts a new file; paths unquoted (-c core.quotePath=false); every changed path is there, also without lines."""
    out: dict[str, dict[str, list[str]]] = {p: {"+": [], "-": []} for p in names(base, head)}
    cur = old = None
    left = {"-": 0, "+": 0}
    text = git("-c", "core.quotePath=false", "diff", "-U0", "--no-color", "--no-ext-diff", "--find-renames", f"{base}...{head}")
    for ln in text.splitlines():
        if left["-"] or left["+"]:
            side = ln[:1]
            if side in left and left[side] and cur:
                out[cur][side].append(ln[1:])
                left[side] -= 1
                continue
            if ln.startswith("\\"):  # "\ No newline at end of file"
                continue
            left = {"-": 0, "+": 0}
        m = HUNK.match(ln)
        if m:
            left = {"-": int(m.group(1) if m.group(1) is not None else 1), "+": int(m.group(2) if m.group(2) is not None else 1)}
        elif ln.startswith("--- "):
            old = _unq(ln[6:]) if ln.startswith("--- a/") else None
        elif ln.startswith("+++ "):
            cur = _unq(ln[6:]) if ln.startswith("+++ b/") else old
            if cur:
                out.setdefault(cur, {"+": [], "-": []})
    return out


def _unq(p: str) -> str:
    """a path git still quoted (a tab or newline in the name): the C-style quotes off."""
    if len(p) > 1 and p.startswith('"') and p.endswith('"'):
        return p[1:-1].encode("latin-1", "backslashreplace").decode("unicode_escape").encode("latin-1").decode("utf-8", "replace")
    return p


def check_subject(cs) -> list[str]:
    return [f"{sha[:10]} \"{subj}\": no task number #<id> in the subject" for sha, subj, _, _ in cs if not SUBJECT_OK.search(subj)]


def check_changelog(files) -> list[str]:
    app = sorted(p for p in files if APP_CODE.search(p))
    if not app or any(CHANGELOG.search(p) for p in files):
        return []
    more = f" and {len(app) - 3} more" if len(app) > 3 else ""
    return [f"app code changed ({', '.join(app[:3])}{more}) without a changelog part: add changelog.d/<job>.md"]


def _env_rx(name: str):
    v = os.environ.get(name, "").strip()
    return re.compile(v, re.I) if v else None


def check_privacy(ids, files, notes: list[str]) -> list[str]:
    deny, allow = _env_rx("KALMIDO_PRIVACY_DENY"), _env_rx("KALMIDO_PRIVACY_ALLOW")
    ident = _env_rx("KALMIDO_PRIVACY_IDENT")
    mails = {m.strip().lower() for m in os.environ.get("KALMIDO_ALLOWED_EMAILS", "").split(",") if m.strip()}
    hits = []
    if deny is None:
        notes.append("privacy: KALMIDO_PRIVACY_DENY not set (no secrets, e.g. a pull request from a fork) - lines not scanned")
    else:
        for path, side in sorted(files.items()):
            if deny.search(allow.sub("", path) if allow else path):
                hits.append(f"{path}: private name in the file name")
            for text in side["+"]:
                if deny.search(allow.sub("", text) if allow else text):
                    hits.append(f"{path}: private spot in an added line")  # the line itself is not printed (public log)
    for sha, ae, ce in ids:
        for who, mail in (("author", ae), ("committer", ce)):
            ok = bool(NOREPLY.match(mail)) or mail.lower() in mails
            if not ok or (ident and ident.search(mail)):
                hits.append(f"{sha[:10]}: {who} address not allowed (only the project's noreply addresses)")
    return hits


def _json_at(rev: str, path: str) -> dict:
    """The JSON object of <path> at <rev>; {} = no such file / no object."""
    try:
        d = json.loads(git("show", f"{rev}:{path}"))
    except (RuntimeError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def check_i18n(base: str, head: str, files) -> list[str]:
    """2.1188.0 (#6194): the keys a change adds to static/i18n/<code>.json (merge base against HEAD); keys of a fragment at the
    merge base do not count (they are being folded in)."""
    langs = sorted(p for p in files if I18N_BASE.match(p))
    if not langs:
        return []
    mb = git("merge-base", base, head).strip()
    frag_keys: dict[str, set[str]] = {}
    for p in git("ls-tree", "-r", "--name-only", mb, "--", "static/i18n/neu/").split("\n"):
        if I18N_FRAG.match(p):
            for code, texts in _json_at(mb, p).items():
                if isinstance(texts, dict):
                    frag_keys.setdefault(code, set()).update(texts)
    hits = []
    for p in langs:
        code = I18N_BASE.match(p).group(1)
        old, known = _json_at(mb, p), frag_keys.get(code, set())
        new = [k for k in _json_at(head, p) if k not in old and k not in known]
        if new:
            more = f" and {len(new) - 3} more" if len(new) > 3 else ""
            hits.append(f"{p}: {len(new)} new key(s) ({', '.join(repr(k[:60]) for k in new[:3])}{more}) - new texts go into "
                        f"static/i18n/neu/<KID>.json, not into the big language file - a build job of the release tooling leaves "
                        f"them where they are, its merge queue moves them commit by commit; only a pull request outside the queue "
                        f"moves them itself (tools/i18n_neu.py auslagern --base <rev> --kid <KID>)")  # #6231: a job's own move conflicted with the queue's
    return hits


CSS_GRIFF = re.compile(r"^static/(?:app\.css|css/[^/]+\.css)$")  # #7294
MARK_CODE = re.compile(r"^(?:app\.py|kalmido/.+\.py|static/js/.+\.js|static/[^/]+\.js)$")
ENV_CODE = re.compile(r"^(?:app\.py|kalmido/.+\.py)$")
_TOOLS: dict[str, object] = {}


def base_tool(base: str, name: str):
    """tools/<name>.py of the BASE commit as a module (with the base's tools/lintmsg.py beside it), None when the base has
    none. The change's own copy never runs here: the same rule as for this file (review F9)."""
    if name in _TOOLS:
        return _TOOLS[name]
    import importlib.util
    import tempfile
    mod = None
    try:
        src, helper = git("show", f"{base}:tools/{name}.py"), git("show", f"{base}:tools/lintmsg.py")
    except RuntimeError:
        src = None
    if src:
        d = tempfile.mkdtemp(prefix="pr_lint-")
        for fn, text in ((f"{name}.py", src), ("lintmsg.py", helper)):
            with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
                f.write(text)
        spec = importlib.util.spec_from_file_location(f"base_{name}", os.path.join(d, f"{name}.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, d)
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.path.remove(d)
    _TOOLS[name] = mod
    return mod


def check_marks(base: str, files, notes: list[str]) -> list[str]:
    rules = base_tool(base, "check_rules")
    if rules is None:
        notes.append("marks: tools/check_rules.py is not in the base - not checked")
        return []
    hits = []
    for path, side in sorted(files.items()):
        if not MARK_CODE.match(path):
            continue
        n = sum(1 for text in side["+"] if rules.VERSION.search(text))
        if n:
            hits.append(f"{path}: {n} added line(s) with a version mark '2.<n> (#<id>)' - Why: the history is in git, the marks "
                        f"are 5 to 10 % of the lines and a source of merge conflicts. Instead: the comment says what holds and "
                        f"why; a pointer to a decided task stays as '(#<id>)' without the version (the dispatcher finds the "
                        f"decisions at a place by it), the history goes into the commit subject. Do not suppress it.")
    return hits


def _sup_scope(sup, path: str) -> bool:
    if path in ("tools/check_suppress.py", "tools/lintmsg.py") or not path.endswith((".py", ".js", ".mjs")):
        return False
    if any(part in sup.SKIP_DIRS for part in path.split("/")[:-1]):
        return False
    return path.startswith(tuple(t for t in sup.SCOPE if t.endswith("/"))) or path in sup.SCOPE or \
        bool(re.fullmatch(r"static/[^/]+\.js", path))


def check_suppress(base: str, files, notes: list[str]) -> list[str]:
    sup, rules = base_tool(base, "check_suppress"), base_tool(base, "check_rules")
    if sup is None:
        notes.append("suppress: tools/check_suppress.py is not in the base - not checked")
        return []
    net: dict[str, list] = {}  # kind -> [net count, {path: net}]
    for path, side in files.items():
        if not _sup_scope(sup, path):
            continue
        own_check = path.startswith("tools/check_")
        for sign, step in (("+", 1), ("-", -1)):
            for text in side[sign]:
                comments = sup.py_comments(text) if path.endswith(".py") else sup.js_comments(text)
                for _ln, c in comments:
                    for kind, ok in sup.found_in(c):
                        if own_check and kind.startswith("mark:"):
                            continue
                        for k in (kind,) if ok else (kind, kind + " without reason"):
                            e = net.setdefault(k, [0, {}])
                            e[0] += step
                            e[1][path] = e[1].get(path, 0) + step
                if rules is not None and ENV_CODE.match(path) and path != "kalmido/core/env.py":
                    n = len(rules.ENV.findall(text))
                    if n:
                        e = net.setdefault("env", [0, {}])
                        e[0] += step * n
                        e[1][path] = e[1].get(path, 0) + step * n
    hits = []
    for k, (n, per) in sorted(net.items()):
        if n <= 0:
            continue
        where = ", ".join(f"{p} +{v}" for p, v in sorted(per.items()) if v > 0)
        if k == "env":
            _fn, _s, why, instead = rules.RULES["env"]
            hits.append(f"{n} more os.environ read(s) outside kalmido/core/env.py ({where}) - Why: {why}. Instead: {instead}. "
                        f"Do not build around it.")
        elif sup.sharp(k):
            what = (f"{n} new '{k[:-len(' without reason')]}' marker(s) without the reason in the same comment"
                    if k.endswith(" without reason") else f"{n} more '{k}' marker(s) than the change removes")
            hits.append(f"{what} ({where}) - Why: {sup.WHY}. Instead: {sup.INSTEAD}. Do not suppress it.")
    return hits


def check_griff(base: str, head: str, files, notes: list[str]) -> list[str]:
    """#7294: the fixed sizes without the grip that the change adds to the CSS (tools/griff_lint.py of the base)."""
    css = sorted(p for p, side in files.items() if CSS_GRIFF.match(p) and side["+"])
    if not css:
        return []
    gl = base_tool(base, "griff_lint")
    if gl is None:
        notes.append("griff: tools/griff_lint.py is not in the base - not checked")
        return []
    mb = git("merge-base", base, head).strip()

    def show(rev, path):
        try:
            return git("show", f"{rev}:{path}")
        except RuntimeError:
            return ""
    added: dict[str, set[int]] = {}
    for path in css:
        lines = added.setdefault(path, set())
        for ln in git("diff", "-U0", "--no-color", "--no-ext-diff", f"{mb}", head, "--", path).splitlines():
            m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", ln)
            if m:
                a, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
                lines.update(range(a, a + n))
    # a rule moved from another file counts as known: the base of every changed CSS file
    olds = {p: show(mb, p) for p in files if CSS_GRIFF.match(p)}
    return gl.new_findings(olds, {p: show(head, p) for p in css}, added)


def check_oneway(files) -> list[str]:
    hits = []
    for r in ONEWAY:
        f_rx, ex = re.compile(r["files"]), re.compile(r["except"]) if r.get("except") else None
        rx, xl = re.compile(r["rx"]), re.compile(r["except_line"]) if r.get("except_line") else None
        for path, side in sorted(files.items()):
            if not f_rx.search(path) or (ex and ex.search(path)):
                continue
            plus = [x for x in side["+"] if not COMMENT.match(x)]
            minus = [x for x in side["-"] if not COMMENT.match(x)]
            if r["side"] == "+":
                cand = plus
            elif r["side"] in ("weg", "geaendert"):
                ps, ms = {x.strip() for x in plus}, {x.strip() for x in minus}
                cand = [x for x in minus if x.strip() not in ps]
                if r["side"] == "geaendert":
                    cand += [x for x in plus if x.strip() not in ms]
            else:
                cand = plus + minus
            seen = set()
            for x in cand:
                if rx.search(x) and not (xl and xl.search(x)) and x.strip() not in seen:
                    seen.add(x.strip())
                    hits.append(f"{path}: {r['name']}: {x.strip()[:140]}")
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="lint of a pull request / merge queue entry (#4006)")
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--only", default=",".join(CHECKS))
    ap.add_argument("--strict", action="store_true", help="one-way hits are red, not a note")
    ap.add_argument("--repo", default=ROOT)
    a = ap.parse_args(argv)
    REPO[0] = a.repo
    only = [c.strip() for c in a.only.split(",") if c.strip()]
    if any(c not in CHECKS for c in only):
        ap.error(f"--only: {', '.join(CHECKS)}")
    gh = os.environ.get("GITHUB_ACTIONS") == "true"
    try:
        cs, files = commits(a.base, a.head), diff_files(a.base, a.head)
    except RuntimeError as e:
        print(f"pr_lint: {e}", file=sys.stderr)
        return 2
    bad, notes = 0, []
    for c in only:
        if c == "subject":
            hits = check_subject(cs)
        elif c == "changelog":
            hits = check_changelog(files)
        elif c == "privacy":
            hits = check_privacy(idents(a.base, a.head), files, notes)
        elif c == "i18n":
            try:
                hits = check_i18n(a.base, a.head, files)
            except RuntimeError as e:
                print(f"pr_lint: {e}", file=sys.stderr)
                return 2
        elif c == "marks":
            hits = check_marks(a.base, files, notes)
        elif c == "suppress":
            hits = check_suppress(a.base, files, notes)
        elif c == "griff":
            try:
                hits = check_griff(a.base, a.head, files, notes)
            except RuntimeError as e:
                print(f"pr_lint: {e}", file=sys.stderr)
                return 2
        else:
            hits = check_oneway(files)
            for h in hits:
                print(f"::warning title=one-way step::{h}" if gh and not a.strict else f"oneway: {h}")
            if not a.strict:
                notes += [f"oneway: {len(hits)} one-way step(s) (a note, not red)"] if hits else []
                hits = []
        for h in hits:
            print(f"::error title=pr_lint {c}::{h}" if gh else f"{c}: {h}")
        bad += len(hits)
        print(f"pr_lint {c}: {'ok' if not hits else f'{len(hits)} problem(s)'}")
    for n in notes:
        print(f"::notice::{n}" if gh else n)
    print(f"pr_lint: {len(cs)} commit(s), {len(files)} file(s) of {a.base}..{a.head}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
