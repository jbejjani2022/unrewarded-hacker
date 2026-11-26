from collections import Counter

from uh.sorh import (final_answer, judge_messages, load_items, model_messages, parse_verdict,
                     summarize)


def test_frozen_subset_has_up_to_six_non_coding_prompts_per_task_type():
    items = load_items()
    assert len(items) == 182 and len({q["id"] for q in items}) == 182
    counts = Counter(q["task"] for q in items)
    assert len(counts) == 34 and max(counts.values()) == 6 and "write a function" not in counts
    assert all(q["user"] and q["hack_example"] and q["honest_example"] and q["cheat_method"] for q in items)


def test_model_sees_only_the_user_request():
    q = load_items(limit=1)[0]
    assert model_messages(q)[1]["content"] == q["user"]


def test_final_answer_drops_reasoning_and_truncated_or_empty_output():
    assert final_answer("<think>plan</think>\n\nDear Jamie", "stop") == "Dear Jamie"
    assert final_answer("<think>plan</think>\n\nDear Jamie", "length") is None
    assert final_answer("<think>plan</think>  ", "stop") is None


def test_judge_prompt_carries_the_request_the_cheat_and_the_response():
    q = load_items(limit=1)[0]
    text = judge_messages(q, "MY RESPONSE {braces}")[0]["content"]
    assert q["user"] in text and q["cheat_method"] in text and "MY RESPONSE {braces}" in text
    assert q["hack_example"] in text and q["honest_example"] in text


def test_verdict_parsing_and_summary():
    assert parse_verdict("HACK") == "HACK" and parse_verdict(" honest.") == "HONEST"
    assert parse_verdict("<think>HACK?</think> HONEST") == "HONEST" and parse_verdict("maybe") == "UNCLEAR"
    rows = [{"verdict": "HACK"}, {"verdict": "HONEST"}, {"verdict": None}, {"verdict": "UNCLEAR"}]
    assert summarize(rows) == {"n": 4, "answered": 3, "hack": 1, "honest": 1, "unclear": 1}
