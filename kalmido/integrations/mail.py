"""Tasks by e-mail (IMAP) and the daily summary by e-mail (SMTP)."""
import email.message
import email.parser
import email.policy
import email.utils
import hashlib
import hmac
import html
import imaplib
import os
import re
import secrets
import smtplib
import threading
import time
from datetime import date, timedelta
from flask import g, jsonify, request

from ..core.config import app, APP_NAME, MAX_FILE_MB, PUBLIC_URL
from ..core.pg import insert_id, system_ctx, table_exists
from ..core.i18n import browser_lang, lang, md_plain, tr, trn
from ..core.db import body, bump, connect, db, err, inbox_default, iso, local_now, now_utc, uset, usettings
from ..accounts.session import GATE, me
from ..accounts.mailtok import mtk_new, mtk_plain, mtk_where  # 2.674.0 (#4382 finding 5)
from ..accounts.bgjobs import bgj_fn
from ..core.access import list_role, need_list, vis_sql, WRITE_ROLES, list_state_sql
from ..core.pages import new_inbox_task, save_attachment_bytes, split_link, valid_url
from ..tasks.validation import as_int, log_act
from ..collab.news import news_unread
from ..collab.integfail import integ_tell  # 2.1269 (#6386)
from ..accounts.users import need_admin
from ..notify.alerts import aa_count, aa_err, aa_fail, aa_ok
from ..agents.core import agent_added_events, agent_comment_events, need_person  # 2.553.0 B (#3460): the events also for integrations/reqmail.py
from ..collab.teamchat import tchat_unread
from ..core.env import env_bool
from ..core.mailframe import MAIL_ACC, Safe, mail_html  # noqa: F401  2.420.0 B (#3499): the one mail frame (re-exported here)
from ..api.common import hit_limit  # 2.149.0 G (#2517): pulled up from functions
from ..collab.liste2eguard import le2b_net, le2b_list_locked, le2b_off  # 2.369.5 (#2517): pulled up from functions
from ..accounts.login import auth_key  # 2.369.5 (#2517): pulled up from functions
from ..accounts.session import rate_ip  # 2.369.5 (#2517): pulled up from functions
from ..collab.comments import lang_of  # 2.369.5 (#2517): pulled up from functions
from ..lists.public import pub_html  # 2.369.5 (#2517): pulled up from functions
from .mailtrim import md_trim_forward  # 2.369.5 (#2517): pulled up from functions
from ..calendars.subscriptions import _cal_connector  # 2.369.5 (#2517): pulled up from functions
from ..core.mailguard import MailRefused, mail_parse, mail_precheck  # 2.1281.0 (#6425)


# ---------------------------------------------------------------- 2.17.0 (#443): tasks by e-mail + the daily summary by e-mail
# In: one mailbox the admin sets up (KALMIDO_IMAP_*), polled every KALMIDO_IMAP_INTERVAL seconds. Every person gets a
# personal address with a secret token (plus addressing: tasks+<token>@example.com -> their inbox) and may make one per
# list (-> that list, while they may change it). Subject = title, the text = the description, attachments = files (the
# usual size limit), "Fwd:" / "WG:" prefixes are dropped. Optionally (setting mail_from_me) mails FROM the person's own
# e-mail address to the plain address land in their inbox too (sender addresses can be forged: off by default).
# Read mails are marked \Seen and never imported twice (Message-ID); 2.240.0 A (#2883): once taken in (or dropped as for
# nobody) they are deleted from the mailbox (KALMIDO_IMAP_KEEP=1: only marked \Seen). Out: KALMIDO_SMTP_* sends the daily summary (digest
# time of the push, setting digest_mail) to the person's e-mail address.
MAIL_ADDRESS = os.environ.get("KALMIDO_MAIL_ADDRESS", "").strip()
IMAP = {"host": os.environ.get("KALMIDO_IMAP_HOST", "").strip(), "port": int(os.environ.get("KALMIDO_IMAP_PORT", "0") or 0),
        "user": os.environ.get("KALMIDO_IMAP_USER", "").strip(), "password": os.environ.get("KALMIDO_IMAP_PASSWORD", ""),
        "folder": os.environ.get("KALMIDO_IMAP_FOLDER", "INBOX").strip() or "INBOX",
        "ssl": env_bool("KALMIDO_IMAP_SSL", True),
        "interval": max(10, int(os.environ.get("KALMIDO_IMAP_INTERVAL", "60") or 60))}
SMTP = {"host": os.environ.get("KALMIDO_SMTP_HOST", "").strip(), "port": int(os.environ.get("KALMIDO_SMTP_PORT", "0") or 0),
        "user": os.environ.get("KALMIDO_SMTP_USER", "").strip(), "password": os.environ.get("KALMIDO_SMTP_PASSWORD", ""),
        "tls": (os.environ.get("KALMIDO_SMTP_TLS", "starttls").strip().lower() or "starttls"),
        "from": os.environ.get("KALMIDO_MAIL_FROM", "").strip() or MAIL_ADDRESS}
IMAP_KEEP = env_bool("KALMIDO_IMAP_KEEP", False)  # 2.240.0 A (#2883)
SMTP_INSECURE = env_bool("KALMIDO_SMTP_INSECURE", False)  # 2.240.0 A (#2883): admin SMTP/IMAP without a certificate check
MAIL_IN_ON = bool(MAIL_ADDRESS and IMAP["host"] and IMAP["user"])
MAIL_OUT_ON = bool(SMTP["host"] and SMTP["from"])
if SMTP_INSECURE and (MAIL_IN_ON or MAIL_OUT_ON):
    print("mail: WARNING KALMIDO_SMTP_INSECURE=1: the certificate of the admin mail server is not checked", flush=True)
MAIL_TOKEN_RE = re.compile(r"\+([A-Za-z0-9_-]{10,40})@")
MAIL_BODY_MAX, MAIL_PREFIX_RE = 20000, re.compile(r"^\s*((fwd?|wg|aw|re|tr|rv|fw|doorst|antw)\s*:\s*)+", re.I)


def mail_addr(token):
    local, _, dom = MAIL_ADDRESS.partition("@")
    return f"{local}+{token}@{dom}" if token and dom else ""


def mail_tokens(c, uid):
    return {r["list_id"]: mtk_plain(c, r["token"]) for r in c.execute("SELECT * FROM mail_tokens WHERE user_id=?", (uid,))}


@app.get("/api/me/mail")
def mail_info():
    """My e-mail addresses for new tasks (personal = inbox, per list), the daily summary by mail."""
    c = db()
    uid = me()
    s = usettings(c, uid)
    toks = mail_tokens(c, uid)
    lists = []
    for lid, t in toks.items():
        if lid is None:
            continue
        l = c.execute("SELECT id, name, e2e FROM lists WHERE id=?", (lid,)).fetchone()
        if l and list_role(c, lid) in WRITE_ROLES:
            if l["e2e"]:  # 2.64.1 B (#1817): the address is off in a list with the lock (the dialog shows why)
                lists.append({"list_id": lid, "name": l["name"], "address": "", "e2e": True, "reason": le2b_off()})
                continue
            lists.append({"list_id": lid, "name": l["name"], "address": mail_addr(t)})
    u = c.execute("SELECT email, email_proved FROM users WHERE id=?", (uid,)).fetchone()
    em = ((u["email"] if u else "") or "").strip()
    return jsonify(enabled=MAIL_IN_ON, address=mail_addr(toks.get(None)) if MAIL_IN_ON else "", plain=MAIL_ADDRESS if MAIL_IN_ON else "",
                   lists=lists if MAIL_IN_ON else [], from_me=s.get("mail_from_me") == "1",
                   trim_fwd=s.get("mail_trim_fwd") == "1", trim_eml=s.get("mail_trim_eml") != "0",  # 2.49.0 (#971)
                   # 2.1033.0 (#5790): the own address again (a comment had swallowed it since 2.49.0: "none set" / no "Send now"),
                   # and whether it is proved - "E-mails from my own address" counts only then (#5775)
                   email=em, email_proved=bool(u) and MAIL_PROOF["ok"](u),  # 2.1299.0 (#6352)
                   digest={"enabled": MAIL_OUT_ON, "on": s.get("digest_mail") == "1", "time": s.get("digest_time") or ""})


@app.post("/api/me/mail/token")
def mail_token_new():
    """{list_id?} -- a new address (the old one stops working): personal (inbox) or for a list I may change."""
    c = db()
    if not MAIL_IN_ON:
        return err(tr("E-mail to tasks is not set up on this server"), 409)
    need_person(403)
    lid = body().get("list_id")
    if lid is not None:
        if isinstance(lid, bool) or not isinstance(lid, int):
            return err(tr("Invalid value: {0}", "list_id"))
        need_list(c, lid)
        if le2b_list_locked(c, lid):  # 2.64.1 B (#1817): no mail address for a list with the lock
            return jsonify(error=le2b_off(), code="list_e2e"), 409
    tok = secrets.token_urlsafe(12).replace("-", "x").replace("_", "y")
    c.execute("DELETE FROM mail_tokens WHERE user_id=? AND list_id IS NOT DISTINCT FROM ?", (me(), lid))
    c.execute("INSERT INTO mail_tokens(token,token_hash,user_id,list_id,created_at) VALUES(?,?,?,?,?)",
              (*mtk_new(c, tok), me(), lid, iso(now_utc())))  # 2.674.0 (#4382 finding 5): sealed + its hash, no plain text
    c.commit()
    return jsonify(address=mail_addr(tok), list_id=lid)


@app.delete("/api/me/mail/token")
def mail_token_del():
    """?list_id= (none = the personal address) -- the address stops working."""
    c = db()
    lid = request.args.get("list_id")
    lid = as_int(lid, "list_id", 1) if lid else None
    c.execute("DELETE FROM mail_tokens WHERE user_id=? AND list_id IS NOT DISTINCT FROM ?", (me(), lid))
    c.commit()
    return jsonify(ok=True)


MAIL_DECOR_MAX = 100_000  # 2.424.0 (#3450): an inline image below this size that the HTML shows (or without a name) is decoration


def _mail_cids(msg):
    """The Content-IDs the HTML parts of a mail show (<img src="cid:...">), lower case, without angle brackets."""
    out = set()
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            try:
                out.update(m.lower() for m in re.findall(r'cid:([^"\'>\s]+)', part.get_content() or "", re.I))
            except Exception:  # noqa: BLE001
                continue
    return out


def _mail_decor(part, name, cids):
    """2.424.0 (#3450): an inline image is decoration (a logo) when it is small and the HTML shows it or it has no file
    name; a large inline photo (iPhone Mail sends receipts photographed like that) stays a file."""
    try:
        size = len(part.get_payload(decode=True) or b"")
    except Exception:  # noqa: BLE001
        size = 0
    cid = str(part.get("Content-ID", "")).strip().strip("<>").lower()
    return size < MAIL_DECOR_MAX and (not name or (cid and cid in cids))


MAIL_HTML_MAX = 2 * 1024 * 1024  # 2.519.0 B (#4378): the HTML part is cut to this before its tags go
_MAIL_HTML_NL = re.compile(r"(?i)br\s*/?|/p|/div|/li|/h\d")


def mail_html_plain(h):
    """2.519.0 B (#4378): the text of an HTML mail part in one pass (str.find, no regex over the whole part): <script> / <style>
    with their content go, <br> </p> </div> </li> </hN> become a line break, every other tag goes; the same text as the regexes
    before, but linear: a part with 100.000 <script> without an end tag (or 1 MB of "<") took minutes there and held the mail
    poll and the background gate."""
    h = h[:MAIL_HTML_MAX]
    low, out, i, n, gone = h.lower(), [], 0, len(h), set()
    while i < n:
        j = h.find("<", i)
        if j < 0:
            out.append(h[i:])
            break
        out.append(h[i:j])
        k = h.find(">", j + 1)
        if k < 0:  # no tag any more: the rest is text (as before)
            out.append(h[j:])
            break
        if k == j + 1:  # "<>" is no tag
            out.append("<")
            i = j + 1
            continue
        tag = low[j + 1:k]
        for name in ("script", "style"):
            if tag.startswith(name) and name not in gone:
                e = low.find("</" + name + ">", k + 1)
                if e < 0:
                    gone.add(name)  # no end tag after here: never searched again (a plain tag from now on)
                else:
                    k = e + len(name) + 2
                    tag = ""
                break
        if tag and _MAIL_HTML_NL.fullmatch(tag):
            out.append("\n")
        i = k + 1
    return "".join(out)


def mail_text(msg, limit=MAIL_BODY_MAX, att_images=False):
    """(text, [(name, mime, bytes)]) of an email.message.EmailMessage: text/plain preferred, else HTML without tags.
    2.84.0 (#1198): limit = characters kept (the hub files longer texts). att_images (2.424.0 B2, #3450, the documents
    mail input): an image is a file only with Content-Disposition attachment (an inline logo of an invoice mail is not)."""
    plain = html_ = None
    files = []
    cids = _mail_cids(msg) if att_images else set()
    for part in msg.walk():
        if part.is_multipart():
            continue
        disp = (part.get_content_disposition() or "").lower()
        ctype = part.get_content_type()
        name = part.get_filename()
        if att_images and ctype.startswith("image/") and disp != "attachment" and _mail_decor(part, name, cids):
            continue
        if disp == "attachment" or (name and disp != "inline") or (name and not ctype.startswith("text/")):
            try:
                data = part.get_payload(decode=True) or b""
            except Exception:  # noqa: BLE001
                data = b""
            if data:
                files.append((name or "file", ctype, data))
            continue
        try:
            txt = part.get_content()
        except Exception:  # noqa: BLE001
            continue
        if ctype == "text/plain" and plain is None:
            plain = txt
        elif ctype == "text/html" and html_ is None:
            html_ = txt
    if plain is None and html_:
        plain = html.unescape(mail_html_plain(html_))
    text = re.sub(r"\n{3,}", "\n\n", (plain or "").replace("\r\n", "\n")).strip()
    return text[:limit], files


def mail_target(c, msg):
    """(user id, list id or None, how) the mail is for, or (None, None, None): how "token" = a token in To / Cc / Delivered-To /
    X-Original-To, how "from" = (mail_from_me) the sender's address of a person who allowed that, which anyone can forge."""
    hdrs = " ".join(str(msg.get_all(h, [])) for h in ("To", "Cc", "Delivered-To", "X-Original-To", "Envelope-To"))
    for tok in MAIL_TOKEN_RE.findall(hdrs):
        w, a = mtk_where(tok)  # 2.674.0 (#4382 finding 5): by the hash (a row of an older version by the plain token)
        r = c.execute(f"SELECT * FROM mail_tokens WHERE {w}", a).fetchone()
        if r:
            u = c.execute("SELECT disabled FROM users WHERE id=?", (r["user_id"],)).fetchone()
            if not u or u["disabled"]:
                return None, None, None
            if r["list_id"] and le2b_list_locked(c, r["list_id"]):
                return None, None, None  # 2.64.1 B (#1817): a list with the lock takes no mail (like an unknown address)
            if r["list_id"] and list_role(c, r["list_id"], r["user_id"]) not in WRITE_ROLES:
                return r["user_id"], None, "token"  # no longer allowed in that list: the inbox
            return r["user_id"], r["list_id"], "token"
    sender = email.utils.parseaddr(str(msg.get("From", "")))[1].strip().lower()
    if sender:
        for r in c.execute("SELECT u.id FROM users u JOIN user_settings s ON s.user_id=u.id AND s.key='mail_from_me' AND s.value='1' "
                           "WHERE lower(u.email)=? AND u.email_proved=? AND NOT u.disabled", (sender, sender)):  # 2.1021.0 (#5775): a proved address only
            return r[0], None, "from"
    return None, None, None


MAIL_PROOF = {}  # 2.1299.0 (#6352): integrations/mailproof.py: ok(u) = a proved address (the one check), hint(c, uid) = the proof mail once per address
MAIL_TASK_HOOK = {}  # 2.393.2 B (#3375): integrations/taskmail.py (take = a reply becomes a comment, keep = store a Message-ID)


class _MailDrop:
    """2.240.0 A (#2883): an importer's answer "for nobody / already imported": falsy, but the mail may be deleted."""
    def __bool__(self):
        return False


MAIL_DROP = _MailDrop()


class _MailLater:
    """2.1322.0 (#6560 3): an importer's answer "not now" (a limit was reached): the mail goes back to unseen, its attempt
    stays open without using one up, and the next round takes it again after the new mails (mail_fetch)."""
    def __bool__(self):
        return True


MAIL_LATER = _MailLater()
_PARSED = threading.local()  # 2.1281.0 (#6425): the mail mail_fetch is at, taken apart once (the step before the transaction + the import)


def _mail_msg(raw):
    """The checked message of raw (core/mailguard.py mail_parse; raises MailRefused); the same bytes object again (mail_fetch:
    prefetch, then the import) gives the same message instead of taking the mail apart a second time."""
    if getattr(_PARSED, "raw", None) is not raw:
        _PARSED.raw, _PARSED.msg = raw, None
        try:
            _PARSED.msg = mail_parse(raw)
        except MailRefused as e:
            _PARSED.msg = e  # (refused once: the second step gets the same answer without parsing again)
    if isinstance(_PARSED.msg, MailRefused):
        raise _PARSED.msg
    return _PARSED.msg


class MailKept(int):
    """2.240.0 A (#2883): a task id whose mail stays in the mailbox (an attachment could not be stored)."""


def mail_import(c, raw, pre=None):
    """One message (bytes) -> one task. Returns the task id, MAIL_DROP when it is for nobody or already imported, None
    when another importer (documents, hub, data protection) took nothing in (2.240.0 A, #2883: that mail stays).
    2.424.0 B2 (#3450): c None = the step before the database transaction (mail_fetch prefetch): the invoice link
    downloads of a documents mail -> pre, handed back in with the mail (docs/ingest.py docs_mail_prefetch)."""
    msg = _mail_msg(raw)  # 2.1281.0 (#6425): counted before it is taken apart (MailRefused: mail_fetch skips it for good)
    from ..docs.ingest import DocsMailKept, docs_mail_import, docs_mail_prefetch  # 2.48.0 (#1111): a document address -> its attachments become documents
    if c is None:
        return docs_mail_prefetch(msg)
    from ..office.privacy import dsb_mail_import  # 2.154.0 C (#2192): a reply with the code of a mailed data protection sheet
    p = dsb_mail_import(c, msg, raw)
    if p is not None:
        return p or None
    d = docs_mail_import(c, msg, raw, pre)
    if d is not None:
        if isinstance(d, DocsMailKept):  # 2.1281.0 (#6425): files left out by the mail's budget: the mail is not deleted
            return MailKept(d)
        return d or None
    from ..hub.hubmail import hbm_mail_import  # 2.84.0 (#1198): a hub address (client / project / hub inbox) -> a filed mail
    h = hbm_mail_import(c, msg, raw)
    if h is not None:
        return h or None
    mid = str(msg.get("Message-ID", "")).strip()[:300] or ("sha:" + hashlib.sha256(raw).hexdigest())
    if c.execute("SELECT 1 FROM tasks WHERE tt_id=?", ("mail:" + mid,)).fetchone():
        return MAIL_DROP
    uid, lid, how_to = mail_target(c, msg)
    hint = ""
    if MAIL_TASK_HOOK and not mid.startswith("sha:"):  # 2.393.2 B (#3375): a reply to a task -> its comment (or a note)
        if c.execute("SELECT 1 FROM task_mail WHERE msg_id=? AND kind IN ('src','in')", (mid,)).fetchone():
            return MAIL_DROP
        how, val = MAIL_TASK_HOOK["take"](c, msg, mid, uid, how_to)
        if how == "comment":
            c.commit()
            return val
        hint = val
    if not uid:
        return MAIL_DROP
    subj = MAIL_PREFIX_RE.sub("", str(msg.get("Subject", "")).replace("\n", " ")).strip()
    text, files = mail_text(msg)
    us = usettings(c, uid)
    eml = None
    if us.get("mail_trim_fwd") == "1":  # 2.49.0 (#971): a forwarded mail shrinks to one header line + the message; the original stays as .eml
        short = md_trim_forward(text)
        if short != text:
            text = short
            if us.get("mail_trim_eml") != "0":
                eml = raw
    lg = lang(c, uid)
    sender = str(msg.get("From", "")).strip()
    title = subj or (text.split("\n", 1)[0][:120] if text else tr("E-mail", lg=lg))
    content = (text + "\n\n" if text else "") + f"— {tr('E-mail from {0}', sender, lg=lg)}" if sender else text
    if hint:  # 2.393.2 B (#3375): "Reply to #N, sender not allowed"
        content = (content + "\n\n" if content else "") + "— " + hint
    title, content, url = split_link(title, content)
    if lid:
        ts = iso(now_utc())
        srt = c.execute("SELECT COALESCE(MIN(sort),0)-1 FROM tasks WHERE list_id=? AND parent_id IS NULL", (lid,)).fetchone()[0]
        tid = insert_id(c, "INSERT INTO tasks(list_id,title,content,sort,created_at,updated_at,tt_id,created_by,url) VALUES(?,?,?,?,?,?,?,?,?)",
                        (lid, title[:300], content, srt, ts, ts, "mail:" + mid, uid, url if valid_url(url) else None))
        log_act(c, tid, "created", uid=uid)
        agent_added_events(c, tid, source="mail")  # 2.23.0 (#795)
    else:
        tid = new_inbox_task(c, uid, title, content, "mail:" + mid, url)
    if MAIL_TASK_HOOK and not mid.startswith("sha:"):  # 2.393.2 B (#3375): the reporter + the Message-ID of the mail
        MAIL_TASK_HOOK["keep"](c, tid, mid, email.utils.parseaddr(sender)[1].strip().lower(), "src")  # 2.393.2 F: review 2
    if eml is not None:
        files = [((subj[:60].replace("/", "-").strip() or "mail") + ".eml", "message/rfc822", eml)] + files
    whole = len(files) <= 20
    for name, mime, data in files[:20]:
        if 0 < len(data) <= MAX_FILE_MB * 1024 * 1024:
            try:
                save_attachment_bytes(c, tid, name, mime, data)
            except OSError:
                whole = False
                break
        elif data:
            whole = False
    bump(c)
    c.commit()
    return tid if whole else MailKept(tid)


MAIL_LITERAL_MAX = 40 * 1024 * 1024  # 2.148.1 D (#2485): largest literal read from an IMAP server (whatever size it announces)


def mail_cap_literals(M, limit):
    """2.148.1 D (#2485): a literal over limit ends the session (IMAP4.abort) instead of being read into memory."""
    read = M.read

    def capped(size):
        if size > limit:
            raise imaplib.IMAP4.abort("literal too large")
        return read(size)
    M.read = capped


MAIL_SEEN_DAYS = 30  # 2.193.0 D (#2220): how long the taken messages of a mailbox are remembered
_SEEN_PRUNE = [0.0]
MAIL_TRIES = 4  # 2.1269 (#6386): attempts per mail (the first + 3 more); a mail whose import broke off or failed that often stays in the mailbox


def mail_seen_key(raw, u):
    """2.193.0 D (#2220): the claim key of one message of a mailbox: a hash of the Message-ID (else of the head) and the
    IMAP UID, so two copies of one mail (two addresses) stay two mails."""
    head = re.split(rb"\r?\n\r?\n", raw, maxsplit=1)[0]
    try:
        mid = str(email.parser.BytesHeaderParser(policy=email.policy.default).parsebytes(head).get("Message-ID", "") or "").strip()
    except Exception:  # noqa: BLE001 -- 2.1269 (#6386): a head the parser gives up on still gets its key (the attempts count it)
        mid = ""
    return hashlib.sha256((mid.encode() if mid else b"head:" + head) + b"|" + (u if isinstance(u, bytes) else str(u).encode())).hexdigest()


def mail_try_open_uids(box):
    """2.1269 (#6386): the UIDs of box with an attempt that was not finished (the round after a cut-off, a restart, a failure)."""
    c = connect()
    try:
        out = [r[0].encode() for r in c.execute("SELECT imap_uid FROM mail_in_seen WHERE box=? AND state='open' AND imap_uid IS NOT NULL "
                                                "ORDER BY seen_at", (box,)).fetchall()]
        c.commit()
        return out
    finally:
        c.close()


def mail_try_start(box, key, u, again):
    """2.1269 (#6386): starts one attempt of a mail, committed before the import (a cut-off leaves it open, not final).
    Returns (n, gave): n = the number of this attempt (None = not to be tried: done, given up or taken by another process),
    gave = this call gave the mail up (its last attempt broke off). again = the UID came from an open attempt only: no new
    claim then (after a UIDVALIDITY change the UID may name another, already handled mail)."""
    c = connect()
    try:
        u = (u.decode() if isinstance(u, bytes) else str(u))[:40]
        n = None if again else c.execute("INSERT INTO mail_in_seen(box, mid, seen_at, tries, state, imap_uid) VALUES(?,?,?,1,'open',?) "
                                         "ON CONFLICT DO NOTHING RETURNING tries", (box, key, iso(now_utc()), u)).fetchone()
        if n is None:
            n = c.execute("UPDATE mail_in_seen SET tries=tries+1, seen_at=?, imap_uid=? WHERE box=? AND mid=? AND state='open' AND tries<? "
                          "RETURNING tries", (iso(now_utc()), u, box, key, MAIL_TRIES)).fetchone()
        gave = n is None and c.execute("UPDATE mail_in_seen SET state='gave' WHERE box=? AND mid=? AND state='open' RETURNING 1",
                                       (box, key)).fetchone() is not None
        c.commit()
        return (n[0] if n else None), gave
    finally:
        c.close()


def mail_try_done(c, box, key, n):
    """2.1269 (#6386): attempt n of the mail ends in c's transaction (committed with its import): False when it is no longer
    this attempt's (another process took it over, or it is done). The row lock holds a second taker until c ends."""
    return c.execute("UPDATE mail_in_seen SET state='done' WHERE box=? AND mid=? AND state='open' AND tries=? RETURNING 1",
                     (box, key, n)).fetchone() is not None


def mail_try_later(c, box, key, n):
    """2.1322.0 (#6560 3): attempt n was put back by its importer (MAIL_LATER, a limit): it stays open and does not count
    (the attempts are for imports that break, not for waiting)."""
    c.execute("UPDATE mail_in_seen SET tries=GREATEST(tries-1, 0), seen_at=? WHERE box=? AND mid=? AND state='open' AND tries=?",
              (iso(now_utc()), box, key, n))


def mail_try_failed(box, key, n):
    """2.1269 (#6386): attempt n failed: the last one gives the mail up (True), else it stays open for the next round."""
    if n < MAIL_TRIES:
        return False
    c = connect()
    try:
        r = c.execute("UPDATE mail_in_seen SET state='gave' WHERE box=? AND mid=? AND state='open' AND tries=? RETURNING 1",
                      (box, key, n)).fetchone()
        c.commit()
        return r is not None
    finally:
        c.close()


def mail_try_lost(box, u):
    """2.1269 (#6386): an open attempt whose UID names another mail now (UIDVALIDITY changed, the folder was rebuilt): its own
    mail cannot be fetched again and may lie there read without ever being taken in -- it counts as given up (-> how many),
    so the owners hear of it."""
    c = connect()
    try:
        n = len(c.execute("UPDATE mail_in_seen SET state='gave' WHERE box=? AND imap_uid=? AND state='open' RETURNING 1",
                          (box, u.decode() if isinstance(u, bytes) else str(u))).fetchall())
        c.commit()
        return n
    finally:
        c.close()


def mail_try_gone(box, u):
    """2.1269 (#6386): an open attempt whose mail is not in the folder any more (moved or deleted by hand): nothing to try."""
    c = connect()
    try:
        c.execute("UPDATE mail_in_seen SET state='done' WHERE box=? AND imap_uid=? AND state='open'", (box, u.decode()))
        c.commit()
    finally:
        c.close()


def mail_seen_prune():
    """After a fetch, at most hourly: the claims older than MAIL_SEEN_DAYS go (the mails are long marked seen)."""
    if time.time() - _SEEN_PRUNE[0] < 3600:
        return 0
    _SEEN_PRUNE[0] = time.time()
    c = connect()
    try:
        n = c.execute("DELETE FROM mail_in_seen WHERE seen_at < ?", (iso(now_utc() - timedelta(days=MAIL_SEEN_DAYS)),)).rowcount
        c.commit()
        return n
    finally:
        c.close()


def mail_fetch(M, folder, importer, max_bytes=None, box="", delete=False, prefetch=False, lost=None):
    """2.141.0 A (#2141): the unseen mails of folder (a logged-in IMAP connection) -> importer(c, raw), each one marked \\Seen
    before its import (2.519.0 B, #4378: a mail that breaks the import does not come back as unseen). Returns how many were taken in.
    max_bytes (review): a mail whose RFC822.SIZE is larger is not fetched (marked seen) -- a workspace's own server.
    box (2.193.0 D, #2220): the mailbox's key in mail_in_seen (a message is handled once, also by two processes).
    2.1269 (#6386): with box each mail has attempts there: one committed before the import, finished in the import's
    transaction. An attempt cut off (time over, restart, database) or failed stays open, its UID is fetched again in the next
    round, up to MAIL_TRIES attempts; then the mail is given up and stays in the mailbox. lost(n) hears how many mails this
    round gave up (once per mail).
    delete (2.240.0 A, #2883): a mail taken in whole (or MAIL_DROP: for nobody / a double) is deleted (\\Deleted + UID EXPUNGE);
    one that failed, was taken in only in part (MailKept), was refused by an importer (None / 0) or skipped as too large
    stays (marked \\Seen).
    prefetch (2.424.0 B2, #3450): importer(None, raw) runs first, outside the gate and any database transaction (the
    invoice link downloads, up to 40 s), its result goes in as importer(c, raw, pre)."""
    n, gone, gave = 0, [], 0
    max_bytes = max_bytes or MAIL_LITERAL_MAX  # 2.148.1 G (#2485): a too large mail is skipped (seen), never fetched again
    mail_cap_literals(M, max_bytes + 1024 * 1024)  # 2.148.1 D (#2485)
    typ, _ = M.select(folder)
    if typ != "OK":
        raise imaplib.IMAP4.error("could not select the folder")
    typ, data = M.uid("SEARCH", None, "UNSEEN")
    new = (data[0] or b"").split()
    again = []
    if box:  # 2.1269 (#6386): the open attempts after the new mails (one that breaks the connection never holds the new ones up)
        with GATE.bg():
            again = mail_try_open_uids(box)
        # 2.1322.0 (#6560 3): an open attempt that is unseen again (a mail an importer put back for later, MAIL_LATER) goes
        # behind the new mails as well: a flood waiting for its limit never holds up the other mails of the mailbox
        new = [u for u in new if u not in set(again)]
    try:  # 2.1269 (#6386): the notice also when the round breaks off later (each given-up mail counts once)
        for u in (new + again)[:200]:
            retry = u in again
            if max_bytes and not retry:
                typ, sz = M.uid("FETCH", u, "(RFC822.SIZE)")
                got = re.search(rb"RFC822\.SIZE (\d+)", b" ".join(x if isinstance(x, bytes) else b"" for x in (sz or [])))
                if not got or int(got.group(1)) > max_bytes:
                    print("mail: skipped one mail: too large or no size", flush=True)
                    M.uid("STORE", u, "+FLAGS", "(\\Seen)")
                    continue
            # 2.1269 (#6386): BODY.PEEK[] does not mark the mail seen; it is marked once its attempt is noted (a restart in
            # between leaves it unseen, never seen without an attempt)
            typ, parts = M.uid("FETCH", u, "(BODY.PEEK[])")
            raw = next((p[1] for p in parts if isinstance(p, tuple) and len(p) > 1), None)
            if not raw:
                if retry:  # moved away or deleted by hand since the last attempt
                    with GATE.bg():
                        mail_try_gone(box, u)
                else:  # 2.549.0 (#4378): a mail without content is marked seen right here
                    M.uid("STORE", u, "+FLAGS", "(\\Seen)")
                continue
            _PARSED.raw = _PARSED.msg = None  # 2.1281.0 (#6425): nothing of the mail before stays
            try:  # 2.1281.0 (#6425): counted on its bytes before anything reads it (the attempt key below reads its head, the
                mail_precheck(raw)  # importers take it apart): a refused mail stays in the mailbox, marked seen, with its reason in the log
            except MailRefused as e:
                print("mail: refused one mail:", e.code, flush=True)
                M.uid("STORE", u, "+FLAGS", "(\\Seen)")
                if retry:  # (an open attempt of it from before: refused for good, never tried again)
                    with GATE.bg():
                        mail_try_gone(box, u)
                continue
            key, tries = None, None
            if box:
                key = mail_seen_key(raw, u)
                with GATE.bg():  # (no database: the round ends here, the mail stays unseen and comes again)
                    tries, out = mail_try_start(box, key, u, retry)
                gave += out
                if tries is None and retry and not out:  # the UID names another mail now: the old attempt is lost
                    with GATE.bg():
                        gave += mail_try_lost(box, u)
            # 2.519.0 B (#4378): seen before it is handled: a mail whose import is cut off does not come back as unseen
            M.uid("STORE", u, "+FLAGS", "(\\Seen)")
            if box and tries is None:  # done, given up, or another process has it (2.193.0 D, #2220)
                continue
            done, failed, later = False, False, False
            pre = None
            if prefetch:
                try:
                    pre = importer(None, raw)
                except MailRefused:  # 2.1281.0 (#6425): the import below gets the same refusal (_mail_msg remembers it) and says so once
                    pre = False
                except Exception as e:  # noqa: BLE001 -- no downloads then; the mail itself goes on
                    print("mail: prefetch failed:", type(e).__name__, flush=True)
                    pre = False
            with GATE.bg():
                c = connect()
                try:
                    res = None
                    if box and not mail_try_done(c, box, key, tries):  # another process took the attempt over
                        c.rollback()
                    elif (res := (importer(c, raw, pre) if prefetch else importer(c, raw))) is MAIL_LATER:
                        c.rollback()  # 2.1322.0 (#6560 3): not now - the attempt stays open and is not counted
                        later = True
                        if box:
                            mail_try_later(c, box, key, tries)
                            c.commit()
                    elif res:
                        n += 1
                        if box:  # (the importer committed; the end of the attempt went with it -- again if it rolled back)
                            mail_try_done(c, box, key, tries)
                        c.commit()
                    elif box:  # for nobody: nothing of it stays but the finished attempt
                        c.rollback()
                        mail_try_done(c, box, key, tries)
                        c.commit()
                    done = res is MAIL_DROP or bool(res) and not isinstance(res, MailKept)  # 2.240.0 A (#2883)
                except Exception as e:  # noqa: BLE001 - 2.126.0 review: one mail that fails never blocks the rest
                    # no message text (addresses). 2.1281.0 (#6425): a refused mail with its reason (too many parts / too deep /
                    # the head) is refused for good: its attempt ends here, it stays in the mailbox marked seen
                    refused = isinstance(e, MailRefused)
                    print("mail: refused one mail:" if refused else "mail: skipped one mail:", e.code if refused else type(e).__name__,
                          f"(attempt {tries})" if tries and not refused else "", flush=True)
                    failed = not refused
                    try:
                        c.rollback()
                        if refused and box:
                            mail_try_done(c, box, key, tries)
                            c.commit()
                    except Exception:  # noqa: BLE001 -- rollback after an error: the next mail starts fresh
                        pass
                finally:
                    c.close()
                    _PARSED.raw = _PARSED.msg = None  # 2.1281.0 (#6425): the parsed mail goes with its round
            if failed and box:  # 2.1269 (#6386): open for the next round, given up after the last attempt
                try:
                    with GATE.bg():
                        gave += mail_try_failed(box, key, tries)
                except Exception as e:  # noqa: BLE001 -- no database: the attempt stays open, the next round counts it
                    print("mail: attempt not noted:", type(e).__name__, flush=True)
            if later:  # 2.1322.0 (#6560 3): unseen again, in the mailbox for the next round
                M.uid("STORE", u, "-FLAGS", "(\\Seen)")
                continue
            if delete and done:
                M.uid("STORE", u, "+FLAGS", "(\\Seen \\Deleted)")
                gone.append(u)
        if gone:
            mail_expunge(M, gone)
    finally:
        if gave:
            print("mail: gave up", gave, "mail(s), they stay in the mailbox", flush=True)  # 2.1269 (#6386): a count, no subject / sender
            if lost:
                try:  # (the callee enters the background gate itself: never nested)
                    lost(gave)
                except Exception as e:  # noqa: BLE001 -- the notice never stops the round
                    print("mail: lost notice failed:", type(e).__name__, flush=True)
    if box:
        with GATE.bg():
            mail_seen_prune()  # 2.193.0 D (#2220)
    return n


def mail_expunge(M, uids):
    """2.240.0 A (#2883): removes exactly these deleted mails (UID EXPUNGE, RFC 4315 UIDPLUS). 2.666.0 (#4074 2): a server
    without it gets the plain EXPUNGE only when no other mail of the folder is marked deleted (it removes every marked one:
    another client's mail marked deleted but not yet removed is never taken along); else ours stay marked seen + deleted
    (never fetched again) until the mail program removes them. A failure leaves them marked as well."""
    try:
        if "UIDPLUS" in (getattr(M, "capabilities", ()) or ()):  # (imaplib's uid() knows no EXPUNGE: an extension command)
            M.xatom("UID", "EXPUNGE", b",".join(u if isinstance(u, bytes) else str(u).encode() for u in uids).decode())
            return  # 2.666.0 (#4074 2): also when refused -- no plain EXPUNGE behind it (it would take other mails along)
        typ, data = M.uid("SEARCH", None, "DELETED")
        mine = {u if isinstance(u, bytes) else str(u).encode() for u in uids}
        marked = set((data[0] or b"").split()) if typ == "OK" and data else None
        if marked is None or not marked <= mine:
            print("mail: other mails marked deleted in the folder, no expunge", flush=True)
            return
        M.expunge()
    except Exception as e:  # noqa: BLE001 - the mails stay marked seen
        print("mail: expunge failed:", type(e).__name__, flush=True)


def mail_lost_instance(n):
    """2.1269 (#6386): n mails of the instance address were given up after MAIL_TRIES attempts: the instance admins hear it
    once (News + push of the event "integration", collab/integfail.py)."""
    with GATE.bg():
        c = connect()
        try:
            with system_ctx(c):
                uids = [r[0] for r in c.execute("SELECT id FROM users WHERE is_admin AND NOT disabled AND kind<>'agent' ORDER BY id").fetchall()]
            integ_tell(c, uids, "maillost", IMAP["user"] or IMAP["host"], str(n), click="settings")
            c.commit()
        finally:
            c.close()


def mail_poll_once():
    """One round: the unseen mails of the folder -> tasks; each one is marked \\Seen afterwards (also when it was for
    nobody: it is never looked at again) and deleted unless KALMIDO_IMAP_KEEP=1 (2.240.0 A, #2883)."""
    port = IMAP["port"] or (993 if IMAP["ssl"] else 143)
    M = imaplib.IMAP4_SSL(IMAP["host"], port, timeout=60, ssl_context=_admin_tls_ctx()) if IMAP["ssl"] else imaplib.IMAP4(IMAP["host"], port, timeout=60)
    try:
        M.login(IMAP["user"], IMAP["password"])
        return mail_fetch(M, IMAP["folder"], mail_import, box="instance", delete=not IMAP_KEEP, prefetch=True, lost=mail_lost_instance)
    finally:
        try:
            M.logout()
        except Exception:  # noqa: BLE001 -- logout after the fetch: the server may have closed the connection already
            pass


_MAIL_WAKE = threading.Event()


def mail_loop():
    while True:
        try:
            n = mail_poll_once()
            aa_ok("mail")
            if n:
                print("mail: imported", n, "task(s)", flush=True)
        except Exception as e:  # noqa: BLE001
            print("mail:", type(e).__name__, flush=True)  # 2.240.0 A (#2883): no message text
            aa_fail("mail", aa_err(e))
        _MAIL_WAKE.wait(IMAP["interval"])
        _MAIL_WAKE.clear()


@app.post("/api/admin/mail/poll")
def mail_poll_now():
    """Admins: look into the mailbox now (instead of waiting for the next round)."""
    need_admin()
    if not MAIL_IN_ON:
        return err(tr("E-mail to tasks is not set up on this server"), 409)
    _MAIL_WAKE.set()
    return jsonify(ok=True)


class _SafeSMTP(smtplib.SMTP):
    """2.141.0 A (#2141): SMTP to a host a workspace entered: every address of the name is checked (no internal host unless
    the admin allowed it, calendars/subscriptions.py cal_allow) and exactly the checked one is connected to."""
    def __init__(self, host, port, timeout, allow):
        self._kal_allow = allow
        super().__init__(host, port, timeout=timeout)

    def _get_socket(self, host, port, timeout):
        return _cal_connector(self._kal_allow)((host, port), timeout)


class _SafeSMTP_SSL(smtplib.SMTP_SSL):
    def __init__(self, host, port, timeout, allow):
        self._kal_allow = allow
        super().__init__(host, port, timeout=timeout, context=_tls_ctx())

    def _get_socket(self, host, port, timeout):
        return self.context.wrap_socket(_cal_connector(self._kal_allow)((host, port), timeout), server_hostname=self._host)


def _tls_ctx():
    """2.141.0 A (#2141, review): a workspace's own server is only spoken to with a checked certificate (the stdlib default
    of smtplib / imaplib checks none); KALMIDO_SMTP_* / KALMIDO_IMAP_* of the admin: _admin_tls_ctx."""
    import ssl
    return ssl.create_default_context()


def _admin_tls_ctx():
    """2.240.0 A (#2883): KALMIDO_SMTP_* / KALMIDO_IMAP_* of the admin are checked too (certificate + host name); only
    KALMIDO_SMTP_INSECURE=1 turns the check off (for both, warned once at start)."""
    import ssl
    ctx = ssl.create_default_context()
    if SMTP_INSECURE:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def smtp_open(smtp=None):
    """2.141.0 A (#2141): a connected and logged-in SMTP session: KALMIDO_SMTP_* (smtp None), else a workspace's access
    {host, port, tls, user, password, from, allow} (allow = the hosts that may be internal: the connection is checked)."""
    cfg = smtp or SMTP
    tls = cfg["tls"]
    port = cfg["port"] or (465 if tls == "ssl" else 587 if tls == "starttls" else 25)
    if smtp is None:
        S_ = smtplib.SMTP_SSL(cfg["host"], port, timeout=30, context=_admin_tls_ctx()) if tls == "ssl" else smtplib.SMTP(cfg["host"], port, timeout=30)
    else:
        allow = cfg.get("allow") or frozenset()
        S_ = _SafeSMTP_SSL(cfg["host"], port, 30, allow) if tls == "ssl" else _SafeSMTP(cfg["host"], port, 30, allow)
    try:
        if tls == "starttls":
            S_.starttls(context=_admin_tls_ctx() if smtp is None else _tls_ctx())
        if cfg["user"]:
            S_.login(cfg["user"], cfg["password"])
    except BaseException:
        try:
            S_.close()
        except Exception:  # noqa: BLE001 -- closing a half-open SMTP connection before the error is raised again
            pass
        raise
    return S_


def mail_message(to, subject, text, html_body=None, images=None, from_name=None, attachments=None, cc=None, reply_to=None, smtp=None, unsub=None):
    """2.141.0 A (#2141): the message mail_send sends (built first so the e-mail filing can keep it before it goes out).
    2.367.5 (#2975): unsub = the one-click link of a notification mail (RFC 8058), never on a security mail or an invoice."""
    subject, text = le2b_net(subject), le2b_net(text)  # 2.64.1 B (#1817): never a ciphertext of a list with the lock in a mail
    html_body = le2b_net(html_body) if html_body else html_body
    frm = (smtp or SMTP)["from"]
    m = email.message.EmailMessage()
    m["From"], m["To"], m["Subject"] = (email.utils.formataddr((from_name, frm)) if from_name else frm), to, subject
    if cc:
        m["Cc"] = cc
    if reply_to:
        m["Reply-To"] = reply_to
    if unsub:
        m["List-Unsubscribe"], m["List-Unsubscribe-Post"] = f"<{unsub}>", "List-Unsubscribe=One-Click"
    m["Date"] = email.utils.formatdate(localtime=True)
    m["Message-ID"] = email.utils.make_msgid(domain=(frm.rpartition("@")[2] or "kalmido.local"))
    m.set_content(text)
    if html_body:
        m.add_alternative(html_body, subtype="html")
        for cid, (data, sub) in (images or {}).items():
            m.get_payload()[1].add_related(data, "image", sub, cid=f"<{cid}>")
    for name, data, mime in attachments or []:
        main, _, sub = (mime or "application/octet-stream").partition("/")
        m.add_attachment(data, maintype=main or "application", subtype=sub or "octet-stream", filename=name)
    return m


def mail_deliver(m, smtp=None):
    """2.141.0 A (#2141): sends a built message (mail_message) through KALMIDO_SMTP_* or the access smtp; raises on failure."""
    S_ = smtp_open(smtp)
    try:
        S_.send_message(m)
    finally:
        try:
            S_.quit()
        except Exception:  # noqa: BLE001 -- quit after sending: the mail is out, a server that already closed does not matter
            pass


def mail_send(to, subject, text, html_body=None, images=None, from_name=None, attachments=None, cc=None, reply_to=None, smtp=None, unsub=None):
    """Sends one mail with KALMIDO_SMTP_*; raises on failure. images: {cid: (bytes, subtype)} shown in the HTML part
    (2.22.0: the logo of the invitation); from_name: a display name for the sender. 2.38.0 (#1021): attachments =
    [(file name, bytes, mime type)] (invoice PDF / XML), cc = a second address, reply_to = the sender's own address.
    2.141.0 A (#2141): smtp = a workspace's own SMTP access instead (hub/mailbox.py mbx_smtp); returns the message sent."""
    m = mail_message(to, subject, text, html_body, images, from_name, attachments, cc, reply_to, smtp=smtp, unsub=unsub)
    mail_deliver(m, smtp)
    return m


def _sec_mail_send(to, subject, text, html_body, images=None):
    """2.266.0 (#2963): the background part of a security mail (accounts/secmail.py queues it by its kind, one try).
    2.593.0 (#3570): images = the logo of an organisation's invitation mail (accounts/invite.py invite_new bg)."""
    try:
        mail_send(to, subject, text, html_body, images=images or None, from_name=APP_NAME)
    except Exception as e:  # noqa: BLE001  (nobody waits for it)
        print("security mail failed:", type(e).__name__, flush=True)


if MAIL_OUT_ON:  # registered only with outgoing mail: accounts/secmail.py queues nothing without it
    bgj_fn("mail:security", tries=1)(_sec_mail_send)


def digest_mail_content(c, uid, today):
    """(subject, text, html) of a person's daily summary: due today / overdue, tomorrow, what waits for them, unread."""
    lg = lang(c, uid)
    rows = c.execute(f"""SELECT t.id, t.title, t.due, t.due_time, t.priority, l.name AS lname, l.is_inbox, l.e2e AS le2e FROM tasks t JOIN lists l ON l.id=t.list_id
                         WHERE t.status=0 AND t.deleted_at IS NULL AND t.parent_id IS NULL AND t.due IS NOT NULL AND t.due<=? AND {list_state_sql('l')}
                           AND ((l.owner_id=? AND (t.assignee_id IS NULL OR t.assignee_id=?)) OR (t.assignee_id=? AND t.list_id IN {vis_sql()}))
                         ORDER BY t.due, t.due_time IS NULL, t.due_time, t.priority DESC LIMIT 60""",
                     ((date.fromisoformat(today) + timedelta(days=1)).isoformat(), uid, uid, uid, uid, uid)).fetchall()
    tom = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
    over = [r for r in rows if r["due"] < today]
    tod = [r for r in rows if r["due"] == today]
    tmr = [r for r in rows if r["due"] == tom]
    waits = c.execute("SELECT COUNT(*) FROM agent_jobs WHERE state='waiting' AND (user_id=? OR user_id IS NULL)", (uid,)).fetchone()[0] \
        if table_exists(c, "agent_jobs") else 0
    unread = news_unread(c, uid)
    chat = tchat_unread(c, uid)
    # 2.368.4 (#2989): the default inbox in the reader's language, as in a push (notify/channels.py), not its stored name
    lname = lambda r: tr("Basket", lg=lg) if r["is_inbox"] and inbox_default(r["lname"]) else r["lname"]  # noqa: E731
    line = lambda r: f"- {md_plain(r['title'])}" + (f" ({r['due_time']})" if r["due_time"] else "") + f" · {lname(r)}"  # noqa: E731
    parts = []
    for head, xs in ((tr("Overdue", lg=lg), over), (tr("Today", lg=lg), tod), (tr("Tomorrow", lg=lg), tmr)):
        if xs:
            # 2.64.1 B (#1817): tasks of a list with the lock as one line per list ("3 tasks in <list> (encrypted)")
            lk = {}
            for r in xs:
                if r["le2e"]:
                    lk[lname(r)] = lk.get(lname(r), 0) + 1
            shown = [line(r) for r in xs if not r["le2e"]][:25]
            shown += ["- " + trn("{0} task in {1} (encrypted)", "{0} tasks in {1} (encrypted)", k, ln, lg=lg) for ln, k in lk.items()]
            parts.append(f"{head} ({len(xs)})\n" + "\n".join(shown))
    extra = []
    if waits:
        extra.append(trn("{0} approval waits for you", "{0} approvals wait for you", waits, lg=lg))
    if unread:
        extra.append(trn("{0} unread news item", "{0} unread news items", unread, lg=lg))
    if chat:
        extra.append(trn("{0} unread chat message", "{0} unread chat messages", chat, lg=lg))
    if extra:
        parts.append(" · ".join(extra))
    if not parts:
        return None
    subj = f"{APP_NAME}: " + (trn("{0} task today", "{0} tasks today", len(tod) + len(over), lg=lg) if tod or over else tr("Your day", lg=lg))
    foot = tr("You get this summary every day. Change or switch it off in Settings > Notifications:", lg=lg)  # 2.367.5 (#2975): the footer of the event mail
    text = "\n\n".join(parts) + f"\n\n{PUBLIC_URL}/#today\n\n-- \n{foot} {PUBLIC_URL}/#settings/notify\n"
    hfoot = Safe(f'{html.escape(foot)} <a href="{html.escape(PUBLIC_URL)}/#settings/notify" style="color:{MAIL_ACC}">{html.escape(tr("Settings", lg=lg))}</a>')
    return subj, text, mail_html(subj, parts, tr("Open {0}", APP_NAME, lg=lg), f"{PUBLIC_URL}/#today", foot=hfoot, lang=lg)  # 2.420.0 B (#3499)


DIGEST_MAIL_TRIES, DIGEST_MAIL_GAP = 3, 900  # 2.367.5 (#2975): a failed summary is tried again, at most 3 times a day, 15 minutes apart


def digest_mail_user(c, uid, s, today):
    """2.367.5 (#2975): "sent" only after the mail went out; every try is noted before it (no transaction open while the mail
    server is asked). A crash right after sending can repeat the mail once the gap is over: rather twice than not at all.
    The day's limit of the address counts the summary once, the person's own sending quota not at all."""
    if not MAIL_OUT_ON or s.get("digest_mail") != "1" or s.get("digest_mail_sent") == today:
        return False
    u = c.execute("SELECT email, email_proved, disabled FROM users WHERE id=?", (uid,)).fetchone()
    if not u or u["disabled"] or not (u["email"] or "").strip():
        return False
    day, _, rest = str(s.get("digest_mail_try") or "").partition(":")
    n, _, at = rest.partition(":")
    tries = int(n) if day == today and n.isdigit() else 0
    if tries >= DIGEST_MAIL_TRIES or (tries and time.time() - float(at or 0) < DIGEST_MAIL_GAP):
        return False
    m = digest_mail_content(c, uid, today)
    if m and not MAIL_PROOF["ok"](u):  # 2.1299.0 (#6352): content only to a proved address - instead (once per address) the proof mail
        uset(c, uid, "digest_mail_sent", today)
        c.commit()
        MAIL_PROOF["hint"](c, uid)
        return False
    from ..admin.hosting import mail_budget
    over = bool(m) and not tries and not mail_budget(c, None, u["email"])
    if not m or over:
        uset(c, uid, "digest_mail_sent", today)  # nothing to say, or the day's mails are used up: not again today
        c.commit()
        if over:
            aa_count("watchdog", "daily mail over the limit", uid)
        return False
    uset(c, uid, "digest_mail_try", f"{today}:{tries + 1}:{int(time.time())}")
    off = mail_off_url(c, uid, "digest")
    c.commit()
    try:
        mail_send(u["email"].strip(), *m, from_name=APP_NAME, unsub=off)
    except Exception as e:  # noqa: BLE001
        print("mail: summary for user", uid, "failed:", type(e).__name__, flush=True)  # 2.240.0 A (#2883): no addresses
        aa_fail("smtp", aa_err(e))
        return False
    uset(c, uid, "digest_mail_sent", today)
    c.commit()
    aa_ok("smtp")
    return True


# ---- 2.367.5 (#2975): one-click off of the notification mails (headers List-Unsubscribe, RFC 8058). The link carries the person,
# what it turns off and a signature, it needs no sign-in. GET only shows a page with one button (mail scanners open every
# link of a mail, like the portal's off link), POST turns the mails off; the mail client's own button posts directly.
MAIL_OFF = {"digest": {"digest_mail": "0"}, "event": {"mail_assign": "off", "mail_mention": "off"}}
MAIL_OFF_PATH = "/mail/off/"


def mail_off_sig(c, uid, what):
    return hmac.new(auth_key(c), f"mailoff|{uid}|{what}".encode(), hashlib.sha256).hexdigest()[:40]


def mail_off_url(c, uid, what):
    return f"{PUBLIC_URL.rstrip('/')}{MAIL_OFF_PATH}{uid}.{what}.{mail_off_sig(c, uid, what)}"


def mail_off_open(c, token):
    """(user id, what) of a valid off link, else (None, None): the same answer for every wrong link."""
    uid, what, sig = (str(token).split(".") + ["", ""])[:3]
    if not (uid.isascii() and uid.isdigit()) or len(uid) > 18 or what not in MAIL_OFF or not hmac.compare_digest(sig.encode(), mail_off_sig(c, int(uid), what).encode()):
        return None, None
    return int(uid), what


def _mail_off_page(token, done):
    if hit_limit(f"mailoff:{rate_ip()}", 30):
        return pub_html(tr("Too many requests"), f'<div class="msg"><h1>{html.escape(tr("Too many requests"))}</h1></div>', browser_lang() or "en", 429)
    c = db()
    with system_ctx(c):  # nobody is signed in: the person of the link, nothing else
        uid, what = mail_off_open(c, token)
        lg = lang_of(usettings(c, uid)) if uid else (browser_lang() or "en")
        if not uid or not c.execute("SELECT 1 FROM users WHERE id=? AND kind!='agent'", (uid,)).fetchone():
            return pub_html(tr("Not found", lg=lg), f'<div class="msg"><h1>{html.escape(tr("Not found", lg=lg))}</h1></div>', lg, 404)
        if done:
            for k, v in MAIL_OFF[what].items():
                uset(c, uid, k, v)
    c.commit()
    e = html.escape
    name = tr("Daily summary by e-mail", lg=lg) if what == "digest" else tr("E-mails for assignments and mentions", lg=lg)
    if done:
        title, body_ = tr("E-mails switched off", lg=lg), (f'<p>{e(name)}</p><p>{e(tr("You can switch them on again in Settings > Notifications.", lg=lg))}</p>'
                                                         f'<a class="btn" href="{e(PUBLIC_URL)}/#settings/notify">{e(tr("Settings", lg=lg))}</a>')
    else:
        title, body_ = tr("Turn e-mails off", lg=lg), (f'<p>{e(name)}</p><form method="post" class="fform">'
                                                       f'<button type="submit">{e(tr("Turn e-mails off", lg=lg))}</button></form>')
    return pub_html(title, f'<div class="msg"><h1>{e(title)}</h1>{body_}</div>', lg)


@app.get("/mail/off/<token>")
def mail_off_ask(token):
    return _mail_off_page(token, False)


@app.post("/mail/off/<token>")
def mail_off(token):
    return _mail_off_page(token, True)


@app.post("/api/me/mail/test")
def mail_test():
    """Sends the daily summary (or a short test text) to my e-mail address now."""
    c = db()
    if not MAIL_OUT_ON:
        return err(tr("E-mail sending is not set up on this server"), 409)
    u = c.execute("SELECT email, email_proved FROM users WHERE id=?", (me(),)).fetchone()
    if not u or not (u["email"] or "").strip():
        return err(tr("No e-mail address is stored for you: an admin adds it (Settings > Organisation > People)"), 409)
    if not MAIL_PROOF["ok"](u):  # 2.1299.0 (#6352): the summary only to a proved address (the button "Confirm address" is next to it)
        return err(tr("Please confirm your e-mail address first: e-mails with content go only to a confirmed address."), 409)
    from ..admin.hosting import mail_budget
    if hit_limit(f"mailtest:{me()}", 5, 3600):  # 2.126.0 C (#1979 I6): a few tests an hour, counted in the daily e-mail limit
        return err(tr("Too many tests, please wait a few minutes"), 429)
    if not mail_budget(c, me(), u["email"]):
        c.rollback()
        return err(tr("Today's e-mail limit is reached. Try again tomorrow."), 429)
    c.commit()
    lg = lang(c, me())
    m = digest_mail_content(c, me(), local_now().date().isoformat()) or (f"{APP_NAME}: " + tr("Test", lg=lg), tr("E-mails from {0} are arriving.", APP_NAME, lg=lg), None)
    try:
        mail_send(u["email"].strip(), *m, from_name=APP_NAME)
    except Exception as e:  # noqa: BLE001
        return err(tr("Sending failed: {0}", type(e).__name__), 502)
    return jsonify(ok=True, to=u["email"].strip())
