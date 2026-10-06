import json

import pytest
from pydantic import ValidationError

from bugflow.agents.crew_llm import AgentCallError
from bugflow.agents.outputs import AGENTS, AnalysisOutput, ComponentOutput, PlanOutput
from bugflow.services.triage import (
    AgentFailure,
    ask_agent,
    failure_text,
    reask_prompt,
    step_summary_text,
    validate_reply,
)
from mocks.fake_openai_server import default_reply

AG1, AG2, AG3, AG4, AG5 = AGENTS


def reply(role, **changes):
    data = default_reply(role)
    data.update(changes)
    return json.dumps(data)


def text_of(agent, raw, ids=frozenset()):
    with pytest.raises(AgentFailure) as caught:
        validate_reply(agent, raw, set(ids))
    return caught.value.text


def test_invalid_enum_text_has_the_value():
    raw = reply("Severity Classifier", severity="high")
    assert text_of(AG2, raw) == "AG2 returned invalid severity 'high'"


def test_enum_value_is_cut_at_forty_characters():
    raw = reply("Component Classifier", component="x" * 60)
    assert text_of(AG1, raw) == f"AG1 returned invalid component '{'x' * 40}'"


def test_non_string_enum_value_is_shown_as_text():
    assert text_of(AG1, reply("Component Classifier", component=5)) == (
        "AG1 returned invalid component '5'"
    )


def test_near_misses_keep_the_exact_value():
    assert text_of(AG1, reply("Component Classifier", component="Backend")) == (
        "AG1 returned invalid component 'Backend'"
    )
    assert text_of(AG1, reply("Component Classifier", component="backend ")).startswith(
        "AG1 returned invalid component"
    )


def test_constrained_field_text_has_no_value():
    assert text_of(AG4, reply("Resolution Manager", target_days=0)) == (
        "AG4 returned invalid target_days"
    )
    assert text_of(AG4, reply("Resolution Manager", target_days=91)) == (
        "AG4 returned invalid target_days"
    )


@pytest.mark.parametrize("raw", ["this is not json", "", "{", "[1, 2]", "null"])
def test_malformed_json_text(raw):
    assert text_of(AG1, raw) == "AG1 returned malformed JSON"


def test_unexpected_field_text():
    raw = reply("Resolution Manager", assignee_name="Alice")
    assert text_of(AG4, raw) == "AG4 returned unexpected field 'assignee_name'"


def test_missing_field_text():
    data = default_reply("Component Classifier")
    del data["justification"]
    assert text_of(AG1, json.dumps(data)) == "AG1 returned invalid justification"


def test_nested_field_uses_dotted_name_without_indexes():
    data = default_reply("Resolution Manager")
    data["assignee_profile"]["skills"] = []
    assert text_of(AG4, json.dumps(data)) == "AG4 returned invalid assignee_profile.skills"
    data["assignee_profile"]["skills"] = [""]
    assert text_of(AG4, json.dumps(data)) == "AG4 returned invalid assignee_profile.skills"


def test_nested_extra_field_text():
    data = default_reply("Resolution Manager")
    data["assignee_profile"]["name"] = "Alice"
    assert text_of(AG4, json.dumps(data)) == (
        "AG4 returned unexpected field 'assignee_profile.name'"
    )


def test_failure_text_for_a_model_error_outside_a_field():
    with pytest.raises(ValidationError) as caught:
        ComponentOutput.model_validate_json("[]")
    assert failure_text(AG1, caught.value) == "AG1 returned malformed JSON"


def test_cross_check_requires_a_subset_of_supplied_ids():
    raw = reply("Technical Analyst", referenced_similar_bug_ids=[99999])
    assert text_of(AG3, raw, {1, 2}) == "AG3 returned invalid referenced_similar_bug_ids"
    assert text_of(AG3, raw) == "AG3 returned invalid referenced_similar_bug_ids"
    ok = reply("Technical Analyst", referenced_similar_bug_ids=[2])
    assert validate_reply(AG3, ok, {1, 2}).referenced_similar_bug_ids == [2]
    assert validate_reply(AG3, reply("Technical Analyst"), set())


def test_validate_reply_returns_the_model():
    output = validate_reply(AG4, reply("Resolution Manager"), set())
    assert isinstance(output, PlanOutput)


class ScriptedRunner:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def __call__(self, agent, prompt, client):
        self.prompts.append(prompt)
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_valid_reply_is_asked_once():
    runner = ScriptedRunner(reply("Component Classifier"))
    output = ask_agent(runner, AG1, "PROMPT", None, set())
    assert isinstance(output, ComponentOutput) and runner.prompts == ["PROMPT"]


def test_invalid_reply_is_re_asked_once_with_the_validation_error():
    bad = reply("Severity Classifier", severity="high")
    runner = ScriptedRunner(bad, reply("Severity Classifier"))
    seen = []
    output = ask_agent(runner, AG2, "PROMPT", None, set(), seen.append)
    assert output.severity.value == "major"
    assert seen == ["AG2 returned invalid severity 'high'"]
    assert len(runner.prompts) == 2
    assert runner.prompts[1].startswith("PROMPT")
    assert "AG2 returned invalid severity 'high'" in runner.prompts[1]
    assert bad not in runner.prompts[1]


def test_second_invalid_reply_fails_with_the_second_text():
    runner = ScriptedRunner(
        reply("Severity Classifier", severity="high"), reply("Severity Classifier", severity="low")
    )
    with pytest.raises(AgentFailure) as caught:
        ask_agent(runner, AG2, "PROMPT", None, set())
    assert caught.value.text == "AG2 returned invalid severity 'low'"
    assert caught.value.raw and len(runner.prompts) == 2


def test_provider_failure_is_not_re_asked():
    runner = ScriptedRunner(AgentCallError("rate_limited", "OpenAI rate limit exceeded"))
    with pytest.raises(AgentFailure) as caught:
        ask_agent(runner, AG1, "PROMPT", None, set())
    assert caught.value.text == "AG1 failed: OpenAI rate limit exceeded"
    assert caught.value.raw is None and len(runner.prompts) == 1


def test_provider_failure_on_the_re_ask_fails_the_step():
    runner = ScriptedRunner("nope", AgentCallError("timeout", "OpenAI request timed out"))
    with pytest.raises(AgentFailure) as caught:
        ask_agent(runner, AG1, "PROMPT", None, set())
    assert caught.value.text == "AG1 failed: OpenAI request timed out"


def test_unexpected_runner_error_gets_fixed_text():
    runner = ScriptedRunner(RuntimeError("secret sk-abcdefghijklmnopqrstuvwxyz"))
    with pytest.raises(AgentFailure) as caught:
        ask_agent(runner, AG1, "PROMPT", None, set())
    assert caught.value.text == "AG1 failed: unexpected agent error"


def test_reask_prompt_contains_the_error():
    text = reask_prompt("PROMPT", "AG1 returned malformed JSON")
    assert text.startswith("PROMPT") and "AG1 returned malformed JSON" in text


def test_step_summaries():
    def summary(agent, role, **changes):
        return step_summary_text(agent.model.model_validate_json(reply(role, **changes)))

    assert summary(AG1, "Component Classifier") == "backend"
    assert summary(AG2, "Severity Classifier") == "major"
    assert summary(AG3, "Technical Analyst") == "2 debugging steps, 0 similar bugs referenced"
    assert summary(AG3, "Technical Analyst", referenced_similar_bug_ids=[1]) == (
        "2 debugging steps, 1 similar bugs referenced"
    )
    assert summary(AG4, "Resolution Manager") == "backend / high / planned"
    assert summary(AG5, "Bug Documenter") == "1 key takeaways, 1 next steps"
    with pytest.raises(TypeError):
        step_summary_text(object())  # type: ignore[arg-type]


def test_analysis_output_type():
    assert isinstance(validate_reply(AG3, reply("Technical Analyst"), set()), AnalysisOutput)
