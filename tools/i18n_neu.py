#!/usr/bin/env python3
"""2.1188.0 (#6194): the new texts of a package out of the big language files into its fragment, and back in.

GitHub's merge queue merges without the merge drivers, and a package that appends its texts to the end of
static/i18n/<code>.json conflicts with every other one. So the new texts of a package live in static/i18n/neu/<KID>.json
({"de": {key: text}, "fr": {...}, ...}); the app mixes the fragments in at run time (kalmido/core/i18nfrag.py) and the pull
request lint (tools/pr_lint.py, check "i18n") refuses new keys in the big files.

  auslagern --base REV --kid KID   every key the working tree's static/i18n/<code>.json has and REV's has not leaves the big
                                   file (the other lines stay byte for byte) and goes into static/i18n/neu/<KID>.json (an
                                   existing fragment is extended). Idempotent: a second run moves nothing. Keys starting with
                                   "_" (_meta, month names) stay in the big file. Prints "<n> key(s) moved".
  einfalten                        every fragment into the big files (its keys appended before the closing brace) and the
                                   fragment files removed. For the release tooling's cut (a later step, not wired in yet);
                                   refused while the checks find a problem (a key in two places, kalmido/core/i18nfrag.py).

  python3 tools/i18n_neu.py auslagern --base REV --kid KID [--repo DIR]
  python3 tools/i18n_neu.py einfalten [--repo DIR]
Exit 0 done (also: nothing to do), 1 refused (a file not in the one-key-per-line layout, a fragment problem), 2 usage / git.
Standard library only.
"""
import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY_RE = re.compile(r'^  (".*?(?<!\\)")\s*:')  # as tools/i18n_merge.py
KID_RE = re.compile(r"[\w.-]{1,40}")


def _frag_mod(repo):
    """kalmido/core/i18nfrag.py of <repo> (the one reader of the fragments), loaded by its path."""
    spec = importlib.util.spec_from_file_location("i18nfrag", os.path.join(repo, "kalmido", "core", "i18nfrag.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def entry_lines(text):
    """-> [(key or None, line)] of a big language file in the one-key-per-line layout ("{" / "}" / blank lines: key None);
    None = another layout."""
    lines = text.split("\n")
    if len(lines) < 2 or lines[0].strip() != "{" or lines[-1] != "" or lines[-2].strip() != "}":
        return None
    out = []
    for i, ln in enumerate(lines[:-1]):
        if i == 0 or i == len(lines) - 2 or not ln.strip():
            out.append((None, ln))
            continue
        m = KEY_RE.match(ln)
        if not m:
            return None
        out.append((json.loads(m.group(1)), ln))
    return out


def without_keys(text, drop):
    """The text of a big language file without the lines of the keys in <drop>; every other line byte for byte as it was, only
    the comma behind the new last entry goes when the old last one left. None: another layout."""
    rows = entry_lines(text)
    if rows is None:
        return None
    last_before = max((i for i, (k, _) in enumerate(rows) if k is not None), default=-1)
    kept = [(k, ln) for i, (k, ln) in enumerate(rows) if k is None or k not in drop]
    last_after = max((i for i, (k, _) in enumerate(kept) if k is not None), default=-1)
    if last_after >= 0 and rows[last_before][0] in drop:
        k, ln = kept[last_after]
        kept[last_after] = (k, ln[:-1] if ln.endswith(",") else ln)
    return "\n".join(ln for _, ln in kept) + "\n"


def git(repo, *args):
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, errors="replace")
    if p.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout


def write_fragment(path, frag):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(dump_fragment(frag))


def dump_fragment(frag):
    """A fragment as text: one language per block, one key per line (the layout of the big files), languages sorted."""
    j = lambda o: json.dumps(o, ensure_ascii=False)  # noqa: E731
    blocks = [f"  {j(c)}: {{\n" + ",\n".join(f"    {j(k)}: {j(v)}" for k, v in frag[c].items()) + "\n  }" if frag[c] else f"  {j(c)}: {{}}"
              for c in sorted(frag)]
    return "{\n" + ",\n".join(blocks) + "\n}\n"


def auslagern(repo, base, kid):
    fr = _frag_mod(repo)
    i18n = os.path.join(repo, "static", "i18n")
    fpath = os.path.join(i18n, fr.FRAG_DIR, kid + ".json")
    frag = {}
    if os.path.isfile(fpath):
        with open(fpath, encoding="utf-8") as f:
            frag = json.load(f)
    moved, changed = 0, {}
    for code in fr.lang_codes(i18n):
        rel = f"static/i18n/{code}.json"
        try:
            old = json.loads(git(repo, "show", f"{base}:{rel}"))
        except RuntimeError:
            print(f"{rel}: not in {base} (a new language) - left as it is")
            continue
        with open(os.path.join(i18n, code + ".json"), encoding="utf-8") as f:
            text = f.read()
        cur = json.loads(text)
        new = [k for k in cur if k not in old and not k.startswith("_")]
        for k in cur:
            if k not in old and k.startswith("_"):
                print(f"{rel}: {k!r} stays (keys with _ belong into the big file)")
        if not new:
            continue
        out = without_keys(text, set(new))
        if out is None:
            print(f"{rel}: not in the one-key-per-line layout - nothing moved", file=sys.stderr)
            return 1
        want = {k: v for k, v in cur.items() if k not in set(new)}
        if json.loads(out) != want:  # never write a file that lost or changed anything else
            print(f"{rel}: the result does not match - nothing moved", file=sys.stderr)
            return 1
        changed[code] = out
        dst = frag.setdefault(code, {})
        for k in new:
            dst[k] = cur[k]
        moved += len(new)
    for code, out in changed.items():
        with open(os.path.join(i18n, code + ".json"), "w", encoding="utf-8") as f:
            f.write(out)
    if moved:
        write_fragment(fpath, frag)
    print(f"{moved} key(s) moved into static/i18n/{fr.FRAG_DIR}/{kid}.json" if moved else "0 key(s) moved (nothing new)")
    return 0


def einfalten(repo):
    fr = _frag_mod(repo)
    i18n = os.path.join(repo, "static", "i18n")
    errs = []
    frags = fr.read_fragments(i18n, errs)
    errs += fr.fragment_problems(i18n, frags)
    if errs:
        for e in errs:
            print("refused:", e, file=sys.stderr)
        return 1
    if not frags:
        print("0 fragment(s), nothing to fold in")
        return 0
    n = 0
    for code in fr.lang_codes(i18n):
        add = fr.merge_lang({}, code, frags)
        if not add:
            continue
        path = os.path.join(i18n, code + ".json")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        rows = entry_lines(text)
        if rows is None:
            print(f"static/i18n/{code}.json: not in the one-key-per-line layout - nothing folded in", file=sys.stderr)
            return 1
        cur = json.loads(text)
        body = text[:text.rstrip().rfind("}")].rstrip("\n")
        lines = [f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}" for k, v in add.items()]
        if not cur:
            out = "{\n" + ",\n".join(lines) + "\n}\n"
        else:
            out = body + ",\n" + ",\n".join(lines) + "\n}\n"
        if json.loads(out) != {**cur, **add}:
            print(f"static/i18n/{code}.json: the result does not match - nothing folded in", file=sys.stderr)
            return 1
        with open(path, "w", encoding="utf-8") as f:
            f.write(out)
        n += len(add)
    for p in fr.fragment_paths(i18n):
        os.remove(p)
    print(f"{n} text(s) of {len(frags)} fragment(s) folded in")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="new texts of a package: into static/i18n/neu/<KID>.json and back (#6194)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("auslagern")
    a1.add_argument("--base", required=True)
    a1.add_argument("--kid", required=True)
    a1.add_argument("--repo", default=ROOT)
    a2 = sub.add_parser("einfalten")
    a2.add_argument("--repo", default=ROOT)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "auslagern":
            if not KID_RE.fullmatch(a.kid):
                ap.error("--kid: letters, digits, . _ - only")
            return auslagern(a.repo, a.base, a.kid)
        return einfalten(a.repo)
    except RuntimeError as e:
        print(f"i18n_neu: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
