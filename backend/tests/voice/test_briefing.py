"""The spoken briefing DAS hears before a hand-over connects (design 2026-11-14 §6)."""

from app.voice.dialogue import briefing


def test_briefing_in_full():
    said = briefing(
        "doamna Maria",
        "Maria Popescu",
        "Calea Aradului 12, bloc A3",
        "A spus: «mă doare în piept»",
        "Locuiește singură. Are tensiune mare.",
    )

    assert said == (
        "Predare EchoCare. doamna Maria, Maria Popescu, Calea Aradului 12, bloc A3. "
        "A spus: «mă doare în piept». Pe scurt: Locuiește singură. Vă conectez."
    )


def test_briefing_without_quote():
    said = briefing(
        "doamna Maria", "Maria Popescu", None, "A cerut un operator (tasta 9)", None
    )

    assert "A spus" not in said


def test_briefing_with_nothing_but_a_name():
    said = briefing("doamna Maria", "Maria Popescu", None, None, None)

    assert said == "Predare EchoCare. doamna Maria, Maria Popescu. Vă conectez."


def test_briefing_stays_short():
    narrative = " ".join(["cuvânt"] * 100)  # 600 characters, one sentence

    said = briefing("doamna Maria", "Maria Popescu", None, None, narrative)

    assert len(said.split()) <= 45
