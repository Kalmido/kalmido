"""2.1213.0 (#6166): the earlier versions of a team chat message are rows of the core's history (obj_history, kind 'tchat_msg',
ref_id = tchat_msgs.id; collab/teamchat.py tcv_keep). obj_history has no FK to the message (kind names the table): when a message
row is deleted for good -- the core's trash run (core/objparts.py part_trash_purge), a room or a project deleted (ON DELETE
CASCADE) -- kalmido_oh_gone takes its history rows with it, as kalmido_ov_gone (5281_a.py) does for obj_versions.
Only a function and a trigger: the version before ignores them (it writes no such rows)."""
SCHEMA = """
CREATE OR REPLACE FUNCTION kalmido_oh_gone() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  DELETE FROM obj_history WHERE kind = TG_ARGV[0] AND ref_id = OLD.id;
  RETURN NULL;
END $$;
CREATE OR REPLACE TRIGGER kalmido_oh_gone_tchat AFTER DELETE ON tchat_msgs FOR EACH ROW EXECUTE FUNCTION kalmido_oh_gone('tchat_msg');
"""
