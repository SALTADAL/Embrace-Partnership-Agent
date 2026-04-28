"""Shared pytest fixtures.

These fixtures build a fully wired :class:`ScoringService` whose two
agents are *stubs* — no network, no API key required. The stubs emit
deterministic data shaped like the real agents' output so we can test
the full FastAPI route surface without hitting Anthropic.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest

from app.agents.research_agent import ResearchResult
from app.agents.scoring_agent import (
    DecisionMaker,
    DimensionScore,
    ScoreOutput,
)
from app.data.repository import PartnershipRepository
from app.services.scoring_service import ScoringService

# --- Stub agents -----------------------------------------------------------


class StubResearchAgent:
    """Returns a deterministic :class:`ResearchResult`.

    If the org name contains "fail" we return a degraded result so we
    can test the limited-research path without hitting an exception.
    """

    def research(
        self,
        organization_name: str,
        website: str | None = None,
        notes: str | None = None,
    ) -> ResearchResult:
        if "fail" in organization_name.lower():
            return ResearchResult(
                summary=f"(stub) research unavailable for {organization_name}",
                research_quality="limited",
                error="stub_failure",
            )
        return ResearchResult(
            summary=(
                f"(stub) {organization_name} is a healthcare nonprofit serving "
                "patients with serious illness across multiple states."
            ),
            research_quality="full",
        )


class StubScoringAgent:
    """Returns a deterministic :class:`ScoreOutput` driven by org name.

    Heuristic so different test inputs produce different tiers:
      - 'cancer' or 'caringbridge' in name => Tier A (~88)
      - 'wish' in name                     => Tier B (~70)
      - 'plumbing' or 'fail' in name       => Tier Pass (~24)
      - everything else                    => Tier C (~50)
    """

    def score(
        self,
        organization_name: str,
        research_summary: str,
        notes: str | None = None,
        research_quality: str = "full",
    ) -> ScoreOutput:
        name_l = organization_name.lower()
        if "cancer" in name_l or "caringbridge" in name_l:
            scores = (20, 18, 20, 15, 15)
        elif "wish" in name_l:
            scores = (16, 14, 16, 12, 12)
        elif "plumbing" in name_l or "fail" in name_l:
            scores = (4, 4, 6, 4, 6)
        else:
            scores = (12, 10, 10, 8, 10)

        cr, ma, sr, dma, sf = scores

        return ScoreOutput(
            clinical_relevance=DimensionScore(
                score=cr, rationale=f"Stub rationale for clinical relevance of {organization_name}."
            ),
            mission_alignment=DimensionScore(
                score=ma, rationale=f"Stub rationale for mission alignment of {organization_name}."
            ),
            scale_and_reach=DimensionScore(
                score=sr, rationale=f"Stub rationale for scale of {organization_name}."
            ),
            decision_maker_accessibility=DimensionScore(
                score=dma,
                rationale=f"Stub rationale for decision-maker access at {organization_name}.",
            ),
            strategic_fit=DimensionScore(
                score=sf, rationale=f"Stub rationale for strategic fit of {organization_name}."
            ),
            decision_makers=[
                DecisionMaker(
                    title="VP, Patient Support",
                    rationale="Owns family-facing programs.",
                    linkedin_query=f'"VP Patient Support" "{organization_name}" site:linkedin.com/in',
                ),
                DecisionMaker(
                    title="Director, Caregiver Programs",
                    rationale="Runs caregiver-facing initiatives.",
                    linkedin_query=f'"Director Caregiver" "{organization_name}" site:linkedin.com/in',
                ),
                DecisionMaker(
                    title="Chief Mission Officer",
                    rationale="Strategic owner for mission-aligned partnerships.",
                    linkedin_query=f'"Chief Mission Officer" "{organization_name}" site:linkedin.com/in',
                ),
            ],
            outreach_draft=(
                f"[DRAFT] Hi team — I'm Atlas, founder of Embrace. We help "
                f"families create video montages for patients facing serious "
                f"illness. Saw {organization_name} doing meaningful work and "
                f"wanted to explore a partnership. Open to a 20-min call?\n\n"
                "Atlas Lad, Founder, Embrace"
            ),
        )


# --- Fixtures --------------------------------------------------------------


@pytest.fixture()
def tmp_db_url() -> str:
    """SQLite URL pointing at a fresh tempfile.

    Using a file (not ``:memory:``) keeps the same connection visible to
    both the FastAPI test client and direct repository checks.
    """

    fd, path = tempfile.mkstemp(suffix=".db", prefix="embrace_test_")
    os.close(fd)
    yield f"sqlite:///{path}"
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture()
def repository(tmp_db_url: str) -> PartnershipRepository:
    return PartnershipRepository(tmp_db_url)


@pytest.fixture()
def stub_service(repository: PartnershipRepository) -> ScoringService:
    """A :class:`ScoringService` with both agents stubbed."""

    return ScoringService(
        research_agent=StubResearchAgent(),
        scoring_agent=StubScoringAgent(),
        repository=repository,
    )


@pytest.fixture()
def api_client(stub_service: ScoringService) -> Any:
    """FastAPI TestClient with the scoring service overridden."""

    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.partnerships import get_scoring_service

    app.dependency_overrides[get_scoring_service] = lambda: stub_service
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
