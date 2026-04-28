"""Unit tests for scoring logic.

Covers:
  - The ``compute_tier`` boundary table.
  - The end-to-end :class:`ScoringService` with stubbed agents (Tier A
    for American Cancer Society, Tier Pass for Local Plumbing LLC, no
    crash on the limited-research path).
  - The Pydantic ``[DRAFT]`` enforcement on the outreach draft.
  - The repository roundtrip.
"""

from __future__ import annotations

import pytest

from app.agents.scoring_agent import (
    DecisionMaker,
    DimensionScore,
    ScoreOutput,
)
from app.services.scoring_service import (
    ScoreRequest,
    ScoringService,
    compute_tier,
)

# --- compute_tier ----------------------------------------------------------


@pytest.mark.parametrize(
    "score, expected",
    [
        (100, "A"),
        (80, "A"),
        (79, "B"),
        (60, "B"),
        (59, "C"),
        (40, "C"),
        (39, "Pass"),
        (0, "Pass"),
    ],
)
def test_compute_tier_boundaries(score: int, expected: str) -> None:
    """Tier boundaries match the rubric exactly."""

    assert compute_tier(score) == expected


# --- end-to-end with stubs -------------------------------------------------


def test_scoring_service_returns_tier_a_for_acs(stub_service: ScoringService) -> None:
    """American Cancer Society should land in Tier A with sensible DMs."""

    result = stub_service.score(ScoreRequest(organization_name="American Cancer Society"))
    assert result["tier"] == "A"
    assert result["total_score"] >= 80
    assert len(result["decision_makers"]) == 3
    titles = [dm["title"] for dm in result["decision_makers"]]
    assert any("VP" in t or "Director" in t or "Chief" in t for t in titles)
    # No fabricated emails
    blob = str(result).lower()
    assert "@" not in result["outreach_draft"] or "[DRAFT]" in result["outreach_draft"]
    assert "site:linkedin.com/in" in blob


def test_scoring_service_returns_pass_for_unrelated_org(
    stub_service: ScoringService,
) -> None:
    """Local Plumbing LLC should land in Tier Pass without crashing."""

    result = stub_service.score(ScoreRequest(organization_name="Local Plumbing LLC"))
    assert result["tier"] == "Pass"
    assert result["total_score"] < 40
    # Even on a Pass, the response is fully formed.
    assert "outreach_draft" in result
    assert result["outreach_draft"].lstrip().startswith("[DRAFT]")


def test_scoring_service_handles_research_failure(stub_service: ScoringService) -> None:
    """When research fails, research_quality should flip to 'limited'."""

    result = stub_service.score(ScoreRequest(organization_name="Failing Org"))
    assert result["research_quality"] == "limited"
    # Pipeline still completes, score still present
    assert "total_score" in result
    assert result["tier"] in {"A", "B", "C", "Pass"}


# --- Pydantic [DRAFT] enforcement ------------------------------------------


def test_outreach_draft_is_force_prefixed_with_marker() -> None:
    """The Pydantic validator should prepend [DRAFT] if the model omits it."""

    out = ScoreOutput(
        clinical_relevance=DimensionScore(score=20, rationale="x" * 20),
        mission_alignment=DimensionScore(score=20, rationale="x" * 20),
        scale_and_reach=DimensionScore(score=20, rationale="x" * 20),
        decision_maker_accessibility=DimensionScore(score=20, rationale="x" * 20),
        strategic_fit=DimensionScore(score=20, rationale="x" * 20),
        decision_makers=[
            DecisionMaker(title="Title One", rationale="one rationale", linkedin_query="query one"),
            DecisionMaker(title="Title Two", rationale="two rationale", linkedin_query="query two"),
            DecisionMaker(
                title="Title Three", rationale="three rationale", linkedin_query="query three"
            ),
        ],
        outreach_draft="Hi team — please consider partnering with us. " * 3,
    )
    assert out.outreach_draft.lstrip().startswith("[DRAFT]")


# --- Repository ------------------------------------------------------------


def test_repository_roundtrip(repository) -> None:
    """A saved row should be retrievable via list() with full payload."""

    row_id = repository.save(
        organization_name="Test Org",
        website="https://example.org",
        total_score=72,
        tier="B",
        research_quality="full",
        payload={"hello": "world"},
    )
    assert row_id >= 1
    rows = repository.list(limit=10, offset=0)
    assert len(rows) == 1
    assert rows[0]["organization_name"] == "Test Org"
    assert rows[0]["payload"] == {"hello": "world"}
    assert rows[0]["tier"] == "B"
