"""2.1188.0 (#6194): The new texts of a package in a file of their own, mixed into the language files at run time.

GitHub's merge queue merges without the merge drivers of tools/git_setup.sh; when every package appends its new texts to the
end of static/i18n/<code>.json, two packages always conflict there. So a package writes its NEW texts into
static/i18n/neu/<KID>.json = {"de": {key: text}, "fr": {...}, ...} (one new file per package: nothing to merge), and every
reader takes a language as the base file plus the fragments in the order of their file names (fragment_names). Changing or
deleting a text in the base files stays allowed; folding the fragments into the base files is a later step of the release
tooling. A key in the base AND in a fragment, or in two fragments, is an error of the checks (fragment_problems,
tools/i18n_check.py); at run time the later file wins and the app keeps running.

Standard library only, no import from the app: core/i18n.py, core/i18nparts.py, core/codemanifest.py, core/pages.py and the
tools (tools/i18n_check.py, tools/perf_budget.py, tools/build_demo.py, ...) load it, the tools by its path."""
import json
import os
import re

FRAG_DIR = "neu"  # static/i18n/neu/<KID>.json
LANG_CODE = re.compile(r"[a-z]{2,3}(-[A-Za-z0-9]{2,8})?")  # as core/i18nparts.py _I18NP_CODE
FRAG_NAME = re.compile(r"[\w.-]+\.json")


def fragment_names(i18n_dir):
    """The fragment files of static/i18n/neu/, sorted by name (the order they are mixed in); [] without the folder."""
    d = os.path.join(i18n_dir, FRAG_DIR)
    try:
        names = os.listdir(d)
    except OSError:
        return []
    return sorted(n for n in names if FRAG_NAME.fullmatch(n) and not n.startswith(".") and os.path.isfile(os.path.join(d, n)))


def fragment_paths(i18n_dir):
    return [os.path.join(i18n_dir, FRAG_DIR, n) for n in fragment_names(i18n_dir)]


def read_fragments(i18n_dir, errors=None):
    """[(file name, {code: {key: text}})] of every readable fragment; a broken one is left out (its reason into errors, or a
    log line without a list): the app runs on with the base files."""
    out = []
    for p in fragment_paths(i18n_dir):
        name = os.path.basename(p)
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict) or not all(isinstance(k, str) and isinstance(v, dict) for k, v in d.items()):
                raise ValueError('needs {"<code>": {"<English key>": <text>}, ...}')
        except (OSError, ValueError) as e:
            why = f"static/i18n/{FRAG_DIR}/{name}: {e}"
            if errors is None:
                print("i18n: skipping fragment", why, flush=True)
            else:
                errors.append(why)
            continue
        out.append((name, d))
    return out


def merge_lang(base, code, frags):
    """The language <code> as the app uses it: the base dict + the texts of every fragment for <code> (a new dict)."""
    out = dict(base)
    for _, d in frags:
        out.update(d.get(code) or {})
    return out


def has_fragment(code, frags):
    return any(d.get(code) for _, d in frags)


def load_lang(i18n_dir, code, frags=None):
    """static/i18n/<code>.json + the fragments -> dict (OSError / ValueError of the base file go to the caller)."""
    with open(os.path.join(i18n_dir, code + ".json"), encoding="utf-8") as f:
        base = json.load(f)
    return merge_lang(base, code, read_fragments(i18n_dir) if frags is None else frags)


def lang_codes(i18n_dir):
    """The codes of the language files static/i18n/<code>.json (never the folder neu/)."""
    return sorted(n[:-5] for n in os.listdir(i18n_dir) if n.endswith(".json") and LANG_CODE.fullmatch(n[:-5])
                  and os.path.isfile(os.path.join(i18n_dir, n)))


def dump_lang(d):
    """A language dict as text in the layout of the base files: one key per line."""
    return "{\n" + ",\n".join(f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}" for k, v in d.items()) + "\n}\n"


def lang_bytes(i18n_dir, code, data=None, frags=None):
    """GET /static/i18n/<code>.json as it goes out: the file as it is (data = its bytes, None = read) while no fragment has
    texts for <code>, else the base + the fragments (dump_lang)."""
    if data is None:
        with open(os.path.join(i18n_dir, code + ".json"), "rb") as f:
            data = f.read()
    frags = read_fragments(i18n_dir) if frags is None else frags
    if not has_fragment(code, frags):
        return data
    try:
        base = json.loads(data)
    except ValueError:  # a broken base file goes out as it is (the checks name it)
        return data
    return dump_lang(merge_lang(base, code, frags)).encode("utf-8") if isinstance(base, dict) else data


def fragment_problems(i18n_dir, frags=None):
    """The errors of the fragments for the checks (tools/i18n_check.py): unreadable, a language without a base file, a key that
    starts with "_" (_meta, the month names: base only), a key in the base AND a fragment or in two fragments."""
    errs = []
    if frags is None:
        frags = read_fragments(i18n_dir, errs)
    codes = set(lang_codes(i18n_dir))
    bases = {}
    seen = {}  # (code, key) -> the first fragment with it
    for name, d in frags:
        where = f"static/i18n/{FRAG_DIR}/{name}"
        for code, texts in d.items():
            if code not in codes:
                errs.append(f"{where}: {code!r} has no language file static/i18n/{code}.json")
                continue
            if code not in bases:
                try:
                    with open(os.path.join(i18n_dir, code + ".json"), encoding="utf-8") as f:
                        bases[code] = json.load(f)
                except (OSError, ValueError) as e:
                    errs.append(f"static/i18n/{code}.json: {e}")
                    bases[code] = {}
            for k in texts:
                if k.startswith("_"):
                    errs.append(f"{where}: {code}: {k!r} belongs into static/i18n/{code}.json (keys with _ stay in the base file)")
                elif k in bases[code]:
                    errs.append(f"{where}: {code}: {k[:80]!r} is already in static/i18n/{code}.json (change it there, or take it out of one of them)")
                elif (code, k) in seen:
                    errs.append(f"{where}: {code}: {k[:80]!r} is also in static/i18n/{FRAG_DIR}/{seen[(code, k)]}")
                else:
                    seen[(code, k)] = name
    return errs
