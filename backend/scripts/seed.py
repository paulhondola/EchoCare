"""Fill the local database with fictitious people and their history, a starting point for
the dashboard and the apps. The demo uses fictitious people only (05 §5).

Twelve seniors in Timișoara, one or more in every enrollment state, with their medics
and caregivers; a second DAS employee; a cold-weather campaign; wellbeing calls with
their transcripts, answers and status reports; watch check-ins; and incidents open, in
progress and resolved, so every dashboard screen has something on it.

The seniors and their history have fixed uuid5 ids, so a second run adds nothing.
--reset deletes every senior the seed made and everything about them, including calls,
incidents, caregivers and edits made through the API since, then makes them again,
timed relative to now (resolved incidents leave the dashboard after a day, 04 §1).
Users, staff grants and the campaign stay and are reused, and so do the seniors made
through the API, with their history. The Firebase test numbers sign in to it
(backend/README.md): +40700000001 as DAS, +40700000002 as the medic of most seniors,
+40700000004 as Maria Popescu's son and +40700000005 as Maria Popescu, unless that number
is already another senior's (AL7), which the run reports.

Local databases only, like alembic/env.py. From backend/:

    uv run python scripts/seed.py           # add the mock data, unless it is there
    uv run python scripts/seed.py --reset   # replace it, with fresh times
"""

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Run as a file, Python puts scripts/ on the path, not the folder that holds app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Base, Session
from app.core.phones import is_mobile
from app.core.settings import db_host, get_settings, is_local_db
from app.models import (
    Answer,
    Call,
    CallTrigger,
    CallTurn,
    Campaign,
    CampaignKind,
    Consent,
    ConsentDecision,
    ConsentMethod,
    EnrollmentState,
    Event,
    EventType,
    Grant,
    Incident,
    IncidentOutcome,
    IncidentStatus,
    ReportSource,
    Role,
    Senior,
    SeniorStatus,
    Speaker,
    StatusReport,
    TurnKind,
    User,
    WarningLevel,
    WatchCondition,
    WatchState,
    WelcomeOutcome,
)
from app.seniors.service import sync_senior_grant
from app.status.engine import BUCHAREST, Certainty, Question, Severity
from app.voice.calls import CallState, was_answered
from app.voice.dialogue import CONSENT_TEXT, CONSENT_VERSION

# uuid5 under this namespace: the same ids on every machine and every run.
NAMESPACE = uuid.UUID("5e1a0000-5eed-4000-8000-000000000000")


def seed_id(*parts: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, "/".join(parts))


@dataclass(frozen=True)
class Person:
    phone: str
    name: str
    practice: str | None = None


# The first two are Firebase test numbers; an existing user keeps their name.
DAS = Person("+40700000001", "DAS Test")
MEDIC = Person("+40700000002", "Medic Test", "CMI Test")
DAS_2 = Person("+40700000301", "Cristian Pavel")
MEDIC_2 = Person("+40700000302", "Dr. Andrei Vlad", "CMI Dr. Andrei Vlad, Timișoara")
STAFF_GRANTS = (
    (DAS, Role.das),
    (DAS_2, Role.das),
    (MEDIC, Role.medic),
    (MEDIC_2, Role.medic),
)


@dataclass(frozen=True)
class SeniorSpec:
    key: str
    full_name: str
    form_of_address: str
    phone: str
    state: EnrollmentState
    medic: Person
    registered_days_ago: float
    caregivers: tuple[tuple[Person, str], ...] = ()
    address: dict[str, str] = field(default_factory=dict)


# The two landlines, Ion's and Constantin's, are valid Timișoara numbers in a 0256 000
# block, unlikely to be anyone's; the mobiles are made up too (05 §5).
# fmt: off
SENIORS = (
    SeniorSpec(
        "maria", "Maria Popescu", "doamna Maria", "+40700000005",
        EnrollmentState.active, MEDIC, 21,
        ((Person("+40700000004", "Andrei Popescu"), "fiu"),),
        {"street": "Calea Aradului", "street_number": "12", "block": "A3",
         "staircase": "B", "floor": "2", "apartment": "14", "intercom_code": "14",
         "key_holder": "Vecina de la ap. 15, doamna Ileana",
         "landmark": "Blocul de lângă farmacie"},
    ),
    SeniorSpec(
        "ion", "Ion Dumitrescu", "domnul Ion", "+40256000101",
        EnrollmentState.active, MEDIC, 33,
        ((Person("+40700000201", "Cristina Dumitrescu"), "fiică"),),
        {"street": "Strada Lipovei", "street_number": "45",
         "key_holder": "Fiica, Cristina, locuiește la 10 minute",
         "landmark": "Casă cu poartă verde, după școală"},
    ),
    SeniorSpec(
        "elena", "Elena Stan", "doamna Elena", "+40700000103",
        EnrollmentState.active, MEDIC, 47,
        ((Person("+40700000202", "Mihai Stan"), "nepot"),),
        {"street": "Bulevardul Eroilor de la Tisa", "street_number": "22",
         "block": "E5", "staircase": "A", "floor": "4", "apartment": "17",
         "intercom_code": "17", "key_holder": "Nepotul, Mihai Stan",
         "landmark": "Bloc cu magazin alimentar la parter"},
    ),
    SeniorSpec(
        "gheorghe", "Gheorghe Ionescu", "domnul Gheorghe", "+40700000104",
        EnrollmentState.active, MEDIC_2, 62,
        ((Person("+40700000203", "Laura Ionescu"), "noră"),),
        {"street": "Strada Mărășești", "street_number": "8", "block": "3",
         "staircase": "A", "floor": "1", "apartment": "5", "intercom_code": "5"},
    ),
    SeniorSpec(
        "ana", "Ana Constantinescu", "doamna Ana", "+40700000105",
        EnrollmentState.active, MEDIC, 52,
        ((Person("+40700000204", "Radu Constantinescu"), "fiu"),),
        {"street": "Strada Alba Iulia", "street_number": "3", "floor": "3",
         "apartment": "9", "intercom_code": "9", "key_holder": "Fiul, Radu",
         "landmark": "Clădire veche, intrarea prin curte"},
    ),
    SeniorSpec(
        "vasile", "Vasile Munteanu", "domnul Vasile", "+40700000106",
        EnrollmentState.active, MEDIC_2, 42,
        ((Person("+40700000205", "Ioana Munteanu"), "fiică"),),
        {"street": "Calea Șagului", "street_number": "101", "block": "22",
         "staircase": "C", "floor": "7", "apartment": "84", "intercom_code": "84",
         "landmark": "Ultimul bloc înainte de supermarket"},
    ),
    SeniorSpec(
        "florica", "Florica Radu", "doamna Florica", "+40700000107",
        EnrollmentState.active, MEDIC, 70,
        ((Person("+40700000210", "Gabriela Radu"), "fiică"),),
        {"street": "Calea Girocului", "street_number": "54", "block": "15",
         "staircase": "B", "floor": "2", "apartment": "11", "intercom_code": "11B",
         "key_holder": "Vecina de la ap. 12, doamna Rodica",
         "landmark": "Lângă stația de tramvai"},
    ),
    SeniorSpec(
        "constantin", "Constantin Barbu", "domnul Constantin", "+40256000102",
        EnrollmentState.submitted, MEDIC_2, 2,
        ((Person("+40700000206", "Sorin Barbu"), "fiu"),),
        {"street": "Strada Gheorghe Lazăr", "street_number": "17",
         "key_holder": "Fiul, Sorin", "landmark": "Casă galbenă cu gard de fier",
         "call_window": "dimineața, 9–12"},
    ),
    SeniorSpec(
        "elisabeta", "Elisabeta Nagy", "doamna Elisabeta", "+40700000109",
        EnrollmentState.submitted, MEDIC, 1,
        ((Person("+40700000207", "Katalin Nagy"), "fiică"),),
        {"street": "Bulevardul Take Ionescu", "street_number": "30", "block": "B2",
         "staircase": "A", "floor": "3", "apartment": "12", "intercom_code": "12"},
    ),
    # A medic still filling in the form: no number on the street, no caregiver yet.
    SeniorSpec(
        "petru", "Petru Moldovan", "domnul Petru", "+40700000110",
        EnrollmentState.draft, MEDIC, 0.2,
        address={"street": "Strada Cluj"},
    ),
    SeniorSpec(
        "silvia", "Silvia Toma", "doamna Silvia", "+40700000111",
        EnrollmentState.accepted, MEDIC_2, 4,
        ((Person("+40700000208", "Dan Toma"), "soț"),),
        {"street": "Calea Buziașului", "street_number": "9", "block": "4",
         "staircase": "A", "floor": "P", "apartment": "2", "intercom_code": "2"},
    ),
    SeniorSpec(
        "nicolae", "Nicolae Lazăr", "domnul Nicolae", "+40700000112",
        EnrollmentState.refused, MEDIC, 9,
        ((Person("+40700000209", "Adriana Lazăr"), "fiică"),),
        {"street": "Strada Arieș", "street_number": "14", "block": "7",
         "staircase": "B", "floor": "2", "apartment": "8"},
    ),
)
# fmt: on

CAMPAIGN_ID = seed_id("campaign", "cold")
# The seed's ids are uuid5 and the API's uuidv7, so this finds every senior any version
# of the seed made, even one since renamed or dropped from SENIORS.
SEEDED = func.uuid_extract_version(Senior.id) == 5


def people() -> list[Person]:
    """Staff and caregivers; sync_senior_grant makes the seniors' own users."""
    found = {p.phone: p for p, _ in STAFF_GRANTS}
    for s in SENIORS:
        found.update((p.phone, p) for p, _ in s.caregivers)
    return list(found.values())


AGENT, SENIOR, SYSTEM = Speaker.agent, Speaker.senior, Speaker.system
KEYS = TurnKind.keys
# The weekdays as a senior says them, Monday first; the engine compares them without
# diacritics (03 §3).
DAY_NAMES = ("luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică")
HAND_OVER = "vă fac legătura acum cu un dispecer DAS. Vă rog să rămâneți la telefon."
TRANSFERRED = "Apel transferat către dispeceratul DAS."
PICKED_UP = "Dispecerul DAS a preluat apelul."


class History:
    """The rows behind the seniors, timed in minutes before `now`."""

    def __init__(self, now: datetime, users: dict[str, uuid.UUID]) -> None:
        self.now = now
        self.users = users
        self.seniors: dict[str, Senior] = {}
        self.grants: list[dict[str, Any]] = []
        self.campaign: Campaign | None = None
        self.calls: list[Call] = []
        # Everything else; each row points only at seniors, users and calls.
        self.rows: list[Base] = []

    def ago(self, minutes: float) -> datetime:
        return self.now - timedelta(minutes=minutes)

    def grant(
        self,
        person: Person,
        role: Role,
        senior: str = "",
        relation: str | None = None,
        granted_by: uuid.UUID | None = None,
    ) -> None:
        # Every row has every key: a multi-row insert takes its columns from the first.
        self.grants.append(
            {
                "user_id": self.users[person.phone],
                "role": role,
                "senior_id": self.seniors[senior].id if senior else None,
                "relation": relation,
                "granted_by": granted_by,
            }
        )

    def register(self, spec: SeniorSpec) -> None:
        senior = Senior(
            id=seed_id("senior", spec.key),
            medic_id=self.users[spec.medic.phone],
            full_name=spec.full_name,
            form_of_address=spec.form_of_address,
            phone_e164=spec.phone,
            phone_is_landline=not is_mobile(spec.phone),
            enrollment_state=spec.state,
            created_at=self.ago(spec.registered_days_ago * 24 * 60),
            **spec.address,
        )
        self.seniors[spec.key] = senior
        medic = self.users[spec.medic.phone]
        for person, relation in spec.caregivers:
            self.grant(person, Role.caregiver, spec.key, relation, granted_by=medic)

    def call(
        self,
        senior: str,
        name: str,
        trigger: CallTrigger,
        minutes_ago: float,
        state: CallState,
        *,
        previous: Call | None = None,
        starting: Severity = Severity.green,
        final: Severity | None = None,
        certainty: Certainty | None = None,
        reason: str | None = None,
        summary: str | None = None,
        welcome: WelcomeOutcome | None = None,
        handover_answered: bool | None = None,
        seconds: int = 80,
    ) -> Call:
        due = self.ago(minutes_ago)
        answered = was_answered(state)
        call = Call(
            id=seed_id("call", senior, name),
            senior_id=self.seniors[senior].id,
            trigger=trigger,
            campaign_id=self.campaign.id if trigger is CallTrigger.campaign else None,
            previous_call_id=previous and previous.id,
            attempt=previous.attempt + 1 if previous else 1,
            starting_severity=starting,
            state=state,
            due_at=due,
            # A redial is queued when the attempt before it ends (03 §9).
            created_at=previous.ended_at if previous else due,
            twilio_call_id=f"CA{seed_id('twilio', senior, name).hex}",
            started_at=due + timedelta(seconds=15) if answered else None,
            ended_at=due + timedelta(seconds=15 + seconds if answered else 45),
            final_severity=final,
            final_certainty=certainty,
            reason=reason,
            summary=summary,
            welcome_outcome=welcome,
            handover_answered=handover_answered,
        )
        self.calls.append(call)
        return call

    def turn_at(self, call: Call, position: int) -> datetime:
        return call.started_at + timedelta(seconds=7 * position)

    def say(self, call: Call, *lines: tuple[Any, ...]) -> None:
        """(speaker, content) for speech, (speaker, keys, KEYS) for a key press."""
        for position, (speaker, content, *kind) in enumerate(lines, start=1):
            spoken = speaker is SENIOR and not kind
            self.rows.append(
                CallTurn(
                    id=seed_id("turn", str(call.id), str(position)),
                    call_id=call.id,
                    position=position,
                    speaker=speaker,
                    kind=kind[0] if kind else TurnKind.speech,
                    content=content,
                    confidence=0.91 if spoken else None,
                    at=self.turn_at(call, position),
                )
            )

    def answer(
        self, call: Call, question: Question, value: str, words: str, position: int
    ) -> None:
        self.rows.append(
            Answer(
                id=seed_id("answer", str(call.id), question),
                call_id=call.id,
                field=question,
                value=value,
                clear=True,
                quote=words,
                at=self.turn_at(call, position),
            )
        )

    def report(
        self,
        call: Call,
        source: ReportSource,
        severity: Severity,
        reason: str,
        *,
        certainty: Certainty | None = None,
        quote: str | None = None,
        position: int = 0,
    ) -> None:
        at = self.turn_at(call, position) if call.started_at else call.ended_at
        key = (str(call.id), source, severity.name, str(position))
        self.rows.append(
            StatusReport(
                id=seed_id("report", *key),
                call_id=call.id,
                source=source,
                severity=severity,
                certainty=certainty,
                reason=reason,
                quote=quote,
                at=at,
            )
        )

    def status(self, senior: str, call: Call, since: datetime | None = None) -> None:
        self.rows.append(
            SeniorStatus(
                senior_id=self.seniors[senior].id,
                code=call.final_severity,
                reason=call.reason,
                since=since or call.ended_at,
                source_call_id=call.id,
            )
        )

    def watch(
        self,
        senior: str,
        state: WatchCondition,
        minutes_ago: float,
        battery: int,
        pulse: int | None = None,
        worn: bool | None = True,
    ) -> None:
        self.rows.append(
            WatchState(
                senior_id=self.seniors[senior].id,
                state=state,
                last_check_in_at=self.ago(minutes_ago),
                battery=battery,
                worn=worn,
                last_pulse=pulse,
            )
        )

    def event(
        self,
        senior: str,
        type: EventType,
        call: Call,
        *,
        snapshot: dict[str, Any] | None = None,
        location: tuple[float, float, float] | None = None,
    ) -> None:
        """What queued `call`, sent by the phone app a moment before."""
        measured = call.created_at - timedelta(seconds=20)
        latitude, longitude, accuracy = location or (None, None, None)
        self.rows.append(
            Event(
                id=seed_id("event", senior, type),
                senior_id=self.seniors[senior].id,
                type=type,
                measured_at=measured,
                received_at=measured + timedelta(seconds=3),
                snapshot=snapshot,
                latitude=latitude,
                longitude=longitude,
                location_accuracy_m=accuracy,
                located_at=location and measured - timedelta(minutes=2),
                call_id=call.id,
            )
        )

    def incident(
        self,
        senior: str,
        call: Call,
        opened: datetime,
        *,
        taken_by: Person | None = None,
        resolved_minutes_ago: float | None = None,
        outcome: IncidentOutcome | None = None,
        note: str | None = None,
    ) -> None:
        """Taken a minute after it opened, and resolved by whoever took it."""
        taker = taken_by and self.users[taken_by.phone]
        resolved = resolved_minutes_ago is not None
        if resolved:
            status = IncidentStatus.resolved
        else:
            status = IncidentStatus.in_progress if taker else IncidentStatus.open
        self.rows.append(
            Incident(
                id=seed_id("incident", senior, str(call.id)),
                senior_id=self.seniors[senior].id,
                opened_by_call_id=call.id,
                status=status,
                reason=call.reason,
                opened_at=opened,
                taken_by=taker,
                taken_at=taker and opened + timedelta(minutes=1),
                resolved_by=taker if resolved else None,
                resolved_at=self.ago(resolved_minutes_ago) if resolved else None,
                outcome=outcome,
                note=note,
            )
        )

    def day(self, minutes_ago: float) -> str:
        """The weekday in Timișoara at that time, as said."""
        return DAY_NAMES[self.ago(minutes_ago).astimezone(BUCHAREST).weekday()]

    def welcome(self, senior: str, days_ago: float, refused: str | None = None) -> None:
        """The welcome call and its consent (UC-04); `refused` is the senior's no."""
        s = self.seniors[senior]
        call = self.call(
            senior,
            "welcome",
            CallTrigger.welcome,
            days_ago * 24 * 60,
            CallState.completed,
            welcome=WelcomeOutcome.confirmed,
            seconds=95,
        )
        title = s.form_of_address.split()[0]
        identity = (
            f"Bună ziua. Sunt asistentul automat al DAS Timișoara. Vorbesc cu {title} "
            f"{s.full_name}? Dacă da, apăsați 1 sau spuneți «da». Dacă {title} nu "
            "poate veni acum la telefon, apăsați 2. Dacă ați primit acest apel din "
            "greșeală, apăsați 3."
        )
        lines: list[tuple[Any, ...]] = [
            (AGENT, identity),
            (SENIOR, "1", KEYS),
            (AGENT, CONSENT_TEXT),
        ]
        if refused:
            lines += [
                (SENIOR, refused),
                (AGENT, "Am înțeles. Nu vă vom mai suna. O zi bună!"),
            ]
        else:
            lines += [
                (SENIOR, "1", KEYS),
                (
                    AGENT,
                    (
                        "Vă rugăm să salvați acest număr. Nu vă vom cere niciodată "
                        "bani sau date."
                    ),
                ),
            ]
        self.say(call, *lines)
        self.rows.append(
            Consent(
                id=seed_id("consent", senior),
                senior_id=s.id,
                decision=ConsentDecision.refused if refused else ConsentDecision.given,
                method=ConsentMethod.call,
                text_version=CONSENT_VERSION,
                call_id=call.id,
                evidence=(
                    {"identity": "1", "consent": refused, "confidence": 0.91}
                    if refused
                    else {"identity": "1", "consent": "1"}
                ),
                at=call.ended_at,
            )
        )

    def cold_call(
        self,
        senior: str,
        name: str,
        minutes_ago: float,
        *,
        feeling: tuple[str, str],
        day: tuple[str, str],
        shelter: tuple[str, str],
        final: Severity,
        reason: str,
        summary: str,
        previous: Call | None = None,
        hand_over: bool = False,
    ) -> Call:
        """A campaign's wellbeing call with the three questions (UC-05 to UC-08), each
        answered as (value, words)."""
        s = self.seniors[senior]
        call = self.call(
            senior,
            name,
            CallTrigger.campaign,
            minutes_ago,
            CallState.handed_over if hand_over else CallState.completed,
            previous=previous,
            final=final,
            certainty=Certainty.high,
            reason=reason,
            summary=summary,
            handover_answered=False if hand_over else None,
        )
        greeting = (
            f"Bună ziua, {s.form_of_address}. Sunt asistentul automat al DAS "
            "Timișoara. Vă sunăm pentru că vin zile reci. Cum vă simțiți astăzi?"
        )
        lines: list[tuple[Any, ...]] = [
            (AGENT, greeting),
            (SENIOR, feeling[1]),
            (AGENT, "Îmi spuneți, vă rog, ce zi a săptămânii este astăzi?"),
            (SENIOR, day[1]),
            (AGENT, "Aveți căldură în casă?"),
            (SENIOR, shelter[1]),
        ]
        if hand_over:
            # Not capitalize(), which would lowercase the name: "Domnul ion".
            name_first = s.form_of_address[:1].upper() + s.form_of_address[1:]
            lines += [(AGENT, f"{name_first}, {HAND_OVER}"), (SYSTEM, TRANSFERRED)]
        else:
            goodbye = (
                f"Vă mulțumesc, {s.form_of_address}. Îmbrăcați-vă gros și beți ceva "
                "cald. O zi bună!"
            )
            lines.append((AGENT, goodbye))
        self.say(call, *lines)
        for question, (value, words), position in (
            (Question.feeling, feeling, 2),
            (Question.orientation, day, 4),
            (Question.shelter, shelter, 6),
        ):
            self.answer(call, question, value, words, position)
        if not hand_over:
            worrying = shelter[1] if shelter[0] == "no" else None
            self.report(
                call,
                ReportSource.rules,
                final,
                reason,
                certainty=Certainty.high,
                quote=worrying,
                position=6,
            )
        return call


def build(now: datetime, users: dict[str, uuid.UUID]) -> History:
    h = History(now, users)
    for spec in SENIORS:
        h.register(spec)
    for person, role in STAFF_GRANTS:
        granted_by = None if person is DAS else users[DAS.phone]
        h.grant(person, role, granted_by=granted_by)
    h.campaign = Campaign(
        id=CAMPAIGN_ID,
        kind=CampaignKind.cold,
        level=WarningLevel.yellow,
        started_by=users[DAS.phone],
        started_at=h.ago(125),
        warning_until=h.ago(125) + timedelta(hours=24),  # Q4
    )
    green = "Se simte bine, știe ce zi este și are căldură"

    def today(minutes_ago: float) -> tuple[str, str]:
        named = h.day(minutes_ago)
        return named, f"{named.capitalize()}."

    # Maria Popescu: green, a quiet day.
    h.welcome("maria", 19)
    call = h.cold_call(
        "maria",
        "campaign",
        118,
        feeling=("ok", "Bine, am fost la piață azi-dimineață."),
        day=today(118),
        shelter=("yes", "Da, am pus aerotermul."),
        final=Severity.green,
        reason=green,
        summary="Doamna Maria se simte bine, a spus corect ziua și are căldură în casă.",
    )
    h.status("maria", call)
    h.watch("maria", WatchCondition.ok, 4, battery=82, pulse=74)

    # Ion Dumitrescu: a landline, no watch. Unwell, then no heating at home: red on the
    # last answer, handed over minutes ago and not picked up yet, so the incident is still
    # open. Red acts at once (03 §6), so the hand-over follows the answer that made it.
    h.welcome("ion", 31)
    first = h.call("ion", "campaign-1", CallTrigger.campaign, 40, CallState.unanswered)
    unwell = "Nu prea bine, mă doare capul de dimineață."
    cold = "Nu, încă nu ne-au dat căldura. E frig la mine."
    call = h.cold_call(
        "ion",
        "campaign-2",
        10,
        previous=first,
        feeling=("unwell", unwell),
        day=today(10),
        shelter=("no", cold),
        final=Severity.red,
        hand_over=True,
        reason="Se simte rău și nu are căldură",
        summary="Domnul Ion spune că îl doare capul de dimineață și nu are căldură în "
        "casă. Transferat către DAS.",
    )
    h.report(
        call,
        ReportSource.rules,
        Severity.yellow,
        "Se simte rău",
        certainty=Certainty.low,
        quote=unwell,
        position=2,
    )
    h.report(
        call,
        ReportSource.rules,
        Severity.red,
        call.reason,
        certainty=Certainty.high,
        quote=cold,
        position=6,
    )
    opened = h.turn_at(call, 6)
    h.status("ion", call, since=opened)
    h.incident("ion", call, opened)

    # Elena Stan: green on the campaign, then the watch's SOS button and a fall. DAS
    # answered the hand-over, which took the incident: it is in progress.
    h.welcome("elena", 45)
    h.cold_call(
        "elena",
        "campaign",
        115,
        feeling=("ok", "Bine, mulțumesc de întrebare."),
        day=today(115),
        shelter=("yes", "Da, avem centrală."),
        final=Severity.green,
        reason=green,
        summary="Doamna Elena se simte bine, a spus corect ziua și are căldură în casă.",
    )
    fell = "Am căzut în baie și nu mă pot ridica."
    call = h.call(
        "elena",
        "sos",
        CallTrigger.watch,
        24,
        CallState.handed_over,
        starting=Severity.yellow,
        final=Severity.red,
        certainty=Certainty.low,
        reason="Căzătură, nu se poate ridica",
        summary="Doamna Elena a căzut în baie și nu se poate ridica. Transferată "
        "către DAS.",
        handover_answered=True,
        seconds=40,
    )
    h.event(
        "elena",
        EventType.sos_button,
        call,
        snapshot={"pulse": 118, "battery": 64},
        location=(45.7590, 21.2275, 11.0),
    )
    h.say(
        call,
        (
            AGENT,
            (
                "Bună ziua, doamna Elena. Sunt asistentul automat al DAS Timișoara. "
                "Am primit un semnal de la ceasul dumneavoastră. Sunteți bine?"
            ),
        ),
        (SENIOR, fell),
        (AGENT, f"Doamna Elena, {HAND_OVER}"),
        (SYSTEM, TRANSFERRED),
        (SYSTEM, PICKED_UP),
    )
    h.report(call, ReportSource.trigger, Severity.yellow, "Butonul SOS al ceasului")
    h.report(
        call,
        ReportSource.alarm_tier1,
        Severity.red,
        "Căzătură",
        certainty=Certainty.low,
        quote=fell,
        position=2,
    )
    opened = h.turn_at(call, 2)
    h.status("elena", call, since=opened)
    h.incident("elena", call, opened, taken_by=DAS)
    h.watch("elena", WatchCondition.ok, 2, battery=63, pulse=112)

    # Gheorghe Ionescu: fine and oriented, but no heating yet: yellow. His watch is on
    # the table.
    h.welcome("gheorghe", 60)
    call = h.cold_call(
        "gheorghe",
        "campaign",
        113,
        feeling=("ok", "Bine, nu mă plâng."),
        day=today(113),
        shelter=("no", "Nu prea. Încă nu ne-au dat drumul la căldură și e frig."),
        final=Severity.yellow,
        reason="Nu are căldură în casă",
        summary="Domnul Gheorghe se simte bine și știe ce zi este, dar nu are căldură "
        "în casă. Familia a fost anunțată.",
    )
    h.status("gheorghe", call)
    h.watch("gheorghe", WatchCondition.not_worn, 35, battery=45, worn=False)

    # Ana Constantinescu: a high pulse at rest this morning, a confirmed call for help,
    # and a dispatcher who found her better. Green again on the campaign.
    h.welcome("ana", 50)
    first = h.call(
        "ana",
        "pulse-1",
        CallTrigger.watch,
        228,
        CallState.unanswered,
        starting=Severity.yellow,
    )
    h.event(
        "ana",
        EventType.high_pulse_at_rest,
        first,
        snapshot={"pulse": 132, "battery": 74},
    )
    # A watch trigger's yellow acts on the first unanswered attempt (03 §6).
    h.report(
        first,
        ReportSource.unanswered,
        Severity.yellow,
        "Nu a răspuns la prima încercare",
    )
    help_ = "Mi-e foarte rău, am palpitații."
    call = h.call(
        "ana",
        "pulse-2",
        CallTrigger.watch,
        218,
        CallState.handed_over,
        previous=first,
        starting=Severity.yellow,
        final=Severity.red,
        certainty=Certainty.low,
        reason="Spune că îi este foarte rău și cere ajutor",
        summary="Doamna Ana are palpitații, spune că îi este foarte rău și a confirmat "
        "că are nevoie de ajutor. Transferată către DAS.",
        handover_answered=True,
        seconds=60,
    )
    h.say(
        call,
        (
            AGENT,
            (
                "Bună ziua, doamna Ana. Sunt asistentul automat al DAS Timișoara. "
                "Ceasul ne-a arătat un puls foarte mare. Cum vă simțiți?"
            ),
        ),
        (SENIOR, help_),
        (
            AGENT,
            (
                "Ați spus că vă este foarte rău. Aveți nevoie de ajutor acum? Spuneți "
                "«da» sau apăsați 1. Dacă nu, spuneți «nu» sau apăsați 2."
            ),
        ),
        (SENIOR, "1", KEYS),
        (AGENT, f"Doamna Ana, {HAND_OVER}"),
        (SYSTEM, TRANSFERRED),
        (SYSTEM, PICKED_UP),
    )
    h.report(
        call,
        ReportSource.alarm_tier2,
        Severity.red,
        call.reason,
        certainty=Certainty.low,
        quote=help_,
        position=4,
    )
    h.incident(
        "ana",
        call,
        h.turn_at(call, 4),
        taken_by=DAS_2,
        resolved_minutes_ago=185,
        outcome=IncidentOutcome.senior_ok,
        note="Am vorbit cu doamna Ana: palpitațiile au trecut după ce s-a odihnit. "
        "Fiul a ajuns la ea și o duce mâine la medicul de familie.",
    )
    call = h.cold_call(
        "ana",
        "campaign",
        112,
        feeling=("ok", "Mai bine acum, mulțumesc."),
        day=today(112),
        shelter=("yes", "Da, am căldură."),
        final=Severity.green,
        reason=green,
        summary="Doamna Ana se simte mai bine, a spus corect ziua și are căldură în casă.",
    )
    h.status("ana", call)
    h.watch("ana", WatchCondition.ok, 6, battery=71, pulse=81)

    # Vasile Munteanu: no answer twice, and the watch has been off since last night.
    h.welcome("vasile", 40)
    first = h.call(
        "vasile", "campaign-1", CallTrigger.campaign, 117, CallState.unanswered
    )
    call = h.call(
        "vasile",
        "campaign-2",
        CallTrigger.campaign,
        87,
        CallState.unanswered,
        previous=first,
        final=Severity.yellow,
        reason="Nu a răspuns la apeluri",
    )
    h.report(call, ReportSource.unanswered, Severity.yellow, "Nu a răspuns de două ori")
    h.status("vasile", call)
    h.watch("vasile", WatchCondition.offline, 540, battery=4, worn=None)

    # Florica Radu: pressed "Sunați-mă" last night after a fall; DAS sent a team.
    h.welcome("florica", 68)
    fell = "Am amețit și am căzut, nu mă pot ridica de pe jos."
    call = h.call(
        "florica",
        "request",
        CallTrigger.manual,
        899,
        CallState.handed_over,
        starting=Severity.yellow,
        final=Severity.red,
        certainty=Certainty.low,
        reason="Căzătură, nu se poate ridica",
        summary="Doamna Florica a amețit, a căzut și nu se poate ridica de pe jos. "
        "Transferată către DAS.",
        handover_answered=True,
        seconds=45,
    )
    h.event(
        "florica", EventType.manual_request, call, location=(45.7362, 21.2401, 25.0)
    )
    h.say(
        call,
        (
            AGENT,
            (
                "Bună ziua, doamna Florica. Sunt asistentul automat al DAS Timișoara. "
                "Ați cerut să vă sunăm. Cum vă simțiți?"
            ),
        ),
        (SENIOR, fell),
        (AGENT, f"Doamna Florica, {HAND_OVER}"),
        (SYSTEM, TRANSFERRED),
        (SYSTEM, PICKED_UP),
    )
    h.report(call, ReportSource.trigger, Severity.yellow, "A cerut să fie sunată")
    h.report(
        call,
        ReportSource.alarm_tier1,
        Severity.red,
        "Căzătură",
        certainty=Certainty.low,
        quote=fell,
        position=2,
    )
    h.incident(
        "florica",
        call,
        h.turn_at(call, 2),
        taken_by=DAS,
        resolved_minutes_ago=840,
        outcome=IncidentOutcome.team_sent,
        note="Echipa DAS a ajuns în 20 de minute; vecina de la ap. 12 a deschis ușa. "
        "Doamna Florica avea doar o vânătaie și a rămas acasă. Fiica a fost anunțată.",
    )
    call = h.cold_call(
        "florica",
        "campaign",
        110,
        feeling=("ok", "Bine, doar mă mai doare genunchiul."),
        day=today(110),
        shelter=("yes", "Da, am căldură."),
        final=Severity.green,
        reason=green,
        summary="Doamna Florica se simte bine după căzătura de aseară, a spus corect "
        "ziua și are căldură în casă.",
    )
    h.status("florica", call)
    h.watch("florica", WatchCondition.ok, 11, battery=55, pulse=78)

    # Nicolae Lazăr said no on the welcome call.
    h.welcome("nicolae", 5, refused="Nu, nu vreau să fiu sunat.")
    return h


async def add_people(session: AsyncSession) -> dict[str, uuid.UUID]:
    """Each number's user, made unless the number already has one. Users stay through
    --reset, with their sign-in, push tokens and duty."""
    everyone = people()
    # user_for in bulk, with the medics' practice.
    await session.execute(
        insert(User)
        .values(
            [
                {"phone_e164": p.phone, "display_name": p.name, "practice": p.practice}
                for p in everyone
            ]
        )
        .on_conflict_do_nothing(index_elements=[User.phone_e164])
    )
    phones = [p.phone for p in everyone]
    rows = await session.execute(
        select(User.phone_e164, User.id).where(User.phone_e164.in_(phones))
    )
    return dict(rows.all())


async def save(session: AsyncSession, history: History) -> None:
    # In foreign key order, a flush per step: the models declare no relationships.
    session.add_all(history.seniors.values())
    await session.flush()
    # ON CONFLICT DO NOTHING: a staff grant the number already holds.
    await session.execute(insert(Grant).values(history.grants).on_conflict_do_nothing())
    for senior in history.seniors.values():
        await sync_senior_grant(session, senior)
    # A mobile already another senior's gets no grant of its own (AL7).
    seniors = {s.id: s for s in history.seniors.values()}
    granted = set(
        await session.scalars(
            select(Grant.senior_id).where(
                Grant.role == Role.senior, Grant.senior_id.in_(list(seniors))
            )
        )
    )
    for s in seniors.values():
        if not s.phone_is_landline and s.id not in granted:
            print(
                f"{s.phone_e164} is already another senior's: it signs in to them, "
                f"not to {s.full_name} (AL7).",
                file=sys.stderr,
            )
    # Kept through --reset, fresh times and all: other seniors' calls may name it.
    await session.merge(history.campaign)
    await session.flush()
    session.add_all(history.calls)  # in order, so a redial follows its first attempt
    await session.flush()
    session.add_all(history.rows)
    await session.flush()


async def remove(session: AsyncSession) -> None:
    """The seed's seniors and everything about them, including what was added through
    the API since; their caregiver and senior grants go with them (ON DELETE CASCADE).
    Users, staff grants and the campaign stay."""
    seniors = select(Senior.id).where(SEEDED)
    calls = select(Call.id).where(Call.senior_id.in_(seniors))
    for table in (CallTurn, Answer, StatusReport):
        await session.execute(delete(table).where(table.call_id.in_(calls)))
    for table in (Incident, SeniorStatus, WatchState, Consent, Event):
        await session.execute(delete(table).where(table.senior_id.in_(seniors)))
    await session.execute(delete(Call).where(Call.senior_id.in_(seniors)))
    await session.execute(delete(Senior).where(SEEDED))


async def seed(reset: bool = False, now: datetime | None = None) -> str:
    """Returns seeded, reseeded, or already seeded."""
    url = get_settings().database_url
    if not is_local_db(url):
        raise SystemExit(f"Refusing to seed {db_host(url)}: mock data stays local.")
    async with Session() as session:
        there = await session.scalar(select(Senior.id).where(SEEDED).limit(1))
        if there and not reset:
            return "already seeded"
        if there:
            await remove(session)
        history = build(now or datetime.now(UTC), await add_people(session))
        await save(session, history)
        await session.commit()
    return "reseeded" if there else "seeded"


def main() -> int:
    parser = argparse.ArgumentParser(description="Mock data for the local database.")
    parser.add_argument("--reset", action="store_true", help="replace it, fresh times")
    result = asyncio.run(seed(parser.parse_args().reset))
    print(result)
    if result == "already seeded":
        print("Run with --reset to replace it with fresh times.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
