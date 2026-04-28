"""Repository layer — encapsulates all SQLAlchemy session handling.

Routers and services never touch sessions directly; they go through
:class:`PartnershipRepository`. This keeps the data access surface small
and easy to mock in tests.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

from sqlalchemy import create_engine, desc, select
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, Partnership

logger = logging.getLogger(__name__)


class PartnershipRepository:
    """CRUD operations for :class:`Partnership`.

    The repository owns its own engine and session factory. SQLite needs
    ``check_same_thread=False`` so that FastAPI (which serves requests
    on different threads) can share the same connection pool safely.
    """

    def __init__(self, database_url: str) -> None:
        """Create the engine, ensure tables exist.

        Args:
            database_url: SQLAlchemy URL, e.g. ``sqlite:///./embrace.db``.
        """

        connect_args: dict[str, Any] = {}
        if database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        self.engine = create_engine(
            database_url,
            connect_args=connect_args,
            future=True,
        )
        self._SessionLocal = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
        Base.metadata.create_all(self.engine)

    @contextmanager
    def _session(self) -> Iterator[Session]:
        """Yield a session and guarantee it is closed.

        Commits on success, rolls back on exception, always closes.
        """

        session = self._SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def save(
        self,
        organization_name: str,
        website: str | None,
        total_score: int,
        tier: str,
        research_quality: str,
        payload: dict[str, Any],
    ) -> int:
        """Persist a scored partnership.

        Returns:
            The auto-generated row id.
        """

        with self._session() as session:
            row = Partnership(
                organization_name=organization_name,
                website=website,
                total_score=total_score,
                tier=tier,
                research_quality=research_quality,
                payload=payload,
                scored_at=datetime.utcnow(),
            )
            session.add(row)
            session.flush()
            row_id = row.id
            logger.info(
                "partnership_saved id=%s org=%s tier=%s score=%s",
                row_id,
                organization_name,
                tier,
                total_score,
            )
            return row_id

    def list(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Return a page of scored partnerships, newest first."""

        with self._session() as session:
            stmt = (
                select(Partnership)
                .order_by(desc(Partnership.scored_at))
                .limit(limit)
                .offset(offset)
            )
            rows = session.execute(stmt).scalars().all()
            return [self._serialize(r) for r in rows]

    def all(self) -> list[dict[str, Any]]:
        """Return every scored partnership (used for CSV export)."""

        with self._session() as session:
            stmt = select(Partnership).order_by(desc(Partnership.scored_at))
            rows = session.execute(stmt).scalars().all()
            return [self._serialize(r) for r in rows]

    @staticmethod
    def _serialize(row: Partnership) -> dict[str, Any]:
        """Translate a SQLAlchemy row into a plain dict for the API."""

        return {
            "id": row.id,
            "organization_name": row.organization_name,
            "website": row.website,
            "total_score": row.total_score,
            "tier": row.tier,
            "research_quality": row.research_quality,
            "payload": row.payload,
            "scored_at": row.scored_at.isoformat() + "Z",
        }
