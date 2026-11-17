"""2.122.0 (#2100): the documents list as a CSV (";" and decimal comma in German, UTF-8 with BOM, like the other table exports).

POST /api/docs/export.csv {ids: [...]}: only documents the signed-in person may see (the others are left out silently);
amounts are opened like in the detail answer. Text a spreadsheet would run as a formula gets a "'" in front.
2.1324.0 (#6589): no row limit any more (was 2000, cut silently): the rows are read one by one into a spooled file
(core/serializers.py csv_download); the rate limit stays."""
import re

from flask import request

from ..core.config import app
from ..core.db import db
from ..core.i18n import dec_comma, lang, tr
from ..core.serializers import csv_download
from ..core.access import Denied
from ..accounts.session import me
from ..files.store import need_node
from . import store as S
from .web import _no_agent, doc_json
from ..api.common import hit_limit  # 2.149.0 G (#2517): pulled up from functions

_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")


def dcx_cell(v):
    v = str(v if v is not None else "")
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") and not _NUM.fullmatch(v) else v


def dcx_rows(c, ids, de):
    """[cell, ...] of each visible document among ids, in the order given (a generator: one document read at a time)."""
    for nid in ids:
        try:
            n = need_node(c, nid)
            m = S.meta_row(c, nid)
        except Denied:
            continue
        if not m or n["kind"] != "file":
            continue
        d = doc_json(c, m, n)
        amount = d["amount"] or ""
        if de:
            amount = amount.replace(".", ",")
        yield [d["date"] or "", (d["created_at"] or "")[:10], d.get("title") or re.sub(r"\.[A-Za-z0-9]{1,5}$", "", d["name"] or ""),  # 2.750.0 (#4876): the own title
               (d["sender"] or {}).get("name") or "", (d["type"] or {}).get("name") or "",
               ", ".join(t["name"] if isinstance(t, dict) else str(t) for t in d["tags"]), amount, d["currency"] or "",
               (d["folder"] or {}).get("name") or "", d["name"] or "", tr("Yes") if d["review"] else ""]


@app.post("/api/docs/export.csv")
def docs_export_csv():
    """{ids: [document ids]} -> the CSV of the documents the account may see."""
    _no_agent()
    b = request.get_json(silent=True) or {}
    ids = [int(x) for x in (b.get("ids") or []) if str(x).isdigit()] if isinstance(b.get("ids"), list) else []
    ids = list(dict.fromkeys(ids))  # 2.1324.0 (#6589): every id (was [:2000])
    if hit_limit(f"docs-csv:{me()}", 6):
        raise Denied(429)
    c = db()
    de = dec_comma(lang())
    head = [tr("Date"), tr("Received"), tr("Title"), tr("Sender"), tr("Type"), tr("Tags"), tr("Amount"), tr("Currency"), tr("Folder"),
            tr("File name"), tr("To review")]
    return csv_download(head, ([dcx_cell(x) for x in row] for row in dcx_rows(c, ids, de)), "documents.csv", ";" if de else ",")
