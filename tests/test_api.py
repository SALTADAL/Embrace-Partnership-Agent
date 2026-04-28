"""API contract tests using FastAPI's TestClient with a stub service."""

from __future__ import annotations


def test_healthz(api_client) -> None:
    """The liveness probe should return 200/ok."""

    r = api_client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_post_score_full_contract(api_client) -> None:
    """POST /score must return every field in the documented contract."""

    r = api_client.post(
        "/score",
        json={"organization_name": "American Cancer Society"},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Required top-level keys
    for key in (
        "organization_name",
        "total_score",
        "tier",
        "dimensions",
        "decision_makers",
        "outreach_draft",
        "research_summary",
        "research_quality",
        "scored_at",
    ):
        assert key in body, f"missing key {key}"

    # Tier comes out of {A,B,C,Pass}
    assert body["tier"] in {"A", "B", "C", "Pass"}

    # Dimensions: five named keys, each with score (0–20) + rationale.
    expected_dims = {
        "clinical_relevance",
        "mission_alignment",
        "scale_and_reach",
        "decision_maker_accessibility",
        "strategic_fit",
    }
    assert set(body["dimensions"].keys()) == expected_dims
    for d in body["dimensions"].values():
        assert 0 <= d["score"] <= 20
        assert len(d["rationale"]) >= 10

    # Exactly three decision-makers, no fabricated emails
    assert len(body["decision_makers"]) == 3
    for dm in body["decision_makers"]:
        assert "title" in dm and "rationale" in dm and "linkedin_query" in dm

    # Outreach is clearly a draft
    assert body["outreach_draft"].lstrip().startswith("[DRAFT]")


def test_post_score_validation_422(api_client) -> None:
    """Missing organization_name should yield 422 (Pydantic validation)."""

    r = api_client.post("/score", json={"website": "https://example.org"})
    assert r.status_code == 422


def test_get_partnerships_after_score(api_client) -> None:
    """After scoring twice, the list endpoint should return both rows."""

    api_client.post("/score", json={"organization_name": "American Cancer Society"})
    api_client.post("/score", json={"organization_name": "Local Plumbing LLC"})

    r = api_client.get("/partnerships?limit=10&offset=0")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    names = {row["organization_name"] for row in rows}
    assert {"American Cancer Society", "Local Plumbing LLC"}.issubset(names)


def test_export_csv(api_client) -> None:
    """CSV export should come back as text/csv with a header row."""

    api_client.post("/score", json={"organization_name": "CaringBridge"})
    r = api_client.get("/partnerships/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    body = r.text.strip().splitlines()
    assert body[0].startswith("id,organization_name,")
    assert any("CaringBridge" in line for line in body[1:])
