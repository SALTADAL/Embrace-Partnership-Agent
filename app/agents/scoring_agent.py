"""Scoring agent — LangChain ChatAnthropic with Pydantic structured output.

Why LangChain here? Because LangChain's ``with_structured_output`` makes
the Pydantic schema the contract: the model is forced to return JSON
that parses into our :class:`ScoreOutput`, and we get retry/parsing for
free. The research agent doesn't use this because the ``web_search``
tool is server-side at Anthropic and the simpler Anthropic SDK is the
right ergonomics there.
"""

from __future__ import annotations

import logging
from typing import List

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings, get_settings
from app.prompts.scoring_prompt import SCORING_SYSTEM, build_scoring_prompt

logger = logging.getLogger(__name__)


class DimensionScore(BaseModel):
    """One rubric dimension."""

    score: int = Field(..., ge=0, le=20, description="Integer 0–20 inclusive.")
    rationale: str = Field(
        ...,
        min_length=10,
        description="Two-sentence justification grounded in the research brief.",
    )


class DecisionMaker(BaseModel):
    """One suggested decision-maker.

    No personal email or phone is allowed — the rubric explicitly bars
    fabrication. Only a role title and a LinkedIn search query.
    """

    title: str = Field(..., min_length=2, description="Role title, e.g. 'VP, Patient Support'.")
    rationale: str = Field(..., min_length=10, description="Why this role owns partnerships.")
    linkedin_query: str = Field(
        ...,
        min_length=4,
        description=(
            "A LinkedIn search query string. Conventional form: "
            '"<title>" "<organization>" site:linkedin.com/in'
        ),
    )


class ScoreOutput(BaseModel):
    """Full structured output of the scoring agent."""

    clinical_relevance: DimensionScore
    mission_alignment: DimensionScore
    scale_and_reach: DimensionScore
    decision_maker_accessibility: DimensionScore
    strategic_fit: DimensionScore
    decision_makers: List[DecisionMaker] = Field(..., min_length=3, max_length=3)
    outreach_draft: str = Field(..., min_length=50)

    @field_validator("outreach_draft")
    @classmethod
    def _must_be_marked_draft(cls, v: str) -> str:
        """Enforce the [DRAFT] prefix so an outreach is never auto-sent."""

        if not v.lstrip().startswith("[DRAFT]"):
            # Don't crash; prepend so the human reviewer still sees the body.
            return "[DRAFT] " + v.lstrip()
        return v


class ScoringAgent:
    """Wraps a ChatAnthropic LLM with structured output for the rubric.

    The LangChain runnable enforces our Pydantic schema. We add a tenacity
    retry layer for transient API hiccups; structural failures bubble up
    so the service layer can fall back to a deterministic stub if needed.
    """

    def __init__(self, settings: Settings | None = None, llm: ChatAnthropic | None = None):
        self.settings = settings or get_settings()
        self._llm = llm

    @property
    def llm(self) -> ChatAnthropic:
        """Return the underlying ChatAnthropic, building if needed."""

        if self._llm is None:
            self._llm = ChatAnthropic(
                model=self.settings.anthropic_model,
                api_key=self.settings.anthropic_api_key,
                max_tokens=2048,
                timeout=self.settings.scoring_timeout_seconds,
                max_retries=0,  # we control retries via tenacity
            )
        return self._llm

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _call(
        self,
        organization_name: str,
        research_summary: str,
        notes: str | None,
        research_quality: str,
    ) -> ScoreOutput:
        """Run one structured-output Claude call and validate."""

        structured_llm = self.llm.with_structured_output(ScoreOutput)
        messages = [
            SystemMessage(content=SCORING_SYSTEM),
            HumanMessage(
                content=build_scoring_prompt(
                    organization_name=organization_name,
                    research_summary=research_summary,
                    notes=notes,
                    research_quality=research_quality,
                )
            ),
        ]
        result = structured_llm.invoke(messages)
        # `with_structured_output` may return a dict on some versions; coerce.
        if isinstance(result, dict):
            result = ScoreOutput.model_validate(result)
        return result

    def score(
        self,
        organization_name: str,
        research_summary: str,
        notes: str | None = None,
        research_quality: str = "full",
    ) -> ScoreOutput:
        """Public entry point.

        Args:
            organization_name: Org being scored.
            research_summary: Brief from the research agent.
            notes: Optional operator notes carried from the request.
            research_quality: ``"full"`` or ``"limited"``.

        Returns:
            A validated :class:`ScoreOutput`.
        """

        logger.info("scoring_start org=%s quality=%s", organization_name, research_quality)
        out = self._call(organization_name, research_summary, notes, research_quality)
        logger.info(
            "scoring_done org=%s total=%d",
            organization_name,
            sum(
                getattr(out, field).score
                for field in (
                    "clinical_relevance",
                    "mission_alignment",
                    "scale_and_reach",
                    "decision_maker_accessibility",
                    "strategic_fit",
                )
            ),
        )
        return out
