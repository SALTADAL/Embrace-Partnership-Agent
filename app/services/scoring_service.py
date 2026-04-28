"""Scoring service — orchestrator for one POST /score request.

Responsibilities:
  1. Call the research agent.
  2. Hand its brief to the scoring agent (with research_quality flag).
  3. Compute total score and tier.
  4. Persist to SQLite via the repository.
  5. Build the API response payload.

Routers depend on :class:`ScoringService`, never on the agents directly,
so swapping in a stub for tests is a one-line dependency override.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.agents.research_agent import ResearchAgent, ResearchResult
from app.agents.scoring_agent import ScoreOutput, ScoringAgent
from app.config import Settings, get_settings
from app.data.repository import PartnershipRepository

logger = logging.getLogger(__name__)


# --- Public API result shape ------------------------------------------------


@dataclass
class ScoreRequest:
    """Internal-friendly mirror of the POST /score body."""

    organization_name: str
    website: str | None = None
    notes: str | None = None


# --- Helpers ----------------------------------------------------------------


def compute_tier(total_score: int) -> str:
    """Map a 0–100 total to the tier letter.

    Tier mapping per the rubric:
      * A = 80+
      * B = 60–79
      * C = 40–59
      * Pass = <40
    """

    if total_score >= 80:
        return "A"
    if total_score >= 60:
        return "B"
    if total_score >= 40:
        return "C"
    return "Pass"


def _score_to_dict(score: ScoreOutput) -> dict[str, Any]:
    """Flatten a :class:`ScoreOutput` into the API response shape."""

    dimensions = {
        "clinical_relevance": score.clinical_relevance.model_dump(),
        "mission_alignment": score.mission_alignment.model_dump(),
        "scale_and_reach": score.scale_and_reach.model_dump(),
        "decision_maker_accessibility": score.decision_maker_accessibility.model_dump(),
        "strategic_fit": score.strategic_fit.model_dump(),
    }
    total = sum(d["score"] for d in dimensions.values())
    return {
        "dimensions": dimensions,
        "total_score": total,
        "decision_makers": [dm.model_dump() for dm in score.decision_makers],
        "outreach_draft": score.outreach_draft,
    }


# --- Service ----------------------------------------------------------------


class ScoringService:
    """Orchestrates research + scoring + persistence."""

    def __init__(
        self,
        research_agent: ResearchAgent | None = None,
        scoring_agent: ScoringAgent | None = None,
        repository: PartnershipRepository | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Wire up agents and repository.

        All collaborators are injectable so tests can substitute fakes
        without touching the network.
        """

        self.settings = settings or get_settings()
        self.research_agent = research_agent or ResearchAgent(settings=self.settings)
        self.scoring_agent = scoring_agent or ScoringAgent(settings=self.settings)
        self.repository = repository or PartnershipRepository(self.settings.database_url)

    def score(self, request: ScoreRequest) -> dict[str, Any]:
        """Run the full pipeline and return the API payload.

        Never raises on transient agent failures — the research agent
        itself returns a degraded :class:`ResearchResult`. If the scoring
        agent fails after retries, we surface a 502-like dict so the
        router can translate to an HTTP error without crashing the API.
        """

        org = request.organization_name.strip()
        logger.info("score_request_start org=%s", org)

        research: ResearchResult = self.research_agent.research(
            organization_name=org,
            website=request.website,
            notes=request.notes,
        )

        try:
            score_output = self.scoring_agent.score(
                organization_name=org,
                research_summary=research.summary,
                notes=request.notes,
                research_quality=research.research_quality,
            )
        except Exception as exc:  # noqa: BLE001 — surface as structured error
            logger.error("scoring_failed org=%s error=%s", org, exc, exc_info=False)
            raise ScoringFailure(str(exc)) from exc

        flat = _score_to_dict(score_output)
        total = flat["total_score"]
        tier = compute_tier(total)

        scored_at = datetime.now(timezone.utc).isoformat()
        payload: dict[str, Any] = {
            "organization_name": org,
            "website": request.website,
            "total_score": total,
            "tier": tier,
            "dimensions": flat["dimensions"],
            "decision_makers": flat["decision_makers"],
            "outreach_draft": flat["outreach_draft"],
            "research_summary": research.summary,
            "research_quality": research.research_quality,
            "research_error": research.error,
            "scored_at": scored_at,
        }

        try:
            self.repository.save(
                organization_name=org,
                website=request.website,
                total_score=total,
                tier=tier,
                research_quality=research.research_quality,
                payload=payload,
            )
        except Exception as exc:  # noqa: BLE001 — log but still return result
            logger.error("persist_failed org=%s error=%s", org, exc, exc_info=False)

        logger.info("score_request_done org=%s tier=%s total=%d", org, tier, total)
        return payload


class ScoringFailure(RuntimeError):
    """Raised when the scoring agent ultimately fails.

    The research agent always degrades gracefully, but if Claude's
    structured output cannot be parsed across all retries we surface a
    dedicated exception that the router translates to HTTP 502.
    """
