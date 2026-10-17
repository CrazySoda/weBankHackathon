-- Row-level security by tenant + append-only audit table (BUILD_PLAN M1).
-- Applied AFTER the tables exist, by app.db.bootstrap.apply_schema (it cannot run
-- at container initdb: the tables are created by the ORM). Idempotent.
--
-- Roles: `cleartrade` is the owner/migrator (a superuser in the local compose
-- stack, so it bypasses RLS). The application and the tests connect as
-- `cleartrade_app`, a plain role that RLS and the REVOKEs below really bind.
-- The tenant comes from a session GUC the backend sets per request/transaction:
--   SET app.current_tenant = 'tenant_a';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cleartrade_app') THEN
        CREATE ROLE cleartrade_app NOLOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO cleartrade_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cleartrade_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cleartrade_app;

-- ---- RLS: one policy per tenant-scoped table ------------------------------
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['trade_deal', 'document', 'finding', 'fx_quote', 'audit_event',
                         'deal_snapshot']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
        EXECUTE format($p$
            CREATE POLICY tenant_isolation ON %I
            USING (tenant_id = current_setting('app.current_tenant', true))
            WITH CHECK (tenant_id = current_setting('app.current_tenant', true))
        $p$, t);
    END LOOP;
END $$;

-- ---- audit_event: append-only for everyone but the owner -------------------
REVOKE UPDATE, DELETE, TRUNCATE ON audit_event FROM PUBLIC;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_event FROM cleartrade_app;
