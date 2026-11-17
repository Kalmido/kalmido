"""2.1309.0 (#6467, GoBD audit #4791 U1/U2): the database holds the positions, payments and office log of finalised documents as
well, next to kalmido_office_locked on office_docs (4598.py) and the app's own checks:

- office_doc_items (kalmido_office_items_locked): no INSERT, UPDATE or DELETE of a position whose document is finalised
  (office_docs.locked_at set, not a trial document); free are only the internal purchase price cost / cost_enc (the encryption
  passes, never printed) and org_id while it is still empty (ledger.ofx_migrate fills positions of very old versions). An UPDATE
  that moves a position to another document is checked on both documents.
- office_payments (kalmido_office_payments_locked): only bank_tx_id may change (a bank line booked on it, office/bank.py);
  no DELETE (a payment is taken back by a reversal row, reverses_id).
- office_doc_log (kalmido_office_log_locked): no UPDATE but setting doc_id once from NULL while no other column moves: an agent's
  log line learns its new draft, office/agentdocs.py _log_doc; a DELETE only of the read entries (actions open / render / pdf /
  xml = notify/push.py FX2_LOG_READS, pruned after FX2_LOG_READ_DAYS).

Like kalmido_office_locked all three let through: the transaction-local switch kalmido.locked_ok = 'on' (ledger.ofx_release,
the deliberate exceptions: the encryption passes, the organisation import and its undo, moving a personal office, the one-time
name fill of #6470 and trim of #2561; the suites' own database access tests/dbx.py) and the database's own reference actions
(pg_trigger_depth() > 1: a document / organisation that goes takes its rows with it, a deleted service or account empties
service_id / user_id). The functions read the rows as JSON, so a column that does not exist yet breaks nothing.

office_docs.chain_ver (office/chain.py): the version of the canonical data a link of the hash chain was made with (NULL = 1, the
fields of 2.531; 2 = plus the stored files' checksums and the head fields of #6467). Old links keep their version and stay valid.

Additive only. An older version runs on with the triggers except where it writes past them without the switch -- its
ofx_release lets only office_docs through, so after a rollback its organisation import / undo, encryption passes and the moving of
a personal office would fail on these tables: the way back of the app includes DROP TRIGGER kalmido_office_items_locked ON
office_doc_items, DROP TRIGGER kalmido_office_payments_locked ON office_payments, DROP TRIGGER kalmido_office_log_locked ON
office_doc_log (and their functions). An older hch_check reads a version-2 link with the version-1 data and names it broken."""
SCHEMA = """
CREATE OR REPLACE FUNCTION kalmido_office_doc_held(did BIGINT) RETURNS BOOLEAN LANGUAGE plpgsql STABLE AS $$
DECLARE
  d JSONB;
BEGIN
  IF did IS NULL THEN RETURN false; END IF;
  SELECT to_jsonb(x) INTO d FROM office_docs x WHERE x.id = did;
  RETURN d IS NOT NULL AND COALESCE(d->>'locked_at', '') <> '' AND COALESCE(d->>'trial', '0') IN ('0', '', 'false');
END $$;
CREATE OR REPLACE FUNCTION kalmido_office_items_locked() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  free TEXT[] := ARRAY['cost', 'cost_enc'];
  o JSONB;
  n JSONB;
  bad TEXT;
BEGIN
  IF current_setting('kalmido.locked_ok', true) = 'on' OR pg_trigger_depth() > 1 THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF kalmido_office_doc_held(NEW.doc_id) THEN
      RAISE EXCEPTION 'office document % is finalised: no position can be added', NEW.doc_id USING HINT = 'kalmido #6467';
    END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'DELETE' THEN
    IF kalmido_office_doc_held(OLD.doc_id) THEN
      RAISE EXCEPTION 'office document % is finalised: its position % cannot be deleted', OLD.doc_id, OLD.id USING HINT = 'kalmido #6467';
    END IF;
    RETURN OLD;
  END IF;
  IF NOT (kalmido_office_doc_held(OLD.doc_id) OR (NEW.doc_id IS DISTINCT FROM OLD.doc_id AND kalmido_office_doc_held(NEW.doc_id))) THEN
    RETURN NEW;
  END IF;
  o := to_jsonb(OLD);
  n := to_jsonb(NEW);
  IF o->>'org_id' IS NULL THEN free := free || 'org_id'; END IF;
  o := o - free;
  n := n - free;
  IF o IS DISTINCT FROM n THEN
    SELECT string_agg(e.key, ', ' ORDER BY e.key) INTO bad FROM jsonb_each(o) e WHERE e.value IS DISTINCT FROM n->e.key;
    RAISE EXCEPTION 'office document % is finalised: % of position % cannot change', OLD.doc_id, COALESCE(bad, 'a column'), OLD.id
      USING HINT = 'kalmido #6467';
  END IF;
  RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION kalmido_office_payments_locked() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  o JSONB;
  n JSONB;
  bad TEXT;
BEGIN
  IF current_setting('kalmido.locked_ok', true) = 'on' OR pg_trigger_depth() > 1 THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'payment % of office document % is booked and cannot be deleted (a reversal takes it back)', OLD.id, OLD.doc_id
      USING HINT = 'kalmido #6467';
  END IF;
  o := to_jsonb(OLD) - 'bank_tx_id';
  n := to_jsonb(NEW) - 'bank_tx_id';
  IF o IS DISTINCT FROM n THEN
    SELECT string_agg(e.key, ', ' ORDER BY e.key) INTO bad FROM jsonb_each(o) e WHERE e.value IS DISTINCT FROM n->e.key;
    RAISE EXCEPTION 'payment % of office document % is booked: % cannot change', OLD.id, OLD.doc_id, COALESCE(bad, 'a column')
      USING HINT = 'kalmido #6467';
  END IF;
  RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION kalmido_office_log_locked() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF current_setting('kalmido.locked_ok', true) = 'on' OR pg_trigger_depth() > 1 THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'DELETE' THEN
    IF OLD.action IN ('open', 'render', 'pdf', 'xml') THEN RETURN OLD; END IF;
    RAISE EXCEPTION 'office log entry % is kept for good and cannot be deleted', OLD.id USING HINT = 'kalmido #6467';
  END IF;
  IF OLD.doc_id IS NULL AND (to_jsonb(OLD) - 'doc_id') = (to_jsonb(NEW) - 'doc_id') THEN
    RETURN NEW;
  END IF;
  IF to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
    RAISE EXCEPTION 'office log entry % is kept for good and cannot change', OLD.id USING HINT = 'kalmido #6467';
  END IF;
  RETURN NEW;
END $$;
CREATE OR REPLACE TRIGGER kalmido_office_items_locked BEFORE INSERT OR DELETE OR UPDATE ON office_doc_items FOR EACH ROW EXECUTE FUNCTION kalmido_office_items_locked();
CREATE OR REPLACE TRIGGER kalmido_office_payments_locked BEFORE DELETE OR UPDATE ON office_payments FOR EACH ROW EXECUTE FUNCTION kalmido_office_payments_locked();
CREATE OR REPLACE TRIGGER kalmido_office_log_locked BEFORE DELETE OR UPDATE ON office_doc_log FOR EACH ROW EXECUTE FUNCTION kalmido_office_log_locked();
"""
MIGRATIONS = [
    ("office_docs", "chain_ver", "ALTER TABLE office_docs ADD COLUMN IF NOT EXISTS chain_ver SMALLINT"),
]
