import pytest

from app.status.alarms import Tier, check, confirmation_question, needs_help, normalize


def test_normalize():
    assert normalize("„Mă doare, ȘI țin!”") == "ma doare si tin"
    assert normalize("aşa ţin") == "asa tin"  # cedilla forms
    assert normalize("N-am aer.") == "n-am aer"  # hyphen kept
    assert normalize("  Nu-mi   simt  mâna ") == "nu-mi simt mana"


@pytest.mark.parametrize(
    ("sentence", "condition"),
    [
        ("Nu pot respira", "breathing"),
        ("Mă sufoc!", "breathing"),
        ("N-am aer", "breathing"),
        ("Nu am aer", "breathing"),
        ("Mă doare pieptul", "chest_heart"),
        ("Am o durere în piept", "chest_heart"),
        ("Mă doare mâna stângă", "chest_heart"),
        ("Nu-mi simt mâna", "stroke"),
        ("Văd dublu", "stroke"),
        ("Chemați salvarea", "ambulance"),
        ("Sunați la 112", "ambulance"),
        ("Sângerez", "bleeding"),
        ("Am căzut și nu mă pot ridica", "fall"),
        ("Stau pe jos de azi dimineață", "fall"),
        ("Vreau să mor", "self_harm"),
        ("Nu mai vreau să trăiesc", "self_harm"),
    ],
)
def test_tier_one(sentence, condition):
    match = check(sentence)
    assert match is not None
    assert match.tier is Tier.one
    assert match.condition == condition


@pytest.mark.parametrize(
    ("sentence", "condition"),
    [
        ("Am leșinat azi", "fainting"),
        ("Am lesinat azi", "fainting"),
        ("Mi s-a făcut negru în fața ochilor", "fainting"),
        ("Tremur tot", "cold"),
        ("Nu-mi simt degetele", "cold"),
        ("Nu am căldură", "cold"),
        ("Se învârte camera", "dizziness_vomiting"),
        ("Ajutor!", "help"),
        ("Mi-e foarte rău", "help"),
        ("Mor de cald!", "help"),
    ],
)
def test_tier_two(sentence, condition):
    match = check(sentence)
    assert match is not None
    assert match.tier is Tier.two
    assert match.condition == condition


def test_tier_one_wins_over_tier_two():
    match = check("Ajutor, am căzut")
    assert match is not None
    assert match.tier is Tier.one


@pytest.mark.parametrize(
    "sentence",
    [
        "N-am căzut azi",
        "Nu am căzut azi",
        "Nu am nevoie de salvare",
        "Nu mă doare pieptul",
        "Mor de cald",
        "Nu am nevoie de ajutor",
        "Sunt bine, mulțumesc",
        "Am apă și e răcoare în casă",
    ],
)
def test_harmless_never_tier_one(sentence):
    # 03 §4: everyday speech must not reach tier 1.
    match = check(sentence)
    assert match is None or match.tier is Tier.two


def test_a_negated_tier_one_asks_first():
    match = check("Nu am căzut azi")
    assert match is not None
    assert (match.tier, match.condition) == (Tier.two, "fall")
    # another tier 1 phrase in the same sentence still wins
    assert check("Nu am căzut, dar mă doare pieptul").tier is Tier.one


def test_harmless_no_match():
    assert check("N-am căzut azi") is None
    assert check("Sunt bine, mulțumesc") is None


def test_confirmation_question_names_what_was_said():
    assert confirmation_question("Tremur tot!") == (
        "Ați spus că tremur tot. Aveți nevoie de ajutor acum? "
        "Spuneți «da» sau apăsați 1. Dacă nu, spuneți «nu» sau apăsați 2."
    )


@pytest.mark.parametrize(
    ("reply", "red"),
    [
        ("1", True),
        ("da", True),
        ("Da, vă rog", True),
        (None, True),  # silence or hang-up
        ("", True),
        ("nu știu", True),  # unclear
        ("da... nu", True),  # unclear
        ("n-am auzit", True),  # unclear
        ("2", False),
        ("doi", False),
        ("nu", False),
        ("N-am nevoie", False),
        ("Nu-i nevoie", False),
        ("Nu, sunt bine, doar e cald", False),  # 03 §10 example 11
    ],
)
def test_needs_help(reply, red):
    assert needs_help(reply) is red
