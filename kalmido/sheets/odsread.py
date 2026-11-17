"""2.1324.0 (#6709): the OpenDocument spreadsheet (.ods, LibreOffice / OpenOffice) import.

An .ods is a ZIP with the entry "mimetype" = application/vnd.oasis.opendocument.spreadsheet (recognised by that entry, not by
its first bytes "PK" -- an .xlsx starts the same way). It is read like an .xlsx (sheets/io.py shx_read_xlsx_all) into the same
ShxGrid per sheet, so shb_import / shx_import take it unchanged:
  - every visible sheet (at most `most`, SHB_TABS_MAX) becomes a sheet of ONE table (references between them keep working)
  - values with their kind (float / percentage / currency / date / boolean / string), formulas from table:formula (OpenFormula
    "of:=SUM([.A1:.A3])" turned into the Excel form the xlsx path reads; what cannot be turned stays its value and is counted
    in the report), list validations (cell-content-is-in-list, inline or a range of a sheet) -> select columns, merged cells
    (number-columns-spanned / number-rows-spanned), single-cell named ranges -> cell names
  - repeated cells and rows (number-columns-repeated / number-rows-repeated) are rolled out only when they hold something:
    the empty repeats LibreOffice writes up to column 1024 / row 1 048 576 only move the position. A filled repeat is checked
    against the row limit and the filled-cell budget BEFORE it is rolled out; columns beyond SH_COLS_MAX are left out and
    counted (cols_cut, #6589).
Safety as for the .xlsx reader: zip_guard before zipfile, at most 2000 entries, content.xml read by core/safexml.py in pieces
(no DOCTYPE / ENTITY anywhere, no NUL, depth limit, size budget SHX_UNZIPPED_MAX), every read element leaves the tree once used
(at most XL_TREE_MAX elements held between two rows), one of the xl_slot places. Cell styles (bold, colours) are not taken over.
2.1324.0 (#6709, Fable F2): the work is bounded for every sheet, also hidden ones and those beyond `most`: a list validation's
range is one entry per column (however many validations point at it), it is filled at most once per column and row, only within
its rows and up to ODS_CAPT_MAX labels; every row and cell read and every filled cell of a sheet not taken (times its repeats)
counts against ODS_WORK_MAX -- above it a clean 400 instead of a thread bound for hours.
"""
import io
import re
import zipfile
import zlib
from datetime import date
from xml.etree import ElementTree as ET

from ..core import safexml
from ..core.errors import BadInput
from ..core.i18n import tr
from ..core.zipread import zip_guard
from ..office.homecur import hc_code
from ..office.legacyimport import XL_CHUNK, XL_DEPTH_MAX, XL_TREE_MAX, _col_index, xl_slot
from .core import SH_COLS_MAX, SH_ROWS_MAX

ODS_MIME = (b"application/vnd.oasis.opendocument.spreadsheet", b"application/vnd.oasis.opendocument.spreadsheet-template")
ODS_COLS_SEEN = 1 << 14  # columns looked at for the "left out" count (LibreOffice has 16 384)
ODS_SPACES_MAX = 1000  # <text:s text:c="..."/>: spaces at most
ODS_CAPT_MAX = 1000  # labels read for one list validation range (sheet, column)
ODS_WORK_MAX = 10_000_000  # rows / cells read + labels taken + filled cells of sheets not taken (with their repeats), all sheets
_T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_O = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
_X = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
_S = "{urn:oasis:names:tc:opendocument:xmlns:style:1.0}"
_CALC = "{urn:org:documentfoundation:names:experimental:calc:xmlns:calcext:1.0}"
_CELL, _COVERED, _ROW, _TABLE = _T + "table-cell", _T + "covered-table-cell", _T + "table-row", _T + "table"
# one side of a reference: [$]['Sheet name' | Sheet].[$]A[$]1 (the sheet part may be empty: ".A1")
_SIDE = r"\$?(?:'((?:[^']|'')*)'|([^.'\[\]:]*))\.(\$?[A-Za-z]{1,3}\$?\d{1,7})"
_REF = re.compile(_SIDE + r"(?::" + _SIDE + r")?")


def _bad():
    return BadInput(tr("This is not a spreadsheet file (.ods)"))


def shx_is_ods(raw):
    """Is it an OpenDocument spreadsheet: a ZIP whose entry "mimetype" says so (read at most 100 bytes of it)."""
    if not raw.startswith(b"PK"):
        return False
    try:
        zip_guard(raw, 2000)
        z = zipfile.ZipFile(io.BytesIO(raw))
        if "mimetype" not in z.namelist():
            return False
        with z.open("mimetype") as fh:
            return fh.read(100).strip() in ODS_MIME
    except (zipfile.BadZipFile, ValueError, KeyError, RuntimeError, NotImplementedError, zlib.error, EOFError, OSError):
        return False


def ods_formula(f):
    """An OpenFormula text ("of:=SUM([.A1:.B2];[$Sheet2.C3])") -> the Excel form the .xlsx path reads ("SUM(A1:B2,'Sheet2'!C3)",
    no "="), or None when it has something that form cannot say (3D ranges, unions, inline arrays, a broken reference)."""
    f = (f or "").strip()
    m = re.match(r"(of|oooc|msoxl):", f)
    if m:
        if m.group(1) == "msoxl":
            return f[len(m.group(0)):].lstrip("=") or None  # already Excel's form
        f = f[len(m.group(0)):]
    if not f.startswith("="):
        return None
    f, out, i, n = f[1:], [], 0, len(f) - 1
    while i < n:
        ch = f[i]
        if ch == '"':  # a text: copied as it is ("" inside it stays)
            j = i + 1
            while j < n:
                if f[j] == '"':
                    if j + 1 < n and f[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            if j >= n:
                return None
            out.append(f[i:j + 1])
            i = j + 1
        elif ch == "[":
            j = f.find("]", i)
            if j < 0:
                return None
            ref = _ods_ref(f[i + 1:j])
            if ref is None:
                return None
            out.append(ref)
            i = j + 1
        elif ch == ";":
            out.append(",")
            i += 1
        elif ch in "~!{}|":  # union, intersection, inline arrays: no Excel form here
            return None
        else:
            out.append(ch)
            i += 1
    s = "".join(out)
    s = re.sub(r"\b(TRUE|FALSE)\(\s*\)", r"\1", s, flags=re.I)
    s = re.sub(r"\bCOM\.MICROSOFT\.", "", s, flags=re.I)
    return s or None


def _ods_ref(ref):
    """The inside of [...]: ".A1", "$Sheet2.$A$1:.$B$3", "'My sheet'.A1" -> "A1", "'Sheet2'!$A$1:$B$3", "'My sheet'!A1"."""
    m = _REF.fullmatch(ref.strip())
    if not m:
        return None
    sh1 = m.group(1).replace("''", "'") if m.group(1) is not None else (m.group(2) or "")
    a = m.group(3)
    if m.group(6):
        sh2 = m.group(4).replace("''", "'") if m.group(4) is not None else (m.group(5) or "")
        if sh2 and sh2 != sh1:
            return None  # a range over several sheets
        a += ":" + m.group(6)
    if not sh1:
        return a
    return "'" + sh1.replace("'", "''") + "'!" + a


def _addr(ref):
    """One cell or range address of an attribute ("$Sheet1.$B$2" / "Sheet1.A1:Sheet1.A5") -> (sheet, c1, r1, c2, r2) or None."""
    m = _REF.fullmatch((ref or "").strip())
    if not m:
        return None
    sh = m.group(1).replace("''", "'") if m.group(1) is not None else (m.group(2) or "")
    a1 = re.fullmatch(r"\$?([A-Za-z]{1,3})\$?(\d{1,7})", m.group(3))
    a2 = re.fullmatch(r"\$?([A-Za-z]{1,3})\$?(\d{1,7})", m.group(6)) if m.group(6) else a1
    return sh, _col_index(a1.group(1).upper()), int(a1.group(2)), _col_index(a2.group(1).upper()), int(a2.group(2))


def _validation(el):
    """A <table:content-validation> -> [labels] | ("rng", sheet, col, row1, row2) | None (not a list)."""
    cond = el.get(_T + "condition") or ""
    cond = re.sub(r"^(of|oooc):", "", cond.strip())
    m = re.fullmatch(r"cell-content-is-in-list\((.*)\)", cond, flags=re.S)
    if not m:
        return None
    inner = m.group(1).strip()
    if inner.startswith('"'):
        return [x.replace('""', '"').strip() for x in re.findall(r'"((?:[^"]|"")*)"', inner) if x.strip()][:100]
    if inner.startswith("[") and inner.endswith("]"):
        a = _addr(inner[1:-1])
        if not a:
            return None
        sh, c1, r1, c2, r2 = a
        if not sh:
            base = _addr(el.get(_T + "base-cell-address") or "")
            sh = base[0] if base else ""
        if c1 != c2 or r2 < r1 or r2 - r1 > 200:
            return None
        return ("rng", sh, c1, r1, r2)
    return None


def _text(cell):
    """The text of a cell: its paragraphs one per line; <text:s c="n"/>, tabs and line breaks as characters."""
    out = []

    def walk(el):
        if el.text:
            out.append(el.text)
        for ch in el:
            tag = ch.tag
            if tag == _X + "s":
                try:
                    out.append(" " * max(1, min(int(ch.get(_X + "c") or 1), ODS_SPACES_MAX)))
                except ValueError:
                    out.append(" ")
            elif tag == _X + "tab":
                out.append("\t")
            elif tag == _X + "line-break":
                out.append("\n")
            elif tag not in (_O + "annotation",):
                walk(ch)
            if ch.tail:
                out.append(ch.tail)

    paras = []
    for p in cell:
        if p.tag in (_X + "p", _X + "h"):
            out.clear()
            walk(p)
            paras.append("".join(out))
    return "\n".join(paras)


def _num(v):
    v = (v or "").strip()
    if re.fullmatch(r"-?\d+\.0+", v):
        return v.split(".")[0]
    if re.fullmatch(r"-?\d+(\.\d+)?[eE][-+]?\d+", v):
        try:
            x = float(v)
            return str(int(x)) if x.is_integer() and abs(x) < 1e15 else repr(x)
        except (ValueError, OverflowError):
            return v
    return v


def _cell(el):
    """A <table:table-cell> -> {v, f, fmt, num[, nf]} or None when it holds nothing (no value, no formula)."""
    vt = el.get(_O + "value-type") or el.get(_CALC + "value-type")
    raw_f = el.get(_T + "formula")
    f = None
    if raw_f:
        f = ods_formula(raw_f) or "\x00ods"  # "\x00...": kept as its value (shx_kalmido_formula), counted in the report
    fmt, num, nf = None, False, None
    if vt in ("float", "percentage", "currency"):
        v, num = _num(el.get(_O + "value")), True
        if vt == "percentage":
            fmt = "percent"
        elif vt == "currency":
            fmt = "currency"
            cur = hc_code((el.get(_O + "currency") or "")[:8])
            nf = (None, cur) if cur else None
        if not v:
            v, num = _text(el), False
    elif vt == "date":
        dv = (el.get(_O + "date-value") or "")[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", dv):
            try:
                v, fmt = date.fromisoformat(dv).isoformat(), "date"
            except ValueError:
                v = _text(el)
        else:
            v = _text(el)
    elif vt == "boolean":
        b = (el.get(_O + "boolean-value") or "").strip().lower()
        v = "WAHR" if b in ("true", "1") else "FALSCH" if b in ("false", "0") else _text(el)
    elif vt == "string":
        v = el.get(_O + "string-value")
        v = _text(el) if v is None else v
    else:  # time, void, none: what the cell shows
        v = _text(el)
    if not v and not f:
        return None
    out = {"v": v or "", "f": f, "fmt": fmt, "num": num}
    if nf:
        out["nf"] = nf
    return out


def _int(el, attr, most):
    try:
        return max(1, min(int(el.get(attr) or 1), most))
    except ValueError:
        return 1


def shx_read_ods_all(raw, most):
    """Every visible sheet of an .ods (at most `most`) -> [ShxGrid] with .sheet_name / .n_sheets (like shx_read_xlsx_all)."""
    with xl_slot():
        return _ods_all(raw, most)


def _ods_all(raw, most):
    from .io import SHX_CELLS_MAX, SHX_STORED_MAX, SHX_UNZIPPED_MAX, ShxGrid, _shx_too_many
    try:
        zip_guard(raw, 2000)
        z = zipfile.ZipFile(io.BytesIO(raw))
        names = set(z.namelist())
    except (zipfile.BadZipFile, ValueError):
        raise _bad() from None
    if "content.xml" not in names or len(names) > 2000:
        raise _bad()
    try:
        return _read(z, most, ShxGrid, _shx_too_many, SHX_CELLS_MAX, SHX_STORED_MAX, SHX_UNZIPPED_MAX)
    except BadInput:
        raise
    except (ET.ParseError, KeyError, ValueError, IndexError, zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, NotImplementedError):
        raise _bad() from None


def _events(z, budget_max):
    info = z.getinfo("content.xml")
    if info.file_size > budget_max:
        raise BadInput(tr("The file is too large"))

    def pieces():
        with z.open("content.xml") as fh:  # ZipExtFile reads at most file_size bytes
            while True:
                chunk = fh.read(XL_CHUNK)
                if not chunk:
                    return
                yield chunk

    try:
        yield from safexml.sx_events(pieces(), max_bytes=info.file_size + 1, max_depth=XL_DEPTH_MAX)
    except safexml.XmlRefused:
        raise _bad() from None


def _read(z, most, ShxGrid, too_many, cells_max, stored_max, unzipped_max):
    hidden_styles, valid, names = set(), {}, []
    need = {}  # sheet name -> {col: [row1, row2]} of list validations' ranges (one per column: the rows they span together)
    cap = {}  # (sheet, col) -> {row: label}
    grids, n_visible = [], 0
    full = [0]  # filled cells of all kept sheets
    work = [0]  # ODS_WORK_MAX: what reading costs, over all sheets
    open_, n = [], 0
    in_cell = 0  # open cells: what is inside one (text, a table inside a cell) is kept until the cell ends
    t = None  # the sheet being read: dict(name, grid | None, cells, r, c, row, vals, capt, cut)

    def kept():
        return t is not None and t["grid"] is not None

    for ev, el in _events(z, unzipped_max):
        if ev == "start":
            tag = el.tag
            if tag in (_CELL, _COVERED) and t is not None:
                in_cell += 1
            if in_cell:
                pass
            elif tag == _TABLE and t is None:
                nm = (el.get(_T + "name") or "")[:200]
                hid = (el.get(_T + "style-name") or "") in hidden_styles
                g = None
                if not hid:
                    n_visible += 1
                    if n_visible <= most:
                        g = ShxGrid()
                        g.sheet_name = nm
                t = {"name": nm, "grid": g, "cells": {}, "r": 0, "c": 0, "row": [], "capt": [], "vals": {}, "seen": 0}
            elif tag == _ROW and t is not None:
                t["c"], t["row"], t["capt"], t["seen"] = 0, [], [], 0
            open_.append(el)
            continue
        open_.pop()
        parent = open_[-1] if open_ else None
        tag = el.tag
        n += 1
        if n > XL_TREE_MAX:  # a cell / row with endless children, or anything else between rows
            raise BadInput(tr("The file is too large"))
        if tag in (_CELL, _COVERED) and t is not None:
            in_cell -= 1
            if in_cell:
                continue  # a cell of a table inside a cell: part of the outer cell
            if parent is not None and parent.tag == _ROW:
                _take_cell(el, t, kept(), need, full, work, cells_max, too_many)
            el.clear()
            if parent is not None:
                parent.remove(el)
            continue
        if in_cell:
            continue  # inside a cell: kept until the cell ends (counted in n)
        if tag == _ROW and t is not None:
            _take_row(el, t, kept(), need, cap, full, work, cells_max, stored_max, too_many)
            el.clear()
            if parent is not None:
                parent.remove(el)
            n = 0
            continue
        if tag == _TABLE and t is not None:
            if kept():
                g = t["grid"]
                cells = t["cells"]
                if cells:
                    h = max(k[0] for k in cells)
                    last = {}
                    for (r, ci) in cells:
                        last[r] = max(last.get(r, -1), ci)
                    from .io import _SHX_EMPTY
                    g.rows = [[cells.get((r, ci)) or _SHX_EMPTY for ci in range(last.get(r, -1) + 1)] for r in range(1, h + 1)]
                g.n_filled = full[0]
                g._vals = t["vals"]
                grids.append(g)
            t = None
            el.clear()
            if parent is not None:
                parent.remove(el)
            n = 0
            continue
        if tag == _S + "style":
            if (el.get(_S + "family") == "table"
                    and any(x.tag == _S + "table-properties" and x.get(_T + "display") == "false" for x in el)):
                hidden_styles.add(el.get(_S + "name") or "")
        elif tag == _T + "content-validation":
            v = _validation(el)
            nm = el.get(_T + "name") or ""
            if v is not None and nm and len(valid) < 10_000:
                valid[nm] = v
                if isinstance(v, tuple):
                    span = need.setdefault(v[1], {}).setdefault(v[2], [v[3], v[4]])
                    span[0], span[1] = min(span[0], v[3]), max(span[1], v[4])
        elif tag == _T + "named-range" and len(names) < 10_000:
            a = _addr(el.get(_T + "cell-range-address") or "")
            nm = el.get(_T + "name") or ""
            if a and nm and a[1:3] == a[3:5]:
                names.append((nm, a[0] or (t["name"] if t else ""), a[2] - 1, a[1]))
        if parent is not None and parent.tag not in (_S + "style", _T + "content-validation"):
            el.clear()
            parent.remove(el)
    if not grids:
        raise _bad()
    for g in grids:
        g.n_sheets = n_visible
        for ci, vn in g._vals.items():
            v = valid.get(vn)
            if isinstance(v, tuple):
                got = cap.get((v[1], v[2]), {})
                v = [got[r] for r in sorted(got) if v[3] <= r <= v[4]][:100]
            if v and ci < SH_COLS_MAX:
                g.lists.setdefault(ci, v)
        del g._vals
        for nm, sh, r, ci in names:
            if sh == g.sheet_name and r >= 0 and ci < SH_COLS_MAX:
                g.names.setdefault(nm, (r, ci))
    if sum(1 for g in grids for r in g.rows for x in r if (x.get("v") or "") != "" or x.get("f")) > cells_max:
        raise too_many()
    return grids


def _spend(work, k):
    work[0] += k
    if work[0] > ODS_WORK_MAX:
        raise BadInput(tr("The file is too large"))


def _take_cell(el, t, keep, need, full, work, cells_max, too_many):
    """One cell of the current row: rolled out over its repeats when it holds something, else only the position moves."""
    _spend(work, 1)
    rep = _int(el, _T + "number-columns-repeated", 1 << 30)
    c = t["c"]
    t["c"] = c + rep
    if el.tag == _COVERED:
        return
    x = _cell(el)
    vn = el.get(_T + "content-validation-name")
    if keep and vn:
        for ci in range(c, min(c + rep, SH_COLS_MAX)):
            t["vals"].setdefault(ci, vn)
    if x is None:
        return
    t["seen"] += min(rep, ODS_COLS_SEEN)  # filled cells of this row (a sheet not taken: counted with the row's repeats)
    cols = need.get(t["name"])
    if cols and x["v"]:  # a list validation reads its labels from here: once per column (columns of a row do not overlap)
        if rep <= len(cols):
            hit = [ci for ci in range(c, c + rep) if ci in cols]
        else:
            hit = [ci for ci in cols if c <= ci < c + rep]
        _spend(work, min(rep, len(cols)))
        t["capt"].extend((ci, x["v"]) for ci in hit)
    if not keep:
        return
    cs, rs = _int(el, _T + "number-columns-spanned", 1 << 14), _int(el, _T + "number-rows-spanned", 1 << 20)
    if (cs > 1 or rs > 1) and c < SH_COLS_MAX:
        g = t["grid"]
        if len(g.merges) < cells_max:
            g.merges.append((t["r"] + 1, c, t["r"] + rs, c + cs - 1))
        else:
            g.fmt_left_out += 1
    if c + rep > SH_COLS_MAX:
        g = t["grid"]
        lo, hi = max(c, SH_COLS_MAX), min(c + rep, ODS_COLS_SEEN)
        # 2.1324.0 (#6709, review F1 of the second reader): no free per-column loop per cell any more. While the columns left out
        # are one gapless block [SH_COLS_MAX, top) only what lies beyond top is added (a row like the one before costs nothing);
        # otherwise the columns are added in one step. Every column added counts against ODS_WORK_MAX.
        top = t.get("cut_top", SH_COLS_MAX)
        block = len(g.cols_cut) == top - SH_COLS_MAX
        if block and lo <= top:
            lo = top
        if hi > lo:
            _spend(work, hi - lo)
            g.cols_cut.update(range(lo, hi))
            t["cut_top"] = max(top, hi)
    take = max(0, min(c + rep, SH_COLS_MAX) - c)
    if take:
        full[0] += take
        if full[0] > cells_max + SH_COLS_MAX:
            raise too_many()
        for ci in range(c, c + take):
            t["row"].append((ci, x))


def _take_row(el, t, keep, need, cap, full, work, cells_max, stored_max, too_many):
    """The current row: its cells into the sheet once per repeat; an empty row (also repeated a million times) only moves on."""
    _spend(work, 1)
    rep = _int(el, _T + "number-rows-repeated", 1 << 30)
    r0 = t["r"]
    t["r"] = r0 + rep
    if t["capt"]:
        cols = need[t["name"]]
        for col, v in t["capt"]:
            span = cols.get(col)
            if span is None:
                continue
            got = cap.setdefault((t["name"], col), {})
            lo = max(r0 + 1, span[0])
            hi = min(r0 + rep, span[1], lo + ODS_CAPT_MAX - len(got) - 1)
            _spend(work, 1 + max(0, hi - lo + 1))
            v = v.strip()
            for r in range(lo, hi + 1):
                got[r] = v
            if len(got) >= ODS_CAPT_MAX or r0 + rep >= span[1]:
                del cols[col]  # full, or its rows are behind: nothing more to read for it
    if not keep:
        if t["seen"] and rep > 1:
            _spend(work, t["seen"] * (rep - 1))
        return
    row = t["row"]
    if not row:
        return
    if r0 + rep > SH_ROWS_MAX + 1:
        raise BadInput(tr("Too many rows (at most {0})", SH_ROWS_MAX))
    if rep > 1:  # checked BEFORE the repeats are rolled out
        full[0] += len(row) * (rep - 1)
        if full[0] > cells_max + SH_COLS_MAX:
            raise too_many()
    cells = t["cells"]
    if len(cells) + len(row) * rep > stored_max:
        raise too_many()
    for k in range(rep):
        for ci, x in row:
            cells[(r0 + 1 + k, ci)] = x if k == 0 else dict(x)
