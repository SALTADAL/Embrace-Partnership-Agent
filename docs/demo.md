# Demo

This page documents how the Streamlit demo works and what the three pre-loaded examples produce. It's the page a non-technical reviewer should land on after reading the README.

## What the demo looks like

The Streamlit app at `http://localhost:8501` has four parts:

1. **Three example buttons** — _American Cancer Society_, _CaringBridge_, _Make-A-Wish Foundation_. Click any one and the form populates.
2. **Input form** — organization name (required), website (optional), notes (optional).
3. **"Score Partnership" button** — kicks off one scoring run. While it runs you'll see status messages: _Researching org…_ → _Scoring fit…_ → _Drafting outreach…_
4. **Results panel** — color-coded tier badge (A/B/C/Pass), five dimension metrics, expandable rationales, decision-maker cards, and the draft outreach email.

The whole loop takes roughly 30–60 seconds against a live Anthropic API key.

## Sample outputs

> The numbers below are illustrative — the agent re-grounds each run on fresh web research, so individual dimensions may shift by a few points. Tier and shape of the response are stable.

### 1. American Cancer Society — Tier A

```json
{
  "organization_name": "American Cancer Society",
  "total_score": 88,
  "tier": "A",
  "dimensions": {
    "clinical_relevance": {
      "score": 20,
      "rationale": "ACS is the largest non-governmental cancer organization in the U.S. and serves patients across the full oncology continuum, including survivors and caregivers. Cancer is a core Embrace population."
    },
    "mission_alignment": {
      "score": 18,
      "rationale": "ACS's mission language explicitly centers patient and caregiver support programs (e.g. Hope Lodge, Road To Recovery) and emotional well-being. Strong alignment with Embrace's family-connection thesis."
    },
    "scale_and_reach": {
      "score": 20,
      "rationale": "National footprint with millions of patient and caregiver touches per year through programs and grants. Multi-site partnership potential is the largest in the nonprofit oncology space."
    },
    "decision_maker_accessibility": {
      "score": 15,
      "rationale": "VP-level patient-support and caregiver leadership is named publicly on the ACS site, but a single partnerships inbox is not obvious; routing requires LinkedIn outreach."
    },
    "strategic_fit": {
      "score": 15,
      "rationale": "Active ACS-CAN policy work and recent digital-health pilots suggest readiness for a video-based caregiver tool. No public partnership with a comparable startup yet."
    }
  },
  "decision_makers": [
    {
      "title": "VP, Patient Support",
      "rationale": "Owns the family-facing programs that Embrace would integrate with.",
      "linkedin_query": "\"VP Patient Support\" \"American Cancer Society\" site:linkedin.com/in"
    },
    {
      "title": "Director, Caregiver Programs",
      "rationale": "Day-to-day owner of caregiver-experience initiatives — a likely champion.",
      "linkedin_query": "\"Director Caregiver Programs\" \"American Cancer Society\" site:linkedin.com/in"
    },
    {
      "title": "Chief Mission Officer",
      "rationale": "Senior signoff on partnerships that touch patient experience.",
      "linkedin_query": "\"Chief Mission Officer\" \"American Cancer Society\" site:linkedin.com/in"
    }
  ],
  "outreach_draft": "[DRAFT] Hi [Name],\n\nI'm Atlas, founder of Embrace. Your team's work expanding caregiver support — particularly the Hope Lodge and Road To Recovery programs — is exactly the kind of family-facing care that drew me to build in this space. Embrace helps friends and family create short video montages for patients facing serious illness, including cancer, and we're scaling from clinical pilots at Duke, UNC, and City of Hope to broader nonprofit partners.\n\nI'd love 20 minutes to share what we've learned from oncology patients and caregivers, and to explore whether ACS's caregiver programs would benefit from a free pilot integration. If a different team owns this, I'd appreciate a pointer.\n\nWith gratitude,\nAtlas Lad, Founder, Embrace",
  "research_summary": "...",
  "research_quality": "full",
  "scored_at": "2026-04-28T15:00:00+00:00"
}
```

### 2. CaringBridge — Tier A

```json
{
  "organization_name": "CaringBridge",
  "total_score": 90,
  "tier": "A",
  "dimensions": {
    "clinical_relevance": {"score": 18, "rationale": "Patient-and-family social platform across all serious diagnoses; near-perfect overlap with Embrace's user."},
    "mission_alignment": {"score": 20, "rationale": "Mission centered on connection, support, and presence during health journeys — almost identical thesis to Embrace."},
    "scale_and_reach": {"score": 18, "rationale": "Used by 300K+ families/year. National reach, high family engagement."},
    "decision_maker_accessibility": {"score": 17, "rationale": "Leadership pages list Partnerships and Product directors. LinkedIn presence active."},
    "strategic_fit": {"score": 17, "rationale": "Public partnerships history with healthcare nonprofits; recent platform redesign signals openness to integrations."}
  },
  "decision_makers": [
    {"title": "VP, Partnerships", "rationale": "Likely owns external integrations.", "linkedin_query": "\"VP Partnerships\" \"CaringBridge\" site:linkedin.com/in"},
    {"title": "Director, Product", "rationale": "Owns the user-facing surface where a video-montage flow would live.", "linkedin_query": "\"Director of Product\" \"CaringBridge\" site:linkedin.com/in"},
    {"title": "Chief Mission Officer", "rationale": "Senior signoff and strategic alignment.", "linkedin_query": "\"Chief Mission Officer\" \"CaringBridge\" site:linkedin.com/in"}
  ],
  "outreach_draft": "[DRAFT] Hi [Name], CaringBridge has been a model for what family-centered support looks like online — Embrace is building the video-montage layer that often comes up in our user interviews as 'the thing CaringBridge doesn't quite do.' I'd love 20 minutes to share notes from our pilots at Duke, UNC, and City of Hope and explore where an Embrace integration might serve your families. — Atlas Lad, Founder, Embrace"
}
```

### 3. Make-A-Wish Foundation — Tier B

```json
{
  "organization_name": "Make-A-Wish Foundation",
  "total_score": 70,
  "tier": "B",
  "dimensions": {
    "clinical_relevance": {"score": 18, "rationale": "Pediatric serious illness — a core Embrace population."},
    "mission_alignment": {"score": 14, "rationale": "Mission emphasizes joy/wishes more than emotional-support technology, but family connection is implicit."},
    "scale_and_reach": {"score": 16, "rationale": "National via 60+ chapters; large but fragmented."},
    "decision_maker_accessibility": {"score": 12, "rationale": "Chapter structure obscures partnership routing; national HQ has named program directors."},
    "strategic_fit": {"score": 10, "rationale": "Less recent digital-health activity than peer nonprofits; a partnership is plausible but not pre-signaled."}
  }
}
```

## What "Pass" looks like

Scoring an obviously irrelevant organization — e.g. "Local Plumbing LLC" — returns a Tier Pass without crashing. Total score lands ~24/100, the rationale notes the absence of clinical relevance, and the outreach draft still parses (the agent acknowledges that a plumber is not a fit and produces a courteous, non-pushy short note). This is the worst-case behavior we want: graceful, never crashing, never producing a misleading score.
