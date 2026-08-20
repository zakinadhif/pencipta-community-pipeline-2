from src.pipeline import _coerce_matches, _coerce_need, _parse_json_tolerant


def test_parse_json_tolerant_extracts_from_markdown():
    text = 'Here you go:\n```json\n{"goal":"x","retrievalQueries":{"offers":"a"}}\n```\nThanks!'
    assert _parse_json_tolerant(text)["goal"] == "x"


def test_parse_json_tolerant_extracts_prose_json():
    text = 'The answer is {"matches":[{"userId":"a","score":0.5,"reason":"r"}]} done.'
    assert _parse_json_tolerant(text)["matches"][0]["userId"] == "a"


def test_coerce_need_normalizes_loose_types():
    need = {
        "goal": "g",
        "interactionType": "mentorship",
        "target": "backend engineer",
        "hardFilters": "Bandung",
        "retrievalQueries": "senior backend",
        "softPreferences": "kind",
        "avoidMatchingOn": [],
    }
    coerced = _coerce_need(need)
    assert coerced["interactionType"] == ["mentoring"]
    assert coerced["target"]["knowledge"] == ["backend engineer"]
    assert coerced["hardFilters"]["location"] == "Bandung"
    assert coerced["retrievalQueries"]["offers"] == "senior backend"
    assert coerced["retrievalQueries"]["interests"] == "senior backend"
    assert coerced["softPreferences"] == ["kind"]


def test_coerce_matches_accepts_candidateId_and_missing_keys():
    judged = {"matches": [
        {"candidateId": "sarah", "score": 0.95, "reason": "great"},
        {"userId": "raka", "matchScore": 0.8},
        {"id": "hana"},
    ]}
    matches = _coerce_matches(judged)
    assert [m["userId"] for m in matches] == ["sarah", "raka", "hana"]
    assert matches[0]["score"] == 0.95
    assert matches[1]["score"] == 0.8
    assert matches[0]["reason"] == "great"
