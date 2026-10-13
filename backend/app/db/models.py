"""SQLAlchemy 2.0 models for the ClearTrade tables (BUILD_PLAN M1).

Conventions:
- Money: `amount_minor BIGINT` + `currency CHAR(3)` — never floats.
- `audit_event` is append-only: the RLS/init SQL revokes UPDATE/DELETE.
- Multi-tenant: every deal-scoped table carries `tenant_id` and is protected by
  row-level security (see db/init/002_rls.sql).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenant"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "user"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(32))  # owner | reviewer | auditor
    webauthn_credential: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WechatIdentity(Base):
    __tablename__ = "wechat_identity"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user.id"), index=True)
    openid: Mapped[str] = mapped_column(String(128), unique=True)
    unionid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # SOTER public keys are verified server-side; we store only fingerprints
    soter_key_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TradeDeal(Base):
    __tablename__ = "trade_deal"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenant.id"), index=True)
    state: Mapped[str] = mapped_column(String(32), default="created")  # graph phase
    lc_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    beneficiary: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str | None] = mapped_column(CHAR(3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Document(Base):
    __tablename__ = "document"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    deal_id: Mapped[str] = mapped_column(ForeignKey("trade_deal.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="unknown")
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str] = mapped_column(String(255))  # read-only object store key
    scan_status: Mapped[str] = mapped_column(String(16), default="pending")  # malware scan
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Rule(Base):
    """Bitemporal rule rows: event time = valid_from/valid_to; system time =
    recorded_at/superseded_at. `rules_in_force` picks the latest record whose
    validity interval contains the deal date (see app/rules/store.py)."""

    __tablename__ = "rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(String(64), index=True)
    jurisdiction: Mapped[str] = mapped_column(String(8), index=True)  # CN, BD, ...
    topic: Mapped[str] = mapped_column(String(64), index=True)  # vat_refund, ucp600, ...
    version: Mapped[str] = mapped_column(String(32))
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source_url: Mapped[str] = mapped_column(String(500))
    valid_from: Mapped[date] = mapped_column(Date())
    valid_to: Mapped[date | None] = mapped_column(Date(), nullable=True)  # None = open-ended
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FindingRow(Base):
    __tablename__ = "finding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deal_id: Mapped[str] = mapped_column(ForeignKey("trade_deal.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    check_id: Mapped[str] = mapped_column(String(64))
    rule_id: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(8), default="open")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_finding_deal_check", "deal_id", "check_id"),)


class FxQuoteRow(Base):
    __tablename__ = "fx_quote"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deal_id: Mapped[str] = mapped_column(ForeignKey("trade_deal.id"), index=True)
    route_id: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(64))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    sell_currency: Mapped[str] = mapped_column(CHAR(3))
    buy_currency: Mapped[str] = mapped_column(CHAR(3))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    net_minor: Mapped[int] = mapped_column(BigInteger)
    mid_rate_scaled: Mapped[int] = mapped_column(BigInteger)
    spread_bp: Mapped[int] = mapped_column(Integer)
    fee_minor: Mapped[int] = mapped_column(BigInteger)
    quoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEventRow(Base):
    """Append-only. UPDATE/DELETE revoked in db/init SQL (M1)."""

    __tablename__ = "audit_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    deal_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), index=True)
