-- Row-level security by tenant + append-only audit table (BUILD_PLAN M1).
-- Runs once at first container init (mounted into postgres initdb).

-- ---- RLS: one policy per tenant-scoped table ------------------------------
-- The app connects as `cleartrade` which owns the tables; RLS policies use a
-- session GUC `app.current_tenant` set by the backend per request/transaction:
--   SET app.current_tenant = 'tenant_a';
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['trade_deal', 'document', 'finding', 'fx_quote', 'audit_event']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        -- table owner bypasses RLS only via explicit SET BYPASS_RLS below; for
        -- the demo the backend role is the owner, so we add a policy keyed on
        -- current_setting('app.current_tenant', true).
        EXECUTE format($p$
            CREATE POLICY tenant_isolation ON %I
            USING (tenant_id = current_setting('app.current_tenant', true))
            WITH CHECK (tenant_id = current_setting('app.current_tenant', true))
        $p$, t);
    END LOOP;
END $$;

-- ---- audit_event: append-only ---------------------------------------------
REVOKE UPDATE, DELETE ON audit_event FROM PUBLIC;
REVOKE UPDATE, DELETE ON audit_event FROM cleartrade;

-- ---- langfuse database (created on demand when profile obs is used) -------
