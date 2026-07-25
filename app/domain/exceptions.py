"""Domain-level exceptions shared across use cases and repositories.
Plain Python, zero framework imports (no SQLAlchemy, no FastAPI) -- an
infrastructure adapter (e.g. PostgresRulePackRepository) translates its
own framework-specific error (sqlalchemy.orm.exc.StaleDataError) into
this before it crosses the repository interface boundary; the interfaces
layer (a FastAPI exception handler, main.py) translates this into an HTTP
response. Neither the domain nor the application layer ever needs to know
what StaleDataError or HTTPException even are."""


class ConcurrentModificationError(RuntimeError):
    """Raised when a write loses a race against another write to the same
    row -- PostgreSQL's optimistic-locking guard (RuleSetORM.lock_version,
    docs/policy-platform.md's concurrency section) caught two writers that
    both read the same version and both tried to commit a change based on
    it. The caller lost the race, not made an invalid request -- callers
    should treat this as "reload and retry," not "fix your input,"
    conventionally surfaced as HTTP 409 Conflict rather than 400."""
