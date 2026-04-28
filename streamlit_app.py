"""Streamlit demo for the Embrace Partnership Scoring Agent.

Run:
    streamlit run streamlit_app.py

The UI calls :func:`app.main.score_one` directly (in-process), so a
reviewer only needs the one command. To call the FastAPI service over
HTTP instead, set ``EMBRACE_API_URL`` in the environment.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx
import streamlit as st

from app.main import score_one

# --- Page config -----------------------------------------------------------

st.set_page_config(
    page_title="Embrace Partnership Scoring Agent",
    page_icon="🤝",
    layout="wide",
)

API_URL = os.environ.get("EMBRACE_API_URL", "").strip()


# --- Styling ---------------------------------------------------------------


TIER_COLORS = {
    "A": "#1f9d55",  # green
    "B": "#2563eb",  # blue
    "C": "#d97706",  # amber
    "Pass": "#dc2626",  # red
}


def tier_badge(tier: str, score: int) -> str:
    """Return an HTML span styled with the tier's color."""

    color = TIER_COLORS.get(tier, "#475569")
    return (
        f"<span style='display:inline-block;padding:6px 14px;border-radius:9999px;"
        f"background:{color};color:white;font-weight:700;font-size:18px;"
        f"letter-spacing:0.5px;'>Tier {tier} &nbsp;·&nbsp; {score}/100</span>"
    )


# --- Scoring backends ------------------------------------------------------


def run_scoring(
    organization_name: str,
    website: str | None,
    notes: str | None,
) -> dict[str, Any]:
    """Score one org via the in-process service or remote API."""

    if API_URL:
        with httpx.Client(timeout=120) as client:
            r = client.post(
                f"{API_URL.rstrip('/')}/score",
                json={
                    "organization_name": organization_name,
                    "website": website or None,
                    "notes": notes or None,
                },
            )
            r.raise_for_status()
            return r.json()
    return score_one(organization_name=organization_name, website=website, notes=notes)


# --- UI helpers ------------------------------------------------------------


EXAMPLES = [
    {
        "label": "American Cancer Society",
        "name": "American Cancer Society",
        "website": "https://www.cancer.org",
    },
    {
        "label": "CaringBridge",
        "name": "CaringBridge",
        "website": "https://www.caringbridge.org",
    },
    {
        "label": "Make-A-Wish Foundation",
        "name": "Make-A-Wish Foundation",
        "website": "https://wish.org",
    },
]


def _set_inputs(name: str, website: str) -> None:
    """Populate the form inputs without triggering an automatic run."""

    st.session_state["organization_name"] = name
    st.session_state["website"] = website


# --- Layout ----------------------------------------------------------------


st.title("🤝 Embrace Partnership Scoring Agent")
st.caption(
    "Type an organization name (or click an example), then click "
    "**Score Partnership**. The agent researches the org and returns a "
    "0–100 fit score, decision-makers, and a draft outreach email."
)

with st.container(border=True):
    st.subheader("Try an example")
    cols = st.columns(len(EXAMPLES))
    for col, ex in zip(cols, EXAMPLES):
        with col:
            if st.button(ex["label"], use_container_width=True, key=f"ex_{ex['label']}"):
                _set_inputs(ex["name"], ex["website"])

with st.form("score_form"):
    organization_name = st.text_input(
        "Organization name",
        key="organization_name",
        placeholder="e.g. American Cancer Society",
    )
    website = st.text_input(
        "Website (optional)",
        key="website",
        placeholder="https://...",
    )
    notes = st.text_area(
        "Notes (optional)",
        key="notes",
        placeholder="Anything to bias the scoring? Recent intro, pilot interest, etc.",
        height=80,
    )
    submitted = st.form_submit_button("Score Partnership", type="primary")


# --- Run ----------------------------------------------------------------


def render_results(result: dict[str, Any]) -> None:
    """Render the structured score in a friendly layout."""

    tier = result["tier"]
    score = result["total_score"]
    quality = result.get("research_quality", "full")

    badge_col, header_col = st.columns([1, 3])
    with badge_col:
        st.markdown(tier_badge(tier, score), unsafe_allow_html=True)
    with header_col:
        st.markdown(f"### {result['organization_name']}")
        if quality == "limited":
            st.warning(
                "Web research was unavailable for this org — score is based on the "
                "organization name only and is conservative."
            )

    st.divider()

    st.subheader("Score breakdown")
    dim_cols = st.columns(5)
    pretty_names = {
        "clinical_relevance": "Clinical Relevance",
        "mission_alignment": "Mission Alignment",
        "scale_and_reach": "Scale & Reach",
        "decision_maker_accessibility": "Decision-Maker Access",
        "strategic_fit": "Strategic Fit",
    }
    for col, (key, name) in zip(dim_cols, pretty_names.items()):
        with col:
            d = result["dimensions"][key]
            st.metric(label=name, value=f"{d['score']}/20")

    for key, name in pretty_names.items():
        with st.expander(f"{name} — rationale", expanded=False):
            st.write(result["dimensions"][key]["rationale"])

    st.divider()
    st.subheader("Decision-maker suggestions")
    for dm in result["decision_makers"]:
        with st.container(border=True):
            st.markdown(f"**{dm['title']}**")
            st.write(dm["rationale"])
            st.code(dm["linkedin_query"], language="text")

    st.divider()
    st.subheader("Draft outreach email")
    st.info("This is an AI-generated draft. Always review before sending.")
    st.text_area(
        "Outreach draft",
        value=result["outreach_draft"],
        height=260,
        label_visibility="collapsed",
    )

    st.divider()
    with st.expander("Research summary (raw)"):
        st.write(result.get("research_summary") or "(no summary)")

    with st.expander("Full JSON response"):
        st.code(json.dumps(result, indent=2, default=str), language="json")


if submitted:
    if not organization_name or len(organization_name.strip()) < 2:
        st.error("Please enter an organization name (2+ characters).")
    else:
        progress = st.empty()
        try:
            progress.info("🔍 Researching org…")
            time.sleep(0.1)  # let the message render before the long call
            result = run_scoring(
                organization_name=organization_name.strip(),
                website=(website or "").strip() or None,
                notes=(notes or "").strip() or None,
            )
            progress.info("⚖️  Scoring fit…")
            time.sleep(0.1)
            progress.info("✍️  Drafting outreach…")
            time.sleep(0.1)
            progress.empty()
            render_results(result)
        except Exception as exc:  # noqa: BLE001 — surface to user
            progress.empty()
            st.error(f"Scoring failed: {exc}")
            st.caption(
                "Check that ANTHROPIC_API_KEY is set in your .env and that "
                "you have network access. The API still degrades gracefully "
                "and will mark the run research_quality='limited' if web "
                "search is unavailable."
            )

st.caption(
    "Embrace Partnership Scoring Agent · Built by Atlas Lad for the Innovate "
    "Carolina fellowship application."
)
