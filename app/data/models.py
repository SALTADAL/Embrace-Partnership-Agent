"""SQLAlchemy ORM models.

Each scored organization is one row in ``partnerships``. The full agent
response is stored as JSON in the ``payload`` column so the API can
return it verbatim later — this also makes schema migrations cheap when
the rubric or output format evolves.
"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Partnership(Base):
    """One scored organization.

    Columns are intentionally a mix of structured (for queryability) and
    JSON blob (for flexibility). The structured fields — ``total_score``
    and ``tier`` — are what the list/export endpoints display, while
    ``payload`` holds the full breakdown for replay.
    """

    __tablename__ = "partnerships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_name = Column(String(255), index=True, nullable=False)
    website = Column(String(500), nullable=True)
    total_score = Column(Integer, nullable=False)
    tier = Column(String(8), nullable=False)
    research_quality = Column(String(16), nullable=False, default="full")
    payload = Column(JSON, nullable=False)
    scored_at = Column(DateTime, nullable=False, default=datetime.utcnow)
