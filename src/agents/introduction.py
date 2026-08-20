"""Prompt contract for explaining a judged match without fabricating familiarity."""

INTRODUCTION_VERSION = "introduction_v1"
INTRODUCTION_PROMPT = """Explain why two people were matched.

Your purpose is to remove the uncertainty involved in contacting a stranger.

Use only the supplied profile information and match context.

Do not infer new facts.

Do not exaggerate compatibility.

Write three pieces of information:

1. WHY THIS PERSON

One or two sentences telling the requester why this candidate is relevant
to their specific need.

2. WHY YOU

One or two sentences explaining what relevant context about the requester
the candidate would see if contacted.

3. POSSIBLE OPENER

A natural first message the requester could optionally send.

The opener must not pretend the two people already know each other.

Avoid generic phrasing such as:

"I noticed we share a passion for..."

unless the shared interest is both supported and genuinely relevant.

Prefer concrete context.

Example:

WHY THIS PERSON:
Maya built a campus marketplace and acquired its first few hundred users
through student organizations. She's also open to helping student founders
with early distribution.

WHY YOU:
You're currently building a campus product and trying to figure out how to
get your first users without paid acquisition.

POSSIBLE OPENER:
"Hey Maya — I'm trying to get the first users for a campus app and saw that
you grew your marketplace through student organizations. I'd love to hear
what worked for you early on."
"""
