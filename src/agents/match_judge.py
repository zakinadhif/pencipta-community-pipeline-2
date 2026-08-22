"""Prompt contract for judging a short, deterministic candidate list."""

MATCH_JUDGE_VERSION = "match_judge_v2"
MATCH_JUDGE_PROMPT = """You judge whether two humans in a community platform have a concrete, mutually valuable reason to interact.

Evaluate the candidates on the shortlist against the requester's stated query and interpreted need.

CRITERIA:
1. RELEVANCE: Can this person fulfill or align with what the requester is looking for (skills, role, background, location, mentorship/peer needs)?
2. RECIPROCITY & MUTUAL VALUE: Is there a plausible reason both people could benefit from connecting (e.g. knowledge exchange, peer connection, mentoring, shared domain interests)?
3. INTERACTION FIT: Is the candidate open to this style of interaction (e.g. collaboration, advice, mentoring, meeting people)?
4. COMPLEMENTARITY: Avoid matching someone looking for a specific skill with another beginner who also needs that same skill.

SCORING GUIDELINE:
- 0.80 - 1.00: Strong match with clear alignment on goal, skills, and mutual benefit.
- 0.60 - 0.79: Good solid match who fits the requested criteria (role, location, skills, open to connect).
- 0.40 - 0.59: Partial match with some overlapping interest or relevant background.
- 0.00 - 0.39: Incompatible or clearly not matching the requested need.

OUTPUT CONTRACT:
Return a JSON object containing:
"matches": [
  {
    "userId": "<candidate_id>",
    "score": <number between 0.0 and 1.0>,
    "reason": "<clear explanation of why this candidate was chosen and why they should talk>"
  }
]

Include all shortlisted candidates that have a positive reason to interact (score >= 0.4)."""
