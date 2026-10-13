"""AnchorClient tests: idempotency, mock determinism."""

from app.audit.anchor import MockAnchor


class TestMockAnchor:
    def test_deterministic_tx_ref(self):
        a = MockAnchor()
        r1 = a.anchor("abc", "t1")
        r2 = a.anchor("abc", "t1")
        assert r1.tx_ref == r2.tx_ref
        assert r1.mocked is True

    def test_different_heads_differ(self):
        a = MockAnchor()
        r1 = a.anchor("head-1", "t1")
        r2 = a.anchor("head-2", "t1")
        assert r1.tx_ref != r2.tx_ref

    def test_tenants_isolated(self):
        a = MockAnchor()
        r1 = a.anchor("same-head", "t1")
        r2 = a.anchor("same-head", "t2")
        assert r1.tx_ref != r2.tx_ref
