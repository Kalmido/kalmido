#!/usr/bin/env python3
"""The building-block duty of the one grip as a check (#7294, decided 19.11.2026): a CSS rule that gives a panel, a column
or a floating window a fixed size, without the grip (static/js/grip.js, docs/dev/kern.md "Resizing: the one grip"), is red.

What counts (per declaration of a style rule):
  column   grid-template-columns with a fixed track beside an fr track (a list column beside the content): a length of at
           least GRIFF_MIN_REM (12rem / 192px; Icon-, Zahlen-, Beschriftungs-Spalten below it stay green), a var() without a
           fallback (its size is not seen here), read through minmax() / min() / max() / clamp() / calc() / fit-content()
  flex     flex: 0 0 <fixed> / flex-basis: <fixed> of the same kind (a list beside the content as a flex item; a field that
           may shrink, flex: 0 1 X, is no panel)
  window   a written width / height of at least 12rem of a floating box: the rule has position fixed / absolute, or its
           selector lies under a pop-up (#pop, .dpop, .lightbox, #achat); not a pseudo element (decoration)
Green: a rule that reads the grip's variable --g-<key> (the kern's naming rule) or one of the old grips' variables
(GRIFF_LEGACY, until their moves #7312 - #7324 are through); auto-fill / auto-fit; pure fr grids; a rule only inside a phone
@media (max-width up to 767px); the cards of dialogs (.modal ... .card: the dialog grip comes by itself); and a rule with the
comment /* griff-ok: REASON */ in it or right before it (menus, hints, icon / number columns: a reason is required).

tools/pr_lint.py "griff" checks only what a change ADDS (diff against the base; a rule moved unchanged is not new), the stock
goes through the audit tasks. Here as a module (parse / findings) and a command for the stock:
  python3 tools/griff_lint.py FILE.css ...   -> the findings of whole files (exit 1 with findings)
Python standard library only."""
from __future__ import annotations

import re
import sys

GRIFF_MIN_REM = 12.0
GRIFF_LEGACY = ("--sideW", "--detW", "--chatW", "--dv-sw", "--dv-mw", "--splW")  # the old grips (#7293 audit), until they move
GRIFF_FLOAT_SEL = re.compile(r"#pop\b|\.dpop\b|\.lightbox\b|#achat\b")
GRIFF_OK = re.compile(r"griff-ok:\s*[^\s*]")
GRIP_VAR = re.compile(r"var\(\s*--g-[a-z0-9_-]+", re.I)
LEN = re.compile(r"(-?\d*\.?\d+)(rem|em|px)\b")
PHONE_MQ = re.compile(r"max-width\s*:\s*(\d+(?:\.\d+)?)(px|rem|em)")
CSS_FILES = re.compile(r"^static/(?:app\.css|css/[^/]+\.css)$")
WHY = "a panel, column or window with a fixed size the person cannot change (everything should be adjustable, #7294)"
INSTEAD = ("the one grip: grip_col / grip_row / grip_corner (static/js/grip.js) and the rule reads var(--g-<key>, <default>) "
           "(docs/dev/kern.md \"Resizing: the one grip\"; a list beside its content in the page: render.js gcol_html); a menu, "
           "a hint, an icon or number column: /* griff-ok: REASON */ at the rule")


def _strip(text: str):
    """(text with comments blanked out to spaces - lines and offsets stay, [(start, end, comment text)])"""
    out, comments, i, n = [], [], 0, len(text)
    while i < n:
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            comments.append((i, j, text[i:j]))
            out.append("".join("\n" if ch == "\n" else " " for ch in text[i:j]))
            i = j
        elif text[i] in "\"'":
            q, j = text[i], i + 1
            while j < n and text[j] != q:
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out), comments


def parse(text: str) -> list[dict]:
    """The declarations of the style rules: {sel, prop, val, line, media: [at-rule preludes around], decls: {prop: val} of
    its rule, ok: the rule carries griff-ok}. Nested at-rules (@media / @supports / @container / @layer) are walked into;
    @keyframes / @font-face are left out."""
    clean, comments = _strip(text)
    line_at = [0]
    for k, ch in enumerate(clean):
        if ch == "\n":
            line_at.append(k + 1)

    def lineno(off):
        lo, hi = 0, len(line_at) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_at[mid] <= off:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    out: list[dict] = []
    stack: list[tuple[str, str, int]] = []  # (kind 'at' | 'rule' | 'skip', prelude, start offset of the prelude)
    start = 0
    rule_decls: list[dict] = []
    i = 0
    while i < len(clean):
        ch = clean[i]
        if ch == "{":
            pre = clean[start:i].strip()
            kind = "skip" if any(s[0] in ("skip", "rule") for s in stack) or re.match(r"@(-\w+-)?(keyframes|font-face|page)\b", pre) \
                else "at" if pre.startswith("@") else "rule"
            stack.append((kind, pre, start))
            if kind == "rule":
                rule_decls = []
            start = i + 1
        elif ch == "}":
            if stack:
                kind, pre, pstart = stack.pop()
                if kind == "rule":
                    body_start = clean.rfind("{", pstart, i)
                    _decls(clean, body_start + 1, i, rule_decls, lineno)
                    media = [p for k, p, _s in stack if k == "at"]
                    raw = clean[pstart:body_start]
                    ok = _ok_at(text, comments, pstart + len(raw) - len(raw.lstrip()), body_start, i)
                    d = {x["prop"]: x["val"] for x in rule_decls}
                    for x in rule_decls:
                        out.append({"sel": " ".join(pre.split()), "prop": x["prop"], "val": x["val"], "line": x["line"],
                                    "media": media, "decls": d, "ok": ok})
            start = i + 1
        elif ch == ";" and not (stack and stack[-1][0] == "rule"):
            start = i + 1  # an at-statement (@import ...;)
        i += 1
    return out


def _ok_at(text, comments, sel, a0, b0):
    """griff-ok "at the rule": a comment in its body, trailing on the line of its closing brace, or on the line(s) right
    before its selector (a comment that starts its own line, only blanks up to the selector)."""
    for a, b, c in comments:
        if not GRIFF_OK.search(c):
            continue
        if a0 <= a < b0:
            return True
        if a > b0 and "\n" not in text[b0:a]:
            return True
        if b <= sel and not text[b:sel].strip() and not text[text.rfind("\n", 0, a) + 1:a].strip():
            return True
    return False


def _decls(clean, a, b, into, lineno):
    depth, s = 0, a
    for k in range(a, b + 1):
        ch = clean[k] if k < b else ";"
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == ";" and depth <= 0:
            part = clean[s:k]
            if ":" in part:
                prop, val = part.split(":", 1)
                prop = prop.strip().lower()
                if prop and re.fullmatch(r"-?[a-z][a-z0-9-]*", prop):
                    off = s + len(part) - len(part.lstrip())
                    into.append({"prop": prop, "val": " ".join(val.replace("!important", "").split()), "line": lineno(off)})
            s = k + 1


def _split_top(val: str) -> list[str]:
    out, depth, cur = [], 0, []
    for ch in val:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == " " and depth == 0:
            if cur:
                out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur))
    return [x for x in out if x and not x.startswith("[")]  # line names [a] are no tracks


def _fallback_of(v: str, at: int) -> tuple[str, str, int]:
    """var( at offset at: (name, fallback or '', end offset)"""
    depth, k = 0, at
    while k < len(v):
        if v[k] == "(":
            depth += 1
        elif v[k] == ")":
            depth -= 1
            if depth == 0:
                break
        k += 1
    inner = v[at + 4:k]
    name, _c, fb = inner.partition(",")
    return name.strip(), fb.strip(), k + 1


def size_of(v: str):
    """The fixed size a value stands for: ('grip', 0) reads a grip's variable, ('var', name) a variable without a fallback,
    ('len', rem) the largest length in it, ('none', 0) nothing fixed (fr, %, auto, keywords)."""
    if GRIP_VAR.search(v) or any(f"var({n}" in v.replace(" ", "") for n in GRIFF_LEGACY):
        return ("grip", 0)
    # the variables: without a fallback = unknown size; with one = its fallback counts
    k = v.find("var(")
    while k >= 0:
        name, fb, end = _fallback_of(v, k)
        if not fb:
            return ("var", name)
        v = v[:k] + fb + v[end:]
        k = v.find("var(")
    best = 0.0
    for num, unit in LEN.findall(v):
        n = float(num) / (16 if unit == "px" else 1)
        best = max(best, n)
    return ("len", best) if best else ("none", 0)


def _fixed(track: str):
    """a track that is fixed (not growing): ('var', name) / ('len', rem) / None. minmax(a, b): b decides (an fr max grows)."""
    t = track.strip()
    if "fr" in re.sub(r"var\([^)]*\)", "", t) and re.search(r"\d*\.?\d+fr\b", t):
        return None
    if t in ("auto", "min-content", "max-content") or t.endswith("%"):
        return None
    m = re.match(r"minmax\((.*)\)$", t)
    if m:
        parts = _split_comma(m.group(1))
        if len(parts) == 2:
            t = parts[1]
            if re.search(r"\d*\.?\d+fr\b", t) or t.strip() in ("auto", "max-content"):
                return None
    kind, x = size_of(t)
    if kind == "var":
        return ("var", x)
    if kind == "len" and x >= GRIFF_MIN_REM:
        return ("len", x)
    return None


def _split_comma(s: str) -> list[str]:
    out, depth, cur = [], 0, []
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur).strip())
    return out


def _phone_only(media: list[str]) -> bool:
    for p in media:
        if p.startswith("@media") and "min-width" not in p:
            m = PHONE_MQ.search(p)
            if m and float(m.group(1)) * (1 if m.group(2) == "px" else 16) <= 767:
                return True
    return False


def _say(fx) -> str:
    return f"a variable without a fallback ({fx[1]})" if fx[0] == "var" else f"{fx[1]:g}rem"


def finding(d: dict) -> str | None:
    """Why declaration d is red, or None."""
    if d["ok"] or _phone_only(d["media"]):
        return None
    sel, prop, val = d["sel"], d["prop"], d["val"]
    if re.search(r"\.modal\b.*\.card\b", sel):
        return None
    if size_of(val)[0] == "grip":
        return None
    if prop == "grid-template-columns":
        if re.search(r"auto-(fill|fit)", val):
            return None
        tracks = _split_top(val)
        if len(tracks) < 2 or not any(re.search(r"\d*\.?\d+fr\b", t) for t in tracks):
            return None
        for t in tracks:
            fx = _fixed(t)
            if fx:
                return f"a fixed column ({_say(fx)}) beside a growing one"
        return None
    if prop in ("flex", "flex-basis"):
        parts = _split_top(val)
        basis = parts[2] if prop == "flex" and len(parts) == 3 and parts[:2] == ["0", "0"] else val if prop == "flex-basis" else None
        fx = _fixed(basis) if basis else None
        return f"a fixed flex column ({_say(fx)})" if fx else None
    if prop in ("width", "height"):
        floating = d["decls"].get("position", "").split()[:1] in (["fixed"], ["absolute"]) or GRIFF_FLOAT_SEL.search(sel)
        if not floating or "::" in sel:  # a pseudo element is decoration, no window
            return None
        kind, x = size_of(val)  # a variable here is mostly measured by the code (bars, overlays): only a written size counts
        if kind == "len" and x >= GRIFF_MIN_REM:
            return f"a floating box with a fixed {prop} ({x:g}rem)"
    return None


def key(d: dict) -> tuple:
    """what makes a declaration the same one in another place (a rule moved unchanged is not new)"""
    return (d["sel"], d["prop"], d["val"], tuple(" ".join(m.split()) for m in d["media"]))


def findings(text: str) -> list[tuple[int, str, str, str]]:
    """[(line, selector, 'prop: value', why)] of a whole file"""
    return [(d["line"], d["sel"], f"{d['prop']}: {d['val']}", w) for d in parse(text) if (w := finding(d))]


def new_findings(base_texts: dict[str, str], head_texts: dict[str, str], added: dict[str, set[int]]) -> list[str]:
    """The findings a change brings: a declaration on an added line of the head whose rule is not in the base of any changed
    CSS file (moved unchanged = not new)."""
    old = {key(d) for t in base_texts.values() for d in parse(t)}
    out = []
    for path, text in sorted(head_texts.items()):
        lines = added.get(path, set())
        for d in parse(text):
            if d["line"] in lines and key(d) not in old and (w := finding(d)):
                out.append(f"{path}:{d['line']} {d['sel'][:80]} {{{d['prop']}: {d['val'][:80]}}}: {w} - Why: {WHY}. Instead: {INSTEAD}.")
    return out


def main(argv=None) -> int:
    paths = argv if argv is not None else sys.argv[1:]
    if not paths:
        print(__doc__)
        return 2
    n = 0
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line, sel, decl, why in findings(f.read()):
                print(f"{p}:{line} {sel[:80]} {{{decl[:80]}}}: {why}")
                n += 1
    print(f"griff_lint: {n} finding(s)")
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
