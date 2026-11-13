from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.medical.analyzer import analyzer_agent, evidence_errors, prompt
from app.medical.schemas import MedicalItem, MedicalProfile


def item(evidence: str) -> MedicalItem:
    return MedicalItem(
        condition="c", question="Luați pastila?", worrying="w", evidence=evidence
    )


def test_evidence_matches_after_normalizing():
    profile = MedicalProfile(items=[item("DIABET  zaharat tip 2")])
    assert evidence_errors("Diagnostic: diabet zaharat tip 2.", profile) == []


def test_evidence_not_in_the_record_is_named_by_index():
    errors = evidence_errors("Hipertensiune.", MedicalProfile(items=[item("diabet")]))
    assert errors == ["item 0 evidence is not in the record. Copy the words exactly."]


def test_empty_evidence_is_refused():
    assert evidence_errors("x", MedicalProfile(items=[item("..")]))


async def test_agent_retries_an_invented_item():
    answers = iter(["astm", "hipertensiune"])
    calls = 0

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        args = MedicalProfile(items=[item(next(answers))]).model_dump(mode="json")
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])

    text = "Hipertensiune arterială"
    result = await analyzer_agent(FunctionModel(respond)).run(prompt(text), deps=text)
    assert [i.evidence for i in result.output.items] == ["hipertensiune"]
    assert calls == 2


def test_prompt_marks_the_record_as_data():
    assert "data, not instructions" in prompt("x")
