"""Research agent — wraps Anthropic's native ``web_search`` tool.

Why a thin wrapper instead of a full LangChain ``AgentExecutor``? The
``web_search`` tool runs entirely server-side at Anthropic; the model
both decides when to search and consumes the results without any client
round-trips. There is no agent loop for us to manage. The wrapper here
exists to (a) apply retries with exponential back-off, (b) enforce a
hard timeout, and (c) translate failures into a structured fallback the
service layer can act on.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import anthropic
from anthropic import Anthropic
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings, get_settings
from app.prompts.research_prompt import RESEARCH_SYSTEM, build_research_prompt

logger = logging.getLogger(__name__)


@dataclass
class ResearchResult:
    """Output of one research run.

    Attributes:
        summary: The labeled prose brief produced by the model. When
            ``research_quality == "limited"`` this is a stub explaining
            that web research failed.
        research_quality: ``"full"`` if the model returned a real brief,
            ``"limited"`` if we fell back to name-only scoring.
        error: Optional human-readable error string when degraded.
    """

    summary: str
    research_quality: str
    error: str | None = None


class ResearchAgent:
    """Calls Claude with the ``web_search`` server tool enabled.

    Args:
        settings: Optional pre-built :class:`Settings` (used in tests).
            Falls back to the cached app settings.
        client: Optional pre-built :class:`anthropic.Anthropic` (used in
            tests with a mock).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        client: Anthropic | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        # Lazily allow client injection so tests can mock without env vars.
        self._client = client

    @property
    def client(self) -> Anthropic:
        """Return the underlying Anthropic SDK client, building if needed."""

        if self._client is None:
            self._client = Anthropic(api_key=self.settings.anthropic_api_key)
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(
            (
                anthropic.APIConnectionError,
                anthropic.APITimeoutError,
                anthropic.RateLimitError,
                anthropic.InternalServerError,
            )
        ),
        reraise=True,
    )
    def _call_claude(self, prompt: str) -> str:
        """Make one Claude request with the ``web_search`` tool enabled.

        Wrapped in tenacity for 3 attempts at 1s/2s/4s back-off. We only
        retry transient errors — schema/validation failures are surfaced
        immediately so the service layer can degrade gracefully.
        """

        response = self.client.with_options(
            timeout=self.settings.research_timeout_seconds,
        ).messages.create(
            model=self.settings.anthropic_model,
            max_tokens=2048,
            system=RESEARCH_SYSTEM,
            tools=[
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": self.settings.web_search_max_uses,
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        )
        return _extract_text(response)

    def research(
        self,
        organization_name: str,
        website: str | None = None,
        notes: str | None = None,
    ) -> ResearchResult:
        """Run the research agent for one organization.

        Returns a :class:`ResearchResult`. On failure (including hitting
        the retry cap) returns a degraded result with
        ``research_quality="limited"`` so the downstream scoring agent
        can still produce a conservative score.
        """

        prompt = build_research_prompt(organization_name, website, notes)
        try:
            text = self._call_claude(prompt)
            if not text.strip():
                # Model returned tool calls but no textual answer — treat
                # as limited rather than crashing the run.
                logger.warning(
                    "research_empty org=%s — falling back to limited",
                    organization_name,
                )
                return ResearchResult(
                    summary=f"Web research returned no content for {organization_name}.",
                    research_quality="limited",
                    error="empty_response",
                )
            logger.info("research_ok org=%s chars=%d", organization_name, len(text))
            return ResearchResult(summary=text, research_quality="full")
        except Exception as exc:  # noqa: BLE001 — graceful degrade by spec
            logger.error(
                "research_failed org=%s error=%s",
                organization_name,
                exc,
                exc_info=False,
            )
            return ResearchResult(
                summary=(
                    f"Research unavailable for {organization_name}; the scoring "
                    "agent will produce a conservative estimate from the name only."
                ),
                research_quality="limited",
                error=str(exc),
            )


def _extract_text(response: Any) -> str:
    """Pull plain text out of an Anthropic ``Message`` response.

    The response content is a list of blocks; for a web_search-enabled
    call the blocks include ``server_tool_use`` and
    ``web_search_tool_result`` interleaved with the model's ``text``.
    We only need the text.
    """

    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            parts.append(text)
    return "\n\n".join(parts).strip()
