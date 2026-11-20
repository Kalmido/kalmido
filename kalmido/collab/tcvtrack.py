"""#6232: the kind 'tchat_msg' (the earlier versions of a team chat message, collab/teamchat.py tcv_keep) is known to the shared
core from the start of every process, not only after the first edit in it: the history readers, the trash run and the undo see it
at once. A module of its own: collab/teamchat.py loads before core/writes.py (kalmido/__init__.py ORDER), this one after it.
No routes."""
from .teamchat import tcv_reg

tcv_reg()
