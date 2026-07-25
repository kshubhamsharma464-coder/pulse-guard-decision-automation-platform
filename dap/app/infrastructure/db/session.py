"""Engine/session factory. One function, get_engine(url), so tests can
point it at sqlite:///:memory: while production points it at the real
Postgres DATABASE_URL -- the ORM models in models.py are identical either
way, only the dialect changes (see the .with_variant() calls there)."""

from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session


def get_engine(database_url: str, *, echo: bool = False, pool_size: int = 5, max_overflow: int = 10):
    kwargs = {"echo": echo}
    if not database_url.startswith("sqlite"):
        kwargs["pool_size"] = pool_size
        kwargs["max_overflow"] = max_overflow
    return create_engine(database_url, **kwargs)


def get_sessionmaker(engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: sessionmaker):
    session: Session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
