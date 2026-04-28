"""FastAPI application factory.

Run locally with:

    uvicorn app.main:app --reload --port 8000

The Streamlit demo (``streamlit_app.py``) imports the ``score_one``
helper here so the UI can call the scoring service in-process without
spinning up a second server.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI

from app.config import get_settings
from app.routers.partnerships import router as partnerships_router
from app.services.scoring_service import ScoreRequest, ScoringService


def _configure_logging(level: str) -> None:
    """Configure structured-ish logging for the whole app.

    We use a single, simple format including timestamp, level, logger
    name, and message. Per the spec, every important log line in the
    services/agents includes the org name and timestamp.
    """

    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )


def create_app() -> FastAPI:
    """Build and return the FastAPI application instance."""

    settings = get_settings()
    _configure_logging(settings.log_level)

    app = FastAPI(
        title="Embrace Partnership Scoring Agent",
        description=(
            "Scores healthcare organizations as potential Embrace partners "
            "using a research + scoring agent powered by Anthropic Claude."
        ),
        version="0.1.0",
    )

    app.include_router(partnerships_router)

    @app.get("/healthz", tags=["meta"], summary="Liveness probe.")
    def healthz() -> dict[str, str]:
        """Return a tiny payload so load balancers know the API is up."""

        return {"status": "ok"}

    return app


app = create_app()


# --- In-process helper for the Streamlit demo -------------------------------


_inproc_service: ScoringService | None = None


def score_one(
    organization_name: str,
    website: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Score one organization without going over HTTP.

    Used by ``streamlit_app.py`` so the demo runs from a single
    ``streamlit run`` command. Builds a process-level ScoringService
    on first call and reuses it.
    """

    global _inproc_service
    if _inproc_service is None:
        _inproc_service = ScoringService()
    return _inproc_service.score(
        ScoreRequest(
            organization_name=organization_name,
            website=website,
            notes=notes,
        )
    )
