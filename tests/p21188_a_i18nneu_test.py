#!/usr/bin/env python3
# kalmido-suite: nodata
"""2.1188.0 A (#6194): the new texts of a package in their own file static/i18n/neu/<KID>.json, so two entries of GitHub's
merge queue (no merge drivers there) never conflict at the end of the big language files. No container, no data:
  - kalmido/core/i18nfrag.py: base + fragments in the order of their names, the whole file as it goes out (unchanged
    without a fragment), the problems (a key in the base AND a fragment, in two fragments, a language without a file, _keys)
  - the server's load_languages + tr() (kalmido/core/i18n.py, run from its source) know a fragment's text
  - the language parts and the web manifest (kalmido/core/codemanifest.py, the same recipe as core/i18nparts.py): the
    fragment's text is in the parts, the version changes, i18n/<code>.json goes out with it, a language without one as it is
  - tools/i18n_check.py: a doubled key is red, a clean fragment counts
  - tools/pr_lint.py check i18n: a new key in static/i18n/<code>.json is red with a hint to the fragment; a changed or
    deleted text, a new fragment and folding a fragment back in are green
  - tools/i18n_neu.py auslagern: exactly the new keys move (the rest of the big files byte for byte), an existing fragment is
    extended, a second run moves nothing; einfalten puts them back and removes the fragment
  - git merge of two branches with one fragment each, without any merge driver: no conflict."""
import ast
import glob
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from kt import FAILS, OKS, check  # noqa: E402

CORE = os.path.join(ROOT, "kalmido", "core")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FRAG = load("i18nfrag", os.path.join(CORE, "i18nfrag.py"))
GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="Kalmido", GIT_AUTHOR_EMAIL="noreply@kalmido.com", GIT_COMMITTER_NAME="Kalmido",
               GIT_COMMITTER_EMAIL="noreply@kalmido.com")
for k in [k for k in GIT_ENV if k.startswith("KALMIDO_PRIVACY") or k == "GITHUB_ACTIONS"]:
    GIT_ENV.pop(k)


def wjson(path, obj, raw=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(raw if raw is not None else json.dumps(obj, ensure_ascii=False))


def big(d):
    """A language file in the layout of static/i18n/<code>.json; keys with … escaped like the real files."""
    return "{\n" + ",\n".join(f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in d.items()) + "\n}\n"


def sh(repo, *a):
    p = subprocess.run(["git", "-C", repo, "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *a],
                       capture_output=True, text=True, env=GIT_ENV)
    if p.returncode:
        raise RuntimeError(f"git {a}: {p.stdout} {p.stderr}")
    return p.stdout.strip()


def commit(repo, msg):
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", msg)
    return sh(repo, "rev-parse", "HEAD")


DE = {"_meta": {"name": "Deutsch", "locale": "de-DE"}, "Save": "Speichern", "Open…": "Öffnen…", "{0} file": ["{0} Datei", "{0} Dateien"]}
FR = {"_meta": {"name": "Français", "locale": "fr-FR"}, "Save": "Enregistrer", "Open…": "Ouvrir…", "{0} file": ["{0} fichier", "{0} fichiers"]}

with tempfile.TemporaryDirectory() as tmp:
    # ------------------------------------------------------------ 1. the reader (kalmido/core/i18nfrag.py)
    d = os.path.join(tmp, "i18n")
    wjson(os.path.join(d, "de.json"), None, big(DE))
    wjson(os.path.join(d, "fr.json"), None, big(FR))
    check(FRAG.fragment_names(d) == [] and FRAG.lang_codes(d) == ["de", "fr"], "without static/i18n/neu/: no fragment, the languages")
    raw_de = open(os.path.join(d, "de.json"), "rb").read()
    check(FRAG.lang_bytes(d, "de") is not None and FRAG.lang_bytes(d, "de") == raw_de, "no fragment: the whole file goes out as it is")
    wjson(os.path.join(d, "neu", "4600.json"), {"de": {"New text": "Neuer Text", "Two": "Zwei (4600)"}})
    wjson(os.path.join(d, "neu", "4700.json"), {"de": {"Two": "Zwei (4700)"}, "fr": {"New text": "Nouveau texte"}})
    check(FRAG.lang_codes(d) == ["de", "fr"], "the folder neu/ is no language")
    check(FRAG.fragment_names(d) == ["4600.json", "4700.json"], f"the fragments sorted by name {FRAG.fragment_names(d)}")
    de = FRAG.load_lang(d, "de")
    check(de["New text"] == "Neuer Text" and de["Save"] == "Speichern" and de["_meta"]["name"] == "Deutsch", "base + fragment")
    check(de["Two"] == "Zwei (4700)", "a key in two fragments: the later name wins at run time (the checks make it red)")
    check(FRAG.load_lang(d, "fr")["New text"] == "Nouveau texte" and "Two" not in FRAG.load_lang(d, "fr"), "each language its own texts")
    out = FRAG.lang_bytes(d, "de")
    check(json.loads(out) == de and out.decode().count("\n") == len(de) + 2, "the whole file with the fragments, one key per line")
    probs = FRAG.fragment_problems(d)
    check(any("4700.json" in p and "'Two'" in p and "4600.json" in p for p in probs) and len(probs) == 1,
          f"a key in two fragments is a problem: {probs}")
    wjson(os.path.join(d, "neu", "4800.json"), {"de": {"Save": "Sichern", "_months": []}, "xx": {"a": "b"}})
    probs = FRAG.fragment_problems(d)
    check(any("4800.json" in p and "'Save'" in p and "de.json" in p for p in probs), f"a key in the base AND a fragment: {probs}")
    check(any("'_months'" in p for p in probs) and any("'xx'" in p for p in probs), f"_keys and a language without a file: {probs}")
    wjson(os.path.join(d, "neu", "4900.json"), None, '{"de": {"broken": ')
    errs = []
    frags = FRAG.read_fragments(d, errs)
    check([n for n, _ in frags] == ["4600.json", "4700.json", "4800.json"] and errs and "4900.json" in errs[0],
          f"a broken fragment is left out and named {errs}")
    for n in ("4700.json", "4800.json", "4900.json"):
        os.remove(os.path.join(d, "neu", n))
    check(FRAG.fragment_problems(d) == [], "a clean fragment: no problem")

    # ------------------------------------------------------------ 2. the server: load_languages + tr() from its source
    src = open(os.path.join(CORE, "i18n.py"), encoding="utf-8").read()
    want = {"load_languages", "tr", "_key"}
    nodes = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name in want]
    check({n.name for n in nodes} == want, f"server functions found {[n.name for n in nodes]}")
    check("merge_lang(d, code, frags)" in src and "read_fragments(I18N_DIR)" in src, "load_languages mixes the fragments in")
    ns = {"glob": glob, "os": os, "json": json, "re": re, "I18N_DIR": d, "merge_lang": FRAG.merge_lang,
          "read_fragments": FRAG.read_fragments, "lang": lambda: "de"}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "kalmido/core/i18n.py", "exec"), ns)  # noqa: S102 (our own source)
    ns["LANGS"] = ns["load_languages"]()
    check(ns["tr"]("New text") == "Neuer Text" and ns["tr"]("Save") == "Speichern" and ns["tr"]("New text", lg="fr") == "New text",
          "tr() knows a fragment's text (and English without one)")
    check(set(ns["LANGS"]) == {"en", "de", "fr"}, f"no language 'neu' {sorted(ns['LANGS'])}")

    # ------------------------------------------------------------ 3. the language parts + the web manifest
    app = os.path.join(tmp, "app")
    os.makedirs(os.path.join(app, "static"))
    for n in os.listdir(ROOT):
        if n not in ("static", ".git"):
            os.symlink(os.path.join(ROOT, n), os.path.join(app, n))
    for n in os.listdir(os.path.join(ROOT, "static")):
        if n != "i18n":
            os.symlink(os.path.join(ROOT, "static", n), os.path.join(app, "static", n))
    # every language with the fragments the tree already has (static/i18n/neu/), the test's own fragment on top
    shutil.copytree(os.path.join(ROOT, "static", "i18n"), os.path.join(app, "static", "i18n"))
    sys.path.insert(0, CORE)
    import codemanifest as cm  # noqa: E402 (as tools/web_manifest.py: the folder by its path, without the app)
    del sys.path[0]
    v0, t0, p0 = cm.cm_i18n(app)
    ai = os.path.join(app, "static", "i18n")
    key = "A text only the fragment of #6194's test has"
    wjson(os.path.join(ai, "neu", "zz-p21188-a.json"), {"de": {key: "Ein Text nur aus dem Fragment"}})
    v1, t1, p1 = cm.cm_i18n(app)
    got = {}
    for url, data in p1.items():
        if url.startswith("/static/i18n/de."):
            got.update(json.loads(data))
    check(got.get(key) == "Ein Text nur aus dem Fragment", "the de parts hold the fragment's text")
    check(v1 != v0, f"a fragment is a new version of the split texts ({v0} -> {v1})")
    check({u: x for u, x in p1.items() if u.startswith("/static/i18n/fr.")} == {u: x for u, x in p0.items() if u.startswith("/static/i18n/fr.")},
          "the parts of a language without a fragment stay the same")
    rows = lambda t: dict(r.split("=", 1) for r in t.split(";")[1:])  # noqa: E731 (meta kalmido-i18nv: names;<code>=<hashes>;...)
    check(rows(t1)["fr"] == rows(t0)["fr"] and rows(t1)["de"] != rows(t0)["de"], "kalmido-i18nv: only the de row changes")
    raw = open(os.path.join(ai, "de.json"), "rb").read()
    served, merged = cm.cm_served(os.path.join(app, "static"), "i18n/de.json", raw)
    check(merged and json.loads(served).get(key) == "Ein Text nur aus dem Fragment" and json.loads(served) == FRAG.load_lang(ai, "de"),
          "/static/i18n/de.json goes out with the fragment (core/pages.py st_asset, the manifest)")
    fr_raw = open(os.path.join(ai, "fr.json"), "rb").read()
    fr_frag = FRAG.has_fragment("fr", FRAG.read_fragments(ai))  # the tree's own fragments may hold French texts
    check(cm.cm_served(os.path.join(app, "static"), "i18n/fr.json", fr_raw) == (FRAG.lang_bytes(ai, "fr", fr_raw), fr_frag),
          "fr.json: as it is without a fragment for fr (section 1), else with the tree's fragments")
    check(cm.cm_served(os.path.join(app, "static"), "i18n/neu/zz-p21188-a.json", b"{}") == (b"{}", False), "the fragment file itself as it is")
    pages = open(os.path.join(CORE, "pages.py"), encoding="utf-8").read()
    parts = open(os.path.join(CORE, "i18nparts.py"), encoding="utf-8").read()
    check("CM_LANG_FILE.fullmatch(filename)" in pages and "fragment_paths(os.path.join(root, \"i18n\"))" in pages,
          "the static route sends i18n/<code>.json through st_asset (a fragment is a new version)")
    check(parts.count("load_lang(I18N_DIR, code)") == 2 and "fragment_paths(I18N_DIR)" in parts and parts.count("lang_bytes(I18N_DIR, code)") == 2,
          "core/i18nparts.py: the parts, their versions and the split-off answers read the fragments")

    # ------------------------------------------------------------ 4. tools/i18n_check.py
    ic = load("i18n_check_6194", os.path.join(ROOT, "tools", "i18n_check.py"))
    ic.I18N_DIR = ai
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = ic.main(["de"])
    txt = buf.getvalue()
    check(rc == 0 and re.search(r"fragments: \d+ in static/i18n/neu/ \([^)]*zz-p21188-a\.json[^)]*\), 0 error\(s\)", txt) and f"unused key {key!r}" in txt,
          f"i18n_check: a clean fragment counts, its unused text is a warning ({rc}) {txt[-400:]}")
    wjson(os.path.join(ai, "neu", "zz-p21188-b.json"), {"de": {key: "doppelt", "Save": "doppelt"}})
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = ic.main(["de"])
    txt = buf.getvalue()
    check(rc == 1 and "ERROR static/i18n/neu/zz-p21188-b.json: de: 'Save' is already in static/i18n/de.json" in txt and "also in static/i18n/neu/zz-p21188-a.json" in txt,
          f"i18n_check: a doubled key is red ({rc}) {[ln for ln in txt.splitlines() if 'ERROR' in ln][:3]}")
    ic.I18N_DIR = os.path.join(ROOT, "static", "i18n")

    # ------------------------------------------------------------ 5. pr_lint check i18n + 6. tools/i18n_neu.py + 7. the merge
    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(repo, "kalmido", "core"))
    sh(tmp, "init", "-q", "-b", "main", repo)
    shutil.copy(os.path.join(CORE, "i18nfrag.py"), os.path.join(repo, "kalmido", "core"))
    wjson(os.path.join(repo, "static", "i18n", "de.json"), None, big(DE))
    wjson(os.path.join(repo, "static", "i18n", "fr.json"), None, big(FR))
    base = commit(repo, "#6194: start")
    LINT = os.path.join(ROOT, "tools", "pr_lint.py")
    NEU = os.path.join(ROOT, "tools", "i18n_neu.py")

    def lint(b):
        p = subprocess.run([sys.executable, LINT, "--repo", repo, "--base", b, "--only", "i18n"], capture_output=True, text=True, env=GIT_ENV)
        return p.returncode, p.stdout + p.stderr

    def neu(*a):
        p = subprocess.run([sys.executable, NEU, *a, "--repo", repo], capture_output=True, text=True, env=GIT_ENV)
        return p.returncode, p.stdout + p.stderr

    def put(code, d):
        wjson(os.path.join(repo, "static", "i18n", code + ".json"), None, big(d))

    # a package adds texts to the big files (one in the middle, one at the end) and changes one
    put("de", {"_meta": DE["_meta"], "Save": "Sichern", "Mid…": "Mitte…", "Open…": "Öffnen…", "{0} file": DE["{0} file"], "End": "Ende"})
    put("fr", dict(FR, End="Fin"))
    sh(repo, "checkout", "-q", "-b", "p1")
    commit(repo, "#6194: texts the old way")
    rc, out = lint(base)
    check(rc == 1 and "static/i18n/de.json: 2 new key(s)" in out and "static/i18n/neu/<KID>.json" in out and "fr.json: 1 new key" in out,
          f"pr_lint i18n: new keys in the big files are red with the hint ({rc}) {out[-500:]}")
    rc, out = neu("auslagern", "--base", base, "--kid", "4600")
    check(rc == 0 and "3 key(s) moved into static/i18n/neu/4600.json" in out, f"auslagern: 3 keys moved ({rc}) {out}")
    de_now = open(os.path.join(repo, "static", "i18n", "de.json"), encoding="utf-8").read()
    want = big(DE).replace('"Speichern"', '"Sichern"')
    check(de_now == want, f"de.json: the base file byte for byte, only the changed text differs {de_now!r}")
    check(open(os.path.join(repo, "static", "i18n", "fr.json"), encoding="utf-8").read() == big(FR),
          "fr.json: the comma behind the old last line is back as before (byte for byte)")
    fr6 = json.load(open(os.path.join(repo, "static", "i18n", "neu", "4600.json"), encoding="utf-8"))
    check(fr6 == {"de": {"Mid…": "Mitte…", "End": "Ende"}, "fr": {"End": "Fin"}}, f"the fragment holds exactly the new keys {fr6}")
    rc, out = neu("auslagern", "--base", base, "--kid", "4600")
    check(rc == 0 and "0 key(s) moved" in out, f"auslagern a second time moves nothing ({out})")
    commit(repo, "#6194: texts as fragment")
    rc, out = lint(base)
    check(rc == 0 and "pr_lint i18n: ok" in out, f"pr_lint i18n: a changed text + a new fragment are green ({rc}) {out[-300:]}")
    # the same package adds one more text later: the fragment is extended
    put("de", {**json.loads(de_now), "Later": "Später"})
    rc, out = neu("auslagern", "--base", base, "--kid", "4600")
    fr6 = json.load(open(os.path.join(repo, "static", "i18n", "neu", "4600.json"), encoding="utf-8"))
    check(rc == 0 and "1 key(s) moved" in out and list(fr6["de"]) == ["Mid…", "End", "Later"], f"an existing fragment is extended {fr6}")
    p1 = commit(repo, "#6194: one more")
    # a parallel package from the same base: its own fragment; merged without any driver
    sh(repo, "checkout", "-q", "-b", "p2", base)
    put("de", {**DE, "Other": "Anderes"})
    put("fr", {**FR, "Other": "Autre"})
    rc, out = neu("auslagern", "--base", base, "--kid", "4700")
    commit(repo, "#6194: the other package")
    p = subprocess.run(["git", "-C", repo, "-c", "merge.i18n.driver=false", "-c", "core.hooksPath=/dev/null", "merge", "-q", "--no-edit", p1],
                       capture_output=True, text=True, env=GIT_ENV)
    check(p.returncode == 0 and not sh(repo, "diff", "--name-only", "--diff-filter=U"), f"two packages with a fragment each: git merge without a driver, no conflict {p.stdout}{p.stderr}")
    i18n_repo = os.path.join(repo, "static", "i18n")
    check(FRAG.load_lang(i18n_repo, "de").get("Other") == "Anderes" and FRAG.load_lang(i18n_repo, "de").get("Later") == "Später"
          and FRAG.fragment_problems(i18n_repo) == [], "after the merge: both packages' texts, no problem")
    merged = sh(repo, "rev-parse", "HEAD")
    # a key deleted from the big file is fine
    put("fr", {k: v for k, v in FR.items() if k != "Save"})
    commit(repo, "#6194: a text removed")
    rc, out = lint(merged)
    check(rc == 0, f"pr_lint i18n: a deleted text is green ({out[-200:]})")
    # folding the fragments back in (the release's cut): green, the fragments are gone
    before = {c: FRAG.load_lang(i18n_repo, c) for c in ("de", "fr")}
    rc, out = neu("einfalten")
    check(rc == 0 and not FRAG.fragment_names(i18n_repo) and {c: json.load(open(os.path.join(i18n_repo, c + ".json"), encoding="utf-8")) for c in ("de", "fr")} == before,
          f"einfalten: the texts in the big files, the fragments gone ({rc}) {out}")
    commit(repo, "#6194: fold in")
    rc, out = lint(merged)
    check(rc == 0, f"pr_lint i18n: folding a fragment in is green ({out[-300:]})")
    rc, out = neu("einfalten")
    check(rc == 0 and "nothing to fold in" in out, "einfalten without fragments: nothing to do")
    # einfalten refuses while a key stands twice
    wjson(os.path.join(i18n_repo, "neu", "4800.json"), {"de": {"Save": "doppelt"}})
    rc, out = neu("einfalten")
    check(rc == 1 and "refused" in out and os.path.isfile(os.path.join(i18n_repo, "neu", "4800.json")), f"einfalten refuses a doubled key ({rc}) {out}")

print(f"\n{OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
