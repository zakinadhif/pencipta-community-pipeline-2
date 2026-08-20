"""Deterministically expand the eight canonical profiles to 100 inspectable fixtures."""
from __future__ import annotations

import json
from pathlib import Path


ARCHETYPES = [
    ("backend", "Backend engineer", ["Python", "APIs"], ["built production web services"], ["developer tools"], ["backend architecture reviews"], ["product design feedback"], ["advice", "collaboration"]),
    ("community", "Community organizer", ["community operations", "facilitation"], ["ran volunteer programs"], ["education", "communities"], ["volunteer onboarding"], ["simple automation help"], ["advice", "collaboration"]),
    ("designer", "Product designer", ["product design", "visual systems"], ["shipped web product designs"], ["unusual interfaces", "side projects"], ["design critique"], ["engineering collaborators"], ["collaboration", "advice"]),
    ("founder", "Early-stage founder", ["customer discovery", "distribution"], ["launched a small digital product"], ["startups", "marketplaces"], ["first-user research"], ["technical architecture help"], ["advice", "collaboration"]),
    ("data", "Data analyst", ["SQL", "data visualization"], ["built operational dashboards"], ["open data", "automation"], ["analytics and measurement"], ["domain experts"], ["advice", "collaboration"]),
    ("finance", "Small-business finance practitioner", ["accounting", "bookkeeping"], ["supported small-business finances"], ["automation", "programming"], ["accounting workflows"], ["help learning Python"], ["advice", "collaboration"]),
    ("mobile", "Mobile developer", ["mobile apps", "frontend engineering"], ["published a mobile application"], ["accessibility", "education"], ["mobile prototyping"], ["user research partners"], ["collaboration", "mentoring"]),
    ("infra", "Infrastructure operator", ["Linux", "containers", "self-hosting"], ["operated self-hosted services"], ["decentralized systems"], ["deployment and operations"], ["people building social software"], ["advice", "mentoring"]),
    ("research", "User researcher", ["qualitative research", "interviewing"], ["ran product discovery studies"], ["public-interest technology"], ["research planning"], ["prototype collaborators"], ["advice", "collaboration"]),
    ("educator", "Programming educator", ["software fundamentals", "curriculum design"], ["mentored beginner developers"], ["teaching", "learning communities"], ["learning programming"], ["real project examples"], ["mentoring", "advice"]),
    ("travel", "Independent travel planner", ["travel planning", "cross-cultural logistics"], ["planned independent regional trips"], ["food", "photography"], ["practical trip planning"], ["local recommendations"], ["advice", "meeting_people"]),
    ("hardware", "Hardware prototyper", ["electronics", "rapid prototyping"], ["built connected-device prototypes"], ["civic technology", "maker communities"], ["hardware prototyping"], ["software collaborators"], ["collaboration", "advice"]),
]
LOCATIONS = ["Bandung", "Jakarta", "Yogyakarta", "Surabaya", "Malang", "Denpasar"]


def expanded_profiles(anchors: list[dict]) -> list[dict]:
    profiles = [profile for profile in anchors if not profile["id"].startswith("synthetic-")]
    for index in range(1, 101 - len(profiles)):
        key, headline, knowledge, experience, interests, offers, needs, open_to = ARCHETYPES[(index - 1) % len(ARCHETYPES)]
        cohort = (index - 1) // len(ARCHETYPES) + 1
        profiles.append({
            "id": f"synthetic-{index:03d}", "name": f"Synthetic {key.title()} {cohort}",
            "headline": headline,
            "summary": f"Synthetic fixture {index:03d}: {headline.lower()} open to focused knowledge exchange.",
            "knowledge": knowledge, "experience": experience, "interests": interests,
            "canHelpWith": offers, "lookingFor": needs, "openTo": open_to,
            "location": LOCATIONS[(index - 1) % len(LOCATIONS)],
        })
    return profiles


if __name__ == "__main__":
    path = Path(__file__).with_name("synthetic_profiles.json")
    anchors = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(expanded_profiles(anchors), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
