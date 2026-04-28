"""Standalone outreach-prompt helpers.

In production we generate the outreach draft inside the scoring agent's
structured output (one Claude call), but this module exists so future
work — e.g. regenerating an outreach email with a different tone — can
hit a focused prompt without re-running the full scoring chain.
"""

OUTREACH_SYSTEM = """You are Atlas Lad, founder of Embrace, drafting one warm, founder-direct outreach email to a prospective partner organization. The email is a DRAFT only — it will be reviewed by a human before sending.

Voice rules:
- Warm but professional. Conversational, not formal.
- Specific in the opening (reference one thing from the org's recent work or mission).
- One clear ask: a 20-minute exploratory call.
- 150 words, hard cap.
- Sign with: "Atlas Lad, Founder, Embrace".
- The very first token of the email body must be the literal string [DRAFT] so it is clearly never auto-sent."""


def build_outreach_prompt(
    organization_name: str,
    research_summary: str,
    target_role: str | None = None,
) -> str:
    """Build the outreach-only user prompt.

    Args:
        organization_name: Org we're emailing.
        research_summary: Brief from the research agent — used to ground
            the opener in real, specific facts.
        target_role: Optional role title to address (e.g. ``"VP, Patient
            Support"``). If omitted, the email opens with "Hi there,".

    Returns:
        The user-message string for the outreach draft prompt.
    """

    addressee = f"the {target_role}" if target_role else "the partnerships team"
    parts = [
        f"Draft a 150-word outreach email to {addressee} at **{organization_name}**.",
        "Open with a specific reference to one thing in the brief below.",
        "Research brief:\n\n" + research_summary,
        "Remember: start the body with the literal token [DRAFT].",
    ]
    return "\n\n".join(parts)
