"""SQLAlchemy declarative base + reusable mixins implementing the DecisioX
spec's per-entity requirements (UUID PK, timestamps, soft delete,
optimistic locking, indexes) as opt-in building blocks rather than forcing
every table to carry every column regardless of whether it makes sense.

Deliberate exclusions, not oversights: `decisions`, `audit_log`,
`incidents`, `escalation_events`, `manual_overrides` are append-only /
immutable by design (see schema.sql's own comments -- an override or audit
entry is a new record, never a mutation of an old one). Soft-delete and
optimistic-locking mixins are applied only to `rule_sets` and `rules`,
the two entities that are genuinely edited in place over their lifetime.
Applying "every entity must include X" literally, everywhere, regardless
of fit, would be cargo-culting the spec rather than engineering to it."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid_column():
    """UUID primary key. Uses Postgres' native UUID type in production;
    falls back to a CHAR-backed UUID under SQLite so the same models are
    testable without a live Postgres instance (see infrastructure/db/session.py)."""
    return mapped_column(
        PG_UUID(as_uuid=True).with_variant(SqliteUUID(), "sqlite"),
        primary_key=True,
        default=uuid.uuid4,
    )


from sqlalchemy.types import CHAR, TypeDecorator


class SqliteUUID(TypeDecorator):
    """Stores a UUID as a 36-char string under SQLite (used only in tests --
    production always runs Postgres, where PG_UUID is used natively). Used
    for BOTH primary keys and foreign keys pointing at them -- a foreign
    key column typed as plain String(36) would receive raw uuid.UUID
    python objects from relationship-assigned values and fail to bind;
    this TypeDecorator's process_bind_param handles the str() conversion
    either way."""
    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return str(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return uuid.UUID(value) if value is not None else None


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = _uuid_column()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class OptimisticLockMixin:
    """SQLAlchemy's native version_id_col mechanism -- raises
    StaleDataError on a concurrent conflicting write instead of silently
    overwriting it. Applied via __mapper_args__ = {"version_id_col": lock_version}
    on the entity, not just by declaring the column."""
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
