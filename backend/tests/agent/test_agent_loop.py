"""The agent loop scripted with a fake model and a fake line (06 §5, design §4, §5)."""

import asyncio
import json
from datetime import date

import pytest

from app.agent.loop import (
    DEFAULT_SUMMARY,
    DROPPED_SUMMARY,
    FAILURE,
    STALL,
    TIME_UP,
    TIME_UP_SUMMARY,
    Agent,
    Limits,
    Line,
)
from app.agent.model import ToolCall
from app.agent.relay import CONNECTING, Escalation
from app.status.alarms import SELF_HARM_HANDOVER, confirmation_question
from app.status.engine import Severity
from app.voice.models import Speaker, TurnKind

CALL = "0190a1b2-0000-7000-8000-000000000001"
SETUP = {"type": "setup", "callSid": "CA1", "sessionId": "VX1"}
SUNDAY = "duminică"


class FakeModel:
    """Each call pops one round and yields its items. An Exception item is raised and an
    Event item is awaited, so a round can fail or hang mid-stream."""

    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.calls: list[list[dict]] = []

    async def __call__(self, messages):
        self.calls.append([dict(m) for m in messages])
        for item in self.rounds.pop(0):
            if isinstance(item, Exception):
                raise item
            if isinstance(item, asyncio.Event):
                await item.wait()
                continue
            yield item


class FakeLine:
    def __init__(self):
        self.turns, self.answers, self.concerns = [], [], []
        self.hand_overs, self.ends = [], []

    async def store(self, speaker, kind, content):
        self.turns.append((speaker, kind, content))

    async def answer(self, question, answer):
        self.answers.append((question, answer))

    async def concern(self, severity, reason):
        self.concerns.append((severity, reason))

    async def hand_over(self, escalation, reason):
        self.hand_overs.append((escalation, reason))
        return True

    async def end(self, summary, dropped):
        self.ends.append((summary, dropped))


_agents: list[Agent] = []


@pytest.fixture(autouse=True)
async def close_agents():
    """Every agent is closed after its test, so no timer outlives it."""
    yield
    while _agents:
        await _agents.pop().close()


def make(model, *, today=date(2026, 11, 8), **limits):
    line, sent = FakeLine(), []

    async def send(message):
        sent.append(message)

    agent = Agent(
        call=CALL,
        greeting="Bună ziua, doamna Elena.",
        form_of_address="doamna Elena",
        heat=False,
        send=send,
        line=Line(line.store, line.answer, line.concern, line.hand_over, line.end),
        model=model,
        today=today,
        limits=Limits(
            **{"first_token": 0.2, "call_limit": 5, "tier2_wait": 0.05, **limits}
        ),
    )
    _agents.append(agent)
    return agent, line, sent


async def started(model, **kw):
    agent, line, sent = make(model, **kw)
    await agent.handle(SETUP)
    return agent, line, sent


def prompt(words, last=True):
    return {"type": "prompt", "voicePrompt": words, "lang": "ro-RO", "last": last}


def dtmf(digit):
    return {"type": "dtmf", "digit": digit}


def rec(field, value, clear):
    return ToolCall(
        f"c-{field}",
        "record_answer",
        {"field": field, "value": value, "clear": clear, "words": value},
    )


def concern(level, reason):
    args = {"level": level, "reason": reason, "words": reason}
    return ToolCall(f"c-{level}", "raise_concern", args)


def texts(sent):
    return [m["token"] for m in sent if m["type"] == "text"]


def users(messages):
    return [m["content"] for m in messages if m["role"] == "user"]


async def test_the_04_5_conversation_reaches_a_close():
    model = FakeModel(
        [
            [rec("feeling", "ok", False)],
            ["Vă simțiți ", "bine acum?"],
            [rec("feeling", "ok", True), rec("orientation", SUNDAY, True), "Aveți?"],
            [rec("shelter", "yes", True), "La revedere."],
        ]
    )
    a, line, sent = await started(model)
    for words in ["mda, merge", "bine, e duminică", "da"]:
        await a.handle(prompt(words))
        await a.idle()
    assert {"type": "text", "token": "Vă simțiți ", "last": False} in sent
    assert {"type": "text", "token": "bine acum?", "last": True} in sent
    assert sent[-1] == {"type": "end"} and line.ends == [(DEFAULT_SUMMARY, False)]
    # The re-ask is named in the tool result.
    assert "feeling" in model.calls[1][-1]["content"]
    assert model.calls[0][:2] == [
        {"role": "system", "content": model.calls[0][0]["content"]},
        {"role": "assistant", "content": "Bună ziua, doamna Elena."},
    ]
    assert len(line.answers) == 4 and a.finished
    assert (Speaker.agent, TurnKind.speech, "Vă simțiți bine acum?") in line.turns


async def test_a_text_round_ends_the_turn():
    model = FakeModel([["Bine.", rec("feeling", "ok", True)]])
    a, _, _ = await started(model)
    await a.handle(prompt("bine"))
    await a.idle()
    assert len(model.calls) == 1


async def test_three_tool_only_rounds_say_the_stall_line():
    model = FakeModel([[rec("feeling", "ok", True)]] * 3)
    a, line, sent = await started(model)
    await a.handle(prompt("bine"))
    await a.idle()
    assert texts(sent) == [STALL] and len(model.calls) == 3
    assert line.turns[-1] == (Speaker.agent, TurnKind.speech, STALL)


async def test_json_looking_text_is_never_sent():
    model = FakeModel([[" ", '{"name": "record_answer"', "}"], ["Ce zi e azi?"]])
    a, line, sent = await started(model)
    await a.handle(prompt("bine"))
    await a.idle()
    assert texts(sent) == ["Ce zi e azi?"]
    assert not any("record_answer" in t[2] for t in line.turns)


async def test_a_red_from_the_rules_hands_over_with_reason_agent():
    model = FakeModel([[rec("feeling", "unwell", True), rec("shelter", "no", True)]])
    a, line, sent = await started(model)
    # Not „n-am căldură”: that is a tier 2 phrase and would ask first.
    await a.handle(prompt("rău, și e frig"))
    await a.idle()
    assert line.hand_overs == [(Escalation.rules, "")]
    assert len(line.answers) == 2  # stored before the hand-over
    assert texts(sent) == [CONNECTING]
    assert json.loads(sent[-1]["handoffData"]) == {"call": CALL, "reason": "agent"}
    assert a.finished


async def test_request_human_hands_over():
    model = FakeModel([[ToolCall("c1", "request_human", {"reason": "nu aude"})]])
    a, line, sent = await started(model)
    await a.handle(prompt("alo? alo?"))
    await a.idle()
    assert line.hand_overs == [(Escalation.human, "nu aude")]
    assert json.loads(sent[-1]["handoffData"])["reason"] == "agent"


async def test_a_red_concern_hands_over_and_a_yellow_is_stored():
    model = FakeModel(
        [
            [concern("yellow", "a uitat pastilele"), "Bine. Ce zi e azi?"],
            [concern("red", "nu se poate ridica")],
        ]
    )
    a, line, _ = await started(model)
    await a.handle(prompt("am uitat pastilele"))
    await a.idle()
    assert line.concerns == [(Severity.yellow, "a uitat pastilele")]
    assert line.hand_overs == []
    await a.handle(prompt("stau în pat de ieri"))
    await a.idle()
    assert line.concerns[-1] == (Severity.red, "nu se poate ridica")
    assert line.hand_overs == [(Escalation.concern, "nu se poate ridica")]


async def test_tier_1_hands_over_without_the_model():
    model = FakeModel([])
    a, line, sent = await started(model)
    await a.handle(prompt("am căzut"))
    await a.idle()
    assert model.calls == [] and line.hand_overs == [(Escalation.alarm, "am căzut")]
    assert texts(sent) == [CONNECTING]
    assert json.loads(sent[-1]["handoffData"])["reason"] == "alarm"


async def test_self_harm_says_its_own_line():
    a, line, sent = await started(FakeModel([]))
    await a.handle(prompt("vreau să mor"))
    assert texts(sent) == [SELF_HARM_HANDOVER]
    assert line.turns[-1] == (Speaker.agent, TurnKind.speech, SELF_HARM_HANDOVER)


@pytest.mark.parametrize("reply", [prompt("da"), dtmf("1"), None])
async def test_tier_2_yes_or_silence_hands_over(reply):
    model = FakeModel([])
    a, line, sent = await started(model)
    await a.handle(prompt("am leșinat"))
    assert sent == [
        {"type": "text", "token": confirmation_question("am leșinat"), "last": True}
    ]
    if reply is None:
        await asyncio.sleep(0.1)
    else:
        await a.handle(reply)
    await a.idle()
    assert model.calls == [] and line.hand_overs == [(Escalation.tier_2, "am leșinat")]
    assert json.loads(sent[-1]["handoffData"])["reason"] == "alarm"


@pytest.mark.parametrize("reply", [prompt("nu"), dtmf("2")])
async def test_tier_2_no_goes_to_the_model(reply):
    model = FakeModel([["Bine. Cum vă simțiți?"]])
    a, line, _ = await started(model)
    await a.handle(prompt("am leșinat ieri, azi nu"))
    await a.handle(reply)
    await a.idle()
    await asyncio.sleep(0.1)  # past the 8 s wait: its timer was cancelled
    assert line.hand_overs == []
    assert users(model.calls[0])[-2] == "am leșinat ieri, azi nu"
    assert len(users(model.calls[0])) == 2
    assert (Speaker.system, TurnKind.speech, "Confirmare nivel 2: nu") in line.turns


async def test_a_tier_1_phrase_in_the_no_still_hands_over():
    a, line, _ = await started(FakeModel([]))
    await a.handle(prompt("am leșinat"))
    await a.handle(prompt("nu, dar am căzut"))
    assert line.hand_overs == [(Escalation.alarm, "nu, dar am căzut")]


async def test_key_9_hands_over():
    a, line, sent = await started(FakeModel([]))
    await a.handle(dtmf("5"))
    await a.handle(dtmf("9"))
    assert line.hand_overs == [(Escalation.key_9, "")]
    assert json.loads(sent[-1]["handoffData"])["reason"] == "key_9"
    assert line.turns[-2] == (Speaker.senior, TurnKind.keys, "9")


async def test_interrupt_cancels_and_keeps_what_was_heard():
    hang = asyncio.Event()
    model = FakeModel([[rec("feeling", "ok", True)], ["Doamna Elena, ", hang], ["Da."]])
    a, line, _ = await started(model)
    await a.handle(prompt("bine"))
    await asyncio.sleep(0.02)
    interrupt = {"type": "interrupt", "utteranceUntilInterrupt": "Doamna Elena"}
    await a.handle(interrupt)
    assert line.turns[-1] == (
        Speaker.system,
        TurnKind.speech,
        "interrupted after: Doamna Elena",
    )
    await a.handle(prompt("ce?"))
    await a.idle()
    # Cancelled mid-stream: the finished tool round stays, what was heard is added.
    assert [m["role"] for m in model.calls[2][-5:]] == [
        "user",
        "assistant",
        "tool",
        "assistant",
        "user",
    ]
    assert model.calls[2][-2:] == [
        {"role": "assistant", "content": "Doamna Elena"},
        {"role": "user", "content": "ce?"},
    ]


async def test_an_interrupt_after_the_turn_keeps_only_what_was_heard():
    model = FakeModel([["Bine. Ce zi e azi?", rec("feeling", "ok", True)], ["Da."]])
    a, line, _ = await started(model)
    await a.handle(prompt("bine"))
    await a.idle()  # the stream ends long before Twilio stops speaking
    await a.handle({"type": "interrupt", "utteranceUntilInterrupt": "Bine."})
    await a.handle(prompt("duminică"))
    await a.idle()
    spoken, result = model.calls[1][-3:-1]
    assert spoken["content"] == "Bine." and spoken["tool_calls"][0]["id"] == "c-feeling"
    assert result["role"] == "tool" and result["tool_call_id"] == "c-feeling"
    assert (Speaker.agent, TurnKind.speech, "Bine. Ce zi e azi?") in line.turns


async def test_an_interrupt_after_the_stall_line_appends():
    model = FakeModel([[rec("feeling", "ok", True)]] * 3 + [["Da."]])
    a, _, _ = await started(model)
    await a.handle(prompt("bine"))
    await a.idle()
    await a.handle({"type": "interrupt", "utteranceUntilInterrupt": "Vă"})
    await a.handle(prompt("ce?"))
    await a.idle()
    assert model.calls[3][-3]["role"] == "tool"
    assert model.calls[3][-2:] == [
        {"role": "assistant", "content": "Vă"},
        {"role": "user", "content": "ce?"},
    ]


async def test_a_new_prompt_mid_turn_replaces_the_turn():
    hang = asyncio.Event()
    model = FakeModel([["Vă ", hang, "simțiți?"], ["Bine."]])
    a, _, sent = await started(model)
    await a.handle(prompt("bine"))
    await asyncio.sleep(0.02)
    await a.handle(prompt("adică foarte bine"))
    await a.idle()
    hang.set()  # a turn still alive would now finish its reply
    await asyncio.sleep(0.02)
    assert users(model.calls[1]) == ["bine", "adică foarte bine"]
    assert model.calls[1][-1] == {"role": "user", "content": "adică foarte bine"}
    assert sent == [{"type": "text", "token": "Bine.", "last": True}]


async def test_a_model_error_drops_the_call():
    a, line, sent = await started(FakeModel([[RuntimeError("boom")]]))
    await a.handle(prompt("bine"))
    await a.idle()
    assert texts(sent) == [FAILURE] and line.ends == [(DROPPED_SUMMARY, True)]
    assert sent[-1] == {"type": "end"} and a.finished


async def test_no_first_token_in_time_drops_the_call():
    async def slow(messages):
        await asyncio.sleep(1)
        yield "prea târziu"

    a, line, sent = await started(slow)
    await a.handle(prompt("bine"))
    await a.idle()
    assert texts(sent) == [FAILURE] and line.ends == [(DROPPED_SUMMARY, True)]


async def test_the_time_limit_closes_with_the_answers_so_far():
    model = FakeModel([[rec("feeling", "ok", True), "Ce zi e azi?"]])
    a, line, sent = await started(model, call_limit=0.05)
    await a.handle(prompt("bine"))
    await a.idle()
    await asyncio.sleep(0.1)
    assert texts(sent)[-1] == TIME_UP and line.ends == [(TIME_UP_SUMMARY, False)]
    assert sent[-1] == {"type": "end"} and len(line.answers) == 1
    assert a.rules.time_up


async def test_the_time_limit_during_a_confirmation_hands_over():
    a, line, _ = await started(FakeModel([]), call_limit=0.05, tier2_wait=5)
    await a.handle(prompt("am leșinat"))
    await asyncio.sleep(0.1)
    assert line.hand_overs == [(Escalation.tier_2, "am leșinat")] and line.ends == []


async def test_may_close_ends_without_end_call():
    round_ = [
        rec("feeling", "ok", True),
        rec("orientation", SUNDAY, True),
        rec("shelter", "yes", True),
        "La revedere.",
    ]
    a, line, sent = await started(FakeModel([round_]))
    await a.handle(prompt("bine, duminică, da"))
    await a.idle()
    assert line.ends == [(DEFAULT_SUMMARY, False)] and sent[-1] == {"type": "end"}


async def test_an_accepted_summary_is_stored():
    round_ = [
        rec("feeling", "ok", True),
        rec("orientation", SUNDAY, True),
        rec("shelter", "yes", True),
        ToolCall("c9", "end_call", {"summary": "Este bine."}),
        "La revedere.",
    ]
    a, line, _ = await started(FakeModel([round_]))
    await a.handle(prompt("bine, duminică, da"))
    await a.idle()
    assert line.ends == [("Este bine.", False)]


async def test_nothing_is_sent_after_end():
    a, line, sent = await started(FakeModel([[RuntimeError("boom")]]))
    await a.handle(prompt("bine"))
    await a.idle()
    count = len(sent)
    for message in [prompt("alo?"), dtmf("9"), prompt("am căzut")]:
        await a.handle(message)
        await a.idle()
    await a.close()
    assert len(sent) == count and line.hand_overs == []
    assert line.ends == [(DROPPED_SUMMARY, True)]


async def test_a_hang_up_during_the_confirmation_hands_over():
    a, line, sent = await started(FakeModel([]))
    await a.handle(prompt("am leșinat"))
    await a.close()
    assert line.hand_overs == [(Escalation.tier_2, "am leșinat")]
    assert len(sent) == 1 and a.finished  # only the question: the line is gone
    assert line.turns[-1][2] == confirmation_question("am leșinat")
    await asyncio.sleep(0.1)  # its timer was cancelled: no second hand-over
    assert len(line.hand_overs) == 1


async def test_close_cancels_a_running_turn_quietly():
    model = FakeModel([["Vă ", asyncio.Event()]])
    a, line, sent = await started(model)
    await a.handle(prompt("bine"))
    await asyncio.sleep(0.02)
    await a.close()
    assert sent == [] and line.ends == [] and line.hand_overs == []
    assert a.finished


def slow_answers(a, line):
    """Answers wait for the returned Event before they are recorded."""
    slow = asyncio.Event()
    record = line.answer

    async def answer(question, value):
        await slow.wait()
        await record(question, value)

    object.__setattr__(a.line, "answer", answer)
    return slow


async def test_a_cancel_during_the_writes_keeps_the_round_whole():
    model = FakeModel([[rec("feeling", "ok", True)], ["Ce zi e azi?"]])
    a, line, _ = await started(model)
    slow = slow_answers(a, line)
    await a.handle(prompt("bine"))
    await asyncio.sleep(0.02)
    await a.handle(prompt("foarte bine"))  # cancels the turn mid-write
    await a.idle()
    roles = [m["role"] for m in model.calls[1]]
    assert roles[-4:] == ["user", "assistant", "tool", "user"]
    slow.set()
    await asyncio.sleep(0.02)
    assert len(line.answers) == 1  # the write was not lost


async def test_close_waits_for_a_write_in_flight():
    model = FakeModel([[rec("feeling", "ok", True)]])
    a, line, _ = await started(model)
    slow = slow_answers(a, line)
    await a.handle(prompt("bine"))
    await asyncio.sleep(0.02)
    closing = asyncio.create_task(a.close())
    await asyncio.sleep(0.02)
    assert not closing.done()  # settle must not conclude before the answer lands
    slow.set()
    await closing
    assert len(line.answers) == 1


async def test_a_hand_over_waits_for_a_write_in_flight():
    model = FakeModel([[rec("feeling", "ok", True)]])
    a, line, _ = await started(model)
    slow = slow_answers(a, line)
    answers_at_hand_over = []
    hand_over = line.hand_over

    async def noting(escalation, reason):
        answers_at_hand_over.append(len(line.answers))
        return await hand_over(escalation, reason)

    object.__setattr__(a.line, "hand_over", noting)
    await a.handle(prompt("bine"))
    await asyncio.sleep(0.02)
    key = asyncio.create_task(a.handle(dtmf("9")))
    await asyncio.sleep(0.02)
    slow.set()
    await key
    assert answers_at_hand_over == [1]


async def test_a_failed_hand_over_still_sends_the_call_to_a_person():
    a, _, sent = await started(FakeModel([]))

    async def broken(escalation, reason):
        raise RuntimeError("database down")

    object.__setattr__(a.line, "hand_over", broken)
    await a.handle(prompt("am căzut"))  # does not raise
    assert texts(sent) == [CONNECTING]
    assert json.loads(sent[-1]["handoffData"]) == {"call": CALL, "reason": "alarm"}
    assert a.finished


async def test_a_hang_up_while_the_question_is_said_hands_over():
    a, line, _ = await started(FakeModel([]))
    asked = asyncio.Event()
    store = line.store

    async def slow_store(speaker, kind, content):
        if content.startswith("Ați spus"):
            await asked.wait()
        await store(speaker, kind, content)

    object.__setattr__(a.line, "store", slow_store)
    saying = asyncio.create_task(a.handle(prompt("am leșinat")))
    await asyncio.sleep(0.02)
    await asyncio.wait_for(a.close(), 0.5)
    asked.set()
    await saying
    assert line.hand_overs == [(Escalation.tier_2, "am leșinat")]
    assert a._confirm is None  # no timer left waiting 8 s


async def test_a_second_setup_starts_no_second_timer():
    a, _, _ = await started(FakeModel([]))
    first = a._limit
    await a.handle(SETUP)
    assert a._limit is first


async def test_no_speech_is_logged(caplog):
    model = FakeModel([['{"name": "record_answer", "secret": "inima"}'], ["Bine."]])
    a, _, _ = await started(model)
    with caplog.at_level("DEBUG"):
        await a.handle(prompt("mă doare capul"))
        await a.idle()
    assert "doare" not in caplog.text and "inima" not in caplog.text
