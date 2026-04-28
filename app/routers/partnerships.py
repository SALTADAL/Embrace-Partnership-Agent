"""HTTP routes for the partnership scoring API."""

from __future__ import annotations

import csv
import io
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.services.scoring_service import (
    ScoreRequest,
    ScoringFailure,
    ScoringService,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["partnerships"])


# --- Request / response schemas --------------------------------------------


class ScoreBody(BaseModel):
    """Validated body for POST /score."""

    organization_name: str = Field(..., min_length=2, max_length=255)
    website: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=2000)


class DimensionResponse(BaseModel):
    """Per-dimension API output."""

    score: int = Field(..., ge=0, le=20)
    rationale: str


class DecisionMakerResponse(BaseModel):
    """Decision-maker suggestion in the API output."""

    title: str
    rationale: str
    linkedin_query: str


class ScoreResponse(BaseModel):
    """Full POST /score response."""

    organization_name: str
    total_score: int
    tier: str
    dimensions: dict[str, DimensionResponse]
    decision_makers: list[DecisionMakerResponse]
    outreach_draft: str
    research_summary: str
    research_quality: str
    scored_at: str


class PartnershipListItem(BaseModel):
    """Lightweight row for GET /partnerships."""

    id: int
    organization_name: str
    website: Optional[str] = None
    total_score: int
    tier: str
    research_quality: str
    scored_at: str


# --- Dependency injection ---------------------------------------------------


_service_singleton: ScoringService | None = None


def get_scoring_service() -> ScoringService:
    """Return a process-level :class:`ScoringService`.

    Tests override this via ``app.dependency_overrides`` to inject a
    stub that does not call the network.
    """

    global _service_singleton
    if _service_singleton is None:
        _service_singleton = ScoringService()
    return _service_singleton


# --- Routes ----------------------------------------------------------------


@router.post(
    "/score",
    response_model=ScoreResponse,
    status_code=status.HTTP_200_OK,
    summary="Score an organization as a potential Embrace partner.",
)
def score_organization(
    body: ScoreBody,
    service: ScoringService = Depends(get_scoring_service),
) -> dict[str, Any]:
    """Run the full research + scoring + outreach pipeline."""

    try:
        return service.score(
            ScoreRequest(
                organization_name=body.organization_name,
                website=body.website,
                notes=body.notes,
            )
        )
    except ScoringFailure as exc:
        # Scoring agent failed after retries — return 502 Bad Gateway so
        # callers know it was an upstream issue, not a bad request.
        logger.error("score_endpoint_502 org=%s err=%s", body.organization_name, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Scoring agent failed: {exc}",
        ) from exc
    except Exception as exc:  # noqa: BLE001 — never crash the API
        logger.exception("score_endpoint_500 org=%s", body.organization_name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while scoring organization.",
        ) from exc


@router.get(
    "/partnerships",
    response_model=list[PartnershipListItem],
    summary="List previously scored organizations (newest first).",
)
def list_partnerships(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: ScoringService = Depends(get_scoring_service),
) -> list[dict[str, Any]]:
    """Paginate through the SQLite store of scored orgs."""

    rows = service.repository.list(limit=limit, offset=offset)
    # The repository returns the full payload; we slim it for the list view.
    return [
        {
            "id": r["id"],
            "organization_name": r["organization_name"],
            "website": r["website"],
            "total_score": r["total_score"],
            "tier": r["tier"],
            "research_quality": r["research_quality"],
            "scored_at": r["scored_at"],
        }
        for r in rows
    ]


@router.get(
    "/partnerships/export",
    summary="Download all scored organizations as CSV.",
    response_class=Response,
)
def export_partnerships(
    service: ScoringService = Depends(get_scoring_service),
) -> Response:
    """Stream a CSV dump of every row in the partnerships table."""

    rows = service.repository.all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "organization_name",
            "website",
            "total_score",
            "tier",
            "research_quality",
            "scored_at",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r["id"],
                r["organization_name"],
                r.get("website") or "",
                r["total_score"],
                r["tier"],
                r["research_quality"],
                r["scored_at"],
            ]
        )

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="embrace_partnerships.csv"'},
    )
