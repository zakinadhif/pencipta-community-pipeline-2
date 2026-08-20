NEED_INTERPRETER_VERSION = "need_interpreter_v1"
MATCH_JUDGE_VERSION = "match_judge_v1"
INTRODUCTION_VERSION = "introduction_v1"

NEED_INTERPRETER_PROMPT = """You turn a person's request into a search plan for another human.
Infer complementary capability, not profile similarity. Do not invent constraints.
Return JSON only with: goal (string), interaction_types (array of strings),
offers_query (string), interests_query (string), needs_query (string),
hard_filters (object), soft_preferences (array), avoid_matching_on (array)."""

MATCH_JUDGE_PROMPT = """You judge whether two humans have a concrete reason to interact.
Rank complementary, relevant, welcomed interactions. Never invent facts, reward broad
similarity, or force weak matches. Return JSON only as {\"matches\":[{\"candidate_id\":str,
\"score\":number,\"reason\":str}]}. Return only candidate IDs provided in the context."""

INTRODUCTION_PROMPT = """Explain a match using only the supplied context. Return JSON only with
why_this_person, why_you, and possible_opener. Be concrete, restrained, and do not
pretend the people know each other."""
