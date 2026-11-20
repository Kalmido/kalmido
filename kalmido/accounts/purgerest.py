"""(#6356, audit #4773 F8): what an account's or an organisation's delete for good leaves on the disk and in other rows, collected
by the delete itself - independent of the retention switch (deletion rule 18.10.2026: after the period really gone, files on
the disk too). The orphan sweeps (admin/dataretention.py, agents/chat.py chat_files_gc) only run with the switch on and do not
know every folder; they stay as the net behind this.

  person (accounts/users.py _user_purge, right before the account row goes)
    - the stored pictures of its bookmarks that go with it (attachments/bookmarks/, the core's purge hook of the kind, the
      same as the trash's delete for good: life/lfkern.py _bm_purge); an organisation's bookmarks handed to the heir stay
    - the files of its agent chats, either side (attachments/chat/<agent>-<person>/, the rows cascade): the folder goes whole
    - its upload of an account import (exports/account-import/<id>, up to 4 GB; else kept up to 24 h)
    - the verbatim quote of its message in an agent's standing rules (agent_rules.source_excerpt, source_user_id): the rule
      itself stays with its agent
  organisation (accounts/orgretain.py odl_dismantle, before the row goes)
    - the stored pictures of its bookmarks (the rows cascade with the organisation)

Each returns what must happen after the commit (paths relative to ATT_DIR or callables, core/serializers.py unlink_files);
the caller commits. The retention export before a delete (#2566, #2468, #1969) is not touched: it runs before these."""
import os
import shutil

from ..core.config import ATT_DIR
from ..core.pg import system_ctx


_BM_OF_USER = "SELECT id FROM bookmarks WHERE user_id=? AND image<>''"
_BM_OF_ORG = "SELECT id FROM bookmarks WHERE org_id=? AND image<>''"


def _bm_pictures(c, q, arg):
    """The pictures of the bookmarks of query q (through the core's purge hook of the kind; no hook = none)."""
    from ..core.writes import OBJ_PURGE
    from ..life import lfkern  # noqa: F401 - registers the hook (also in a process that did not load the bookmarks yet)
    from ..life.bookmarks import BM_KIND
    f = OBJ_PURGE[BM_KIND]
    out = []
    for (rid,) in c.execute(q, (arg,)).fetchall():
        out += f(c, rid) or []
    return out


def _chat_dirs_drop(uid):
    """After the commit: the agent chat folders with uid on either side (chat/<agent id>-<person id>/)."""
    root = os.path.join(ATT_DIR, "chat")
    if not os.path.isdir(root):
        return
    for d in os.listdir(root):
        a, _, p = d.partition("-")
        if a.isdigit() and p.isdigit() and int(uid) in (int(a), int(p)):
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)


def _import_drop(uid):
    """After the commit: the upload folder of an account import (admin/acctimport.py _base)."""
    from ..admin.acctimport import UMZ_IN_DIR
    shutil.rmtree(os.path.join(UMZ_IN_DIR, str(int(uid))), ignore_errors=True)


def pgr_user(c, uid):
    """Account uid goes (accounts/users.py _user_purge, before its row): its leftovers, see above -> paths / callables."""
    uid = int(uid)
    with system_ctx(c):  # its own rows, also in organisations' spaces and other people's agents
        files = _bm_pictures(c, _BM_OF_USER, uid)
        files += [r[0] for r in c.execute("SELECT f.path FROM chat_files f JOIN agent_chat m ON m.id=f.message_id "
                                          "WHERE m.user_id=? OR m.agent_id=?", (uid, uid)).fetchall()]
        c.execute("UPDATE agent_rules SET source_excerpt='', source_user_id=NULL WHERE source_user_id=?", (uid,))
    return files + [lambda: _chat_dirs_drop(uid), lambda: _import_drop(uid)]


def pgr_org(c, oid):
    """Organisation oid goes (accounts/orgretain.py odl_dismantle, before its row): its bookmarks' pictures."""
    with system_ctx(c):
        return _bm_pictures(c, _BM_OF_ORG, int(oid))
