"""Fill the local database with fictitious people and their history, a starting point for
the dashboard and the apps. The demo uses fictitious people only (05 §5).

Twenty-one seniors in Timișoara, one or more in every enrollment state, with their medics
and caregivers; a second DAS employee; a cold-weather campaign; wellbeing calls with
their transcripts, answers and status reports; watch check-ins; and fourteen incidents,
four open, four in progress and six resolved, so every dashboard screen has something
on it. Every active senior has weeks of earlier wellbeing calls, and each answered
wellbeing call its fixed-text summary version, so the briefing, the incident dossier and
the observations show with no model or key (design §6; staging seed design §4.4). Eugenia
Tudor is the summary demo: six calls over three weeks that show a slow decline and a
broken heater.

The seniors and their history have fixed uuid5 ids, so a second run adds nothing.
--reset deletes every senior the seed made and everything about them, including calls,
incidents, caregivers and edits made through the API since, then makes them again,
timed relative to now (resolved incidents leave the dashboard after a day, 04 §1).
Users, staff grants and the campaign stay and are reused, and so do the seniors made
through the API, with their history. The Firebase test numbers sign in to it
(backend/README.md): +40700000001 as DAS, +40700000002 as the medic of most seniors,
+40700000004 as Maria Popescu's son and +40700000005 as Maria Popescu, unless that number
is already another senior's (AL7), which the run reports.

Locally, from backend/:

    uv run python scripts/seed.py           # add the mock data, unless it is there
    uv run python scripts/seed.py --reset   # replace it, with fresh times

On staging, inside the api container (a cloud database is refused from a laptop, as in
alembic/env.py, and production always):

    railway ssh -s api -e staging -- python scripts/seed.py --confirm staging

There nobody gets das, since the test numbers' codes are public, and the campaign has
already lapsed (staging seed design §4.2, §4.3). DIAL_ALLOWLIST keeps every seeded
number from ringing.
"""

import argparse
import asyncio
import math
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

from app.auth.service import sync_senior_grant
from app.calls.ending import campaign_reason, redial_delay
from app.core.db import Base, Session
from app.core.phones import is_mobile
from app.core.settings import get_settings, is_local_db
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
    SummaryVersion,
    TurnKind,
    User,
    WarningLevel,
    WatchCondition,
    WatchReading,
    WatchState,
    WelcomeOutcome,
)
from app.seniors.schemas import Citation, FollowUp, SummaryContent, Trend
from app.status.engine import BUCHAREST, Certainty, Question, Severity
from app.voice.calls import CallState, was_answered
from app.voice.dialogue import CONSENT_TEXT, CONSENT_VERSION
from scripts.seed_cast import check_target

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
    # The next six each hold an unresolved incident, so the board has cards to triage.
    SeniorSpec(
        "dumitru", "Dumitru Pop", "domnul Dumitru", "+40700000113",
        EnrollmentState.active, MEDIC, 38,
        ((Person("+40700000211", "Simona Pop"), "fiică"),),
        {"street": "Strada Bucovinei", "street_number": "27", "block": "H4",
         "staircase": "A", "floor": "5", "apartment": "31", "intercom_code": "31",
         "key_holder": "Fiica, Simona, are cheie de rezervă",
         "landmark": "Lângă parcul din cartier"},
    ),
    SeniorSpec(
        "aurelia", "Aurelia Marinescu", "doamna Aurelia", "+40700000114",
        EnrollmentState.active, MEDIC_2, 55,
        ((Person("+40700000212", "Cătălin Marinescu"), "fiu"),),
        {"street": "Strada Cluj", "street_number": "6", "floor": "1",
         "apartment": "3", "intercom_code": "3",
         "landmark": "Casă veche cu două intrări"},
    ),
    SeniorSpec(
        "teodor", "Teodor Crișan", "domnul Teodor", "+40700000115",
        EnrollmentState.active, MEDIC, 29,
        ((Person("+40700000213", "Mirela Crișan"), "nepoată"),),
        {"street": "Bulevardul Cetății", "street_number": "11", "block": "C7",
         "staircase": "B", "floor": "3", "apartment": "20", "intercom_code": "20",
         "key_holder": "Vecinul de la ap. 21, domnul Sorin"},
    ),
    SeniorSpec(
        "viorica", "Viorica Bălan", "doamna Viorica", "+40700000116",
        EnrollmentState.active, MEDIC_2, 44,
        ((Person("+40700000214", "Horia Bălan"), "fiu"),),
        {"street": "Strada Take Ionescu", "street_number": "52", "block": "D1",
         "staircase": "C", "floor": "4", "apartment": "27", "intercom_code": "27",
         "landmark": "Vizavi de librărie"},
    ),
    SeniorSpec(
        "gavril", "Gavril Szabó", "domnul Gavril", "+40700000117",
        EnrollmentState.active, MEDIC, 66,
        ((Person("+40700000215", "Emese Szabó"), "fiică"),),
        {"street": "Strada Memorandumului", "street_number": "19", "floor": "2",
         "apartment": "6", "intercom_code": "6",
         "key_holder": "Fiica, Emese, locuiește în apropiere",
         "landmark": "Clădire cu scări exterioare"},
    ),
    SeniorSpec(
        "margareta", "Margareta Oprea", "doamna Margareta", "+40700000118",
        EnrollmentState.active, MEDIC_2, 36,
        ((Person("+40700000216", "Bogdan Oprea"), "nepot"),),
        {"street": "Calea Lipovei", "street_number": "73", "block": "27",
         "staircase": "A", "floor": "6", "apartment": "42", "intercom_code": "42",
         "landmark": "Lângă spitalul de copii"},
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
    # The welcome call never reached them: a second unanswered attempt, and a wrong number.
    SeniorSpec(
        "stefan", "Ștefan Rusu", "domnul Ștefan", "+40700000119",
        EnrollmentState.unreachable, MEDIC, 6,
        ((Person("+40700000217", "Camelia Rusu"), "fiică"),),
        {"street": "Strada Memorandumului", "street_number": "21", "block": "C4",
         "staircase": "A", "floor": "1", "apartment": "5", "intercom_code": "5"},
    ),
    SeniorSpec(
        "rodica", "Rodica Neagu", "doamna Rodica", "+40700000120",
        EnrollmentState.wrong_number, MEDIC, 7,
        ((Person("+40700000218", "Victor Neagu"), "fiu"),),
        {"street": "Calea Martirilor", "street_number": "40", "block": "11",
         "staircase": "B", "floor": "4", "apartment": "19", "intercom_code": "19"},
    ),
    # The summary demo (design §6): a slow decline, no incident.
    SeniorSpec(
        "eugenia", "Eugenia Tudor", "doamna Eugenia", "+40700000121",
        EnrollmentState.active, MEDIC, 30,
        address={"street": "Strada Pestalozzi", "street_number": "14", "floor": "2",
                 "apartment": "7", "intercom_code": "7"},
    ),
)
# fmt: on

CAMPAIGN_ID = seed_id("campaign", "cold")
PAST_CAMPAIGN_ID = seed_id("campaign", "cold-earlier")
# The seed's ids are uuid5 and the API's uuidv7, so this finds every senior any version
# of the seed made, even one since renamed or dropped from SENIORS.
SEEDED = func.uuid_extract_version(Senior.id) == 5


# What the medic declared (design 2026-11-14), so the dashboard shows each case: a watch
# that reports, none, a watch that never reported (aurelia), a home node (gheorghe),
# the app alone (silvia). Seniors not named stay null, as if registered before.
WATCH = ["smartphone", "watch"]
EQUIPMENT: dict[str, list[str]] = {
    **dict.fromkeys(
        (
            "maria",
            "elena",
            "ana",
            "vasile",
            "florica",
            "dumitru",
            "viorica",
            "gavril",
            "margareta",
            "aurelia",
        ),
        WATCH,
    ),
    "gheorghe": [*WATCH, "home_node"],
    "ion": [],
    "constantin": [],
    "teodor": [],
    "silvia": ["smartphone"],
}


def people() -> list[Person]:
    """Staff and caregivers; sync_senior_grant makes the seniors' own users."""
    found = {p.phone: p for p, _ in STAFF_GRANTS}
    for s in SENIORS:
        found.update((p.phone, p) for p, _ in s.caregivers)
    return list(found.values())


AGENT, SENIOR, SYSTEM = Speaker.agent, Speaker.senior, Speaker.system
DISPATCHER = Speaker.das
KEYS = TurnKind.keys
# The weekdays as a senior says them, Monday first; the engine compares them without
# diacritics (03 §3).
DAY_NAMES = ("luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică")
HAND_OVER = "vă fac legătura acum cu un dispecer DAS. Vă rog să rămâneți la telefon."
TRANSFERRED = "Apel transferat către dispeceratul DAS."
PICKED_UP = "Dispecerul DAS a preluat apelul."
# What the agent says and what the status report names, by what queued the call (UC-09).
OPENING = {
    EventType.sos_button: "Am primit un semnal de la ceasul dumneavoastră. Sunteți bine?",
    EventType.high_pulse_at_rest: "Ceasul ne-a arătat un puls foarte mare. Cum vă simțiți?",
    EventType.inactivity: "Ceasul nu a mai înregistrat nicio mișcare de ceva vreme. "
    "Sunteți bine?",
    EventType.manual_request: "Ați cerut să vă sunăm. Cum vă simțiți?",
}
TRIGGER_REASON = {
    EventType.sos_button: "Butonul SOS al ceasului",
    EventType.high_pulse_at_rest: "Puls mare în repaus",
    EventType.inactivity: "Fără mișcare de câteva ore",
    EventType.manual_request: "A cerut să fie sunată",
}


class History:
    """The rows behind the seniors, timed in minutes before `now`."""

    def __init__(self, now: datetime, users: dict[str, uuid.UUID]) -> None:
        self.now = now
        self.users = users
        self.seniors: dict[str, Senior] = {}
        self.grants: list[dict[str, Any]] = []
        self.campaign: Campaign | None = None
        # The cold spell before it: campaign calls dated before `campaign` started.
        self.past_campaign: Campaign | None = None
        self.calls: list[Call] = []
        # Everything else; each row points only at seniors, users and calls.
        self.rows: list[Base] = []
        # Summary versions, in each senior's call order: each one points at that
        # senior's one before.
        self.summaries: list[SummaryVersion] = []

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
        created = self.ago(spec.registered_days_ago * 24 * 60)
        # Submitted soon after registering, accepted by the DAS soon after that, for the
        # states past each (the medic's enrollment timeline).
        past_draft = spec.state is not EnrollmentState.draft
        past_submitted = past_draft and spec.state is not EnrollmentState.submitted
        senior = Senior(
            id=seed_id("senior", spec.key),
            medic_id=self.users[spec.medic.phone],
            full_name=spec.full_name,
            form_of_address=spec.form_of_address,
            phone_e164=spec.phone,
            phone_is_landline=not is_mobile(spec.phone),
            enrollment_state=spec.state,
            created_at=created,
            submitted_at=created + timedelta(hours=2) if past_draft else None,
            accepted_at=created + timedelta(hours=20) if past_submitted else None,
            accepted_by=self.users[DAS.phone] if past_submitted else None,
            equipment=EQUIPMENT.get(spec.key),
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
            campaign_id=(
                None
                if trigger is not CallTrigger.campaign
                else self.campaign.id
                if due >= self.campaign.started_at
                else self.past_campaign.id
            ),
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
        senior_id = self.seniors[senior].id
        resting = pulse - 6 if pulse else None
        self.rows.append(
            WatchState(
                senior_id=senior_id,
                state=state,
                last_check_in_at=self.ago(minutes_ago),
                battery=battery,
                worn=worn,
                last_pulse=pulse,
                resting_pulse=resting,
                steps_today=1840 if pulse else None,
                minutes_without_steps=12 if pulse else None,
            )
        )
        # A day of readings up to the last check-in, every 5 minutes (ADR-006): a slow
        # wave around the latest pulse, the battery draining towards the latest value
        for i in range(288):
            back = minutes_ago + 5 * i
            if back > 24 * 60:
                break
            self.rows.append(
                WatchReading(
                    senior_id=senior_id,
                    measured_at=self.ago(back),
                    pulse=round(pulse + 8 * math.sin(i / 12)) if pulse else None,
                    resting_pulse=resting,
                    steps_today=max(0, 1840 - 7 * i) if pulse else None,
                    battery=min(100, battery + i // 6),
                    worn=worn,
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

    def emergency(
        self,
        senior: str,
        event_type: EventType,
        minutes_ago: float,
        said: str,
        reason: str,
        summary: str,
        *,
        answered: bool = False,
        snapshot: dict[str, Any] | None = None,
        location: tuple[float, float, float] | None = None,
        **resolution: Any,
    ) -> Call:
        """A watch or "Sunați-mă" event, the call it queued, and the red the senior's
        first words made: handed over, then an incident. `answered` is whether DAS
        picked up the hand-over; `resolution` goes to incident()."""
        manual = event_type is EventType.manual_request
        call = self.call(
            senior,
            "alarm",
            CallTrigger.manual if manual else CallTrigger.watch,
            minutes_ago,
            CallState.handed_over,
            starting=Severity.yellow,
            final=Severity.red,
            certainty=Certainty.low,
            reason=reason,
            summary=summary,
            handover_answered=answered,
            seconds=45,
        )
        self.event(senior, event_type, call, snapshot=snapshot, location=location)
        form = self.seniors[senior].form_of_address
        lines: list[tuple[Any, ...]] = [
            (
                AGENT,
                f"Bună ziua, {form}. Sunt asistentul automat al DAS Timișoara. "
                + OPENING[event_type],
            ),
            (SENIOR, said),
            (AGENT, f"{form[:1].upper()}{form[1:]}, {HAND_OVER}"),
            (SYSTEM, TRANSFERRED),
        ]
        if answered:
            lines.append((SYSTEM, PICKED_UP))
        self.say(call, *lines)
        self.report(
            call, ReportSource.trigger, Severity.yellow, TRIGGER_REASON[event_type]
        )
        self.report(
            call,
            ReportSource.alarm_tier1,
            Severity.red,
            reason,
            certainty=Certainty.low,
            quote=said,
            position=2,
        )
        opened = self.turn_at(call, 2)
        self.incident(senior, call, opened, **resolution)
        if "resolved_minutes_ago" not in resolution:
            self.status(senior, call, since=opened)
        return call

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

    def welcome_unreached(
        self, senior: str, days_ago: float, *, wrong: bool = False
    ) -> None:
        """A welcome call that reached no consent (UC-04): a wrong number on the first
        attempt, or two unanswered ones, the redial after the delay (03 §9)."""
        if wrong:
            call = self.call(
                senior,
                "welcome",
                CallTrigger.welcome,
                days_ago * 24 * 60,
                CallState.completed,
                welcome=WelcomeOutcome.wrong_number,
                seconds=25,
            )
            s = self.seniors[senior]
            title = s.form_of_address.split()[0]
            self.say(
                call,
                (
                    AGENT,
                    (
                        "Bună ziua. Sunt asistentul automat al DAS Timișoara. Vorbesc "
                        f"cu {title} {s.full_name}? Dacă ați primit acest apel din "
                        "greșeală, apăsați 3."
                    ),
                ),
                (SENIOR, "3", KEYS),
                (AGENT, "Ne cerem scuze pentru deranj. O zi bună!"),
            )
            return
        first = self.call(
            senior,
            "welcome",
            CallTrigger.welcome,
            days_ago * 24 * 60,
            CallState.unanswered,
            welcome=WelcomeOutcome.no_answer,
        )
        self.call(
            senior,
            "welcome-2",
            CallTrigger.welcome,
            days_ago * 24 * 60 - redial_delay().total_seconds() / 60,
            CallState.unanswered,
            previous=first,
            welcome=WelcomeOutcome.no_answer,
        )

    def summarize(self, senior: str, call: Call, **content: Any) -> None:
        """The fixed-text version for `call`, chained to that senior's one before
        (design §6)."""
        senior_id = self.seniors[senior].id
        chain = [v for v in self.summaries if v.senior_id == senior_id]
        self.summaries.append(
            SummaryVersion(
                id=seed_id("summary", senior, str(len(chain) + 1)),
                senior_id=senior_id,
                call_id=call.id,
                previous_id=chain[-1].id if chain else None,
                content=SummaryContent(**content).model_dump(mode="json"),
                model="seed",
                created_at=call.ended_at + timedelta(seconds=30),
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


def build(
    now: datetime, users: dict[str, uuid.UUID], *, cloud: bool = False
) -> History:
    """`cloud`: staging, where only the team holds das, since the Firebase test numbers'
    codes are published in the README, and the campaign has already lapsed, so one the
    team starts is not answered by it (04 §2; staging seed design §4.2, §4.3)."""
    h = History(now, users)
    for spec in SENIORS:
        h.register(spec)
    for person, role in STAFF_GRANTS:
        if cloud and role is Role.das:
            continue
        granted_by = None if person is DAS else users[DAS.phone]
        h.grant(person, role, granted_by=granted_by)
    h.campaign = Campaign(
        id=CAMPAIGN_ID,
        kind=CampaignKind.cold,
        level=WarningLevel.yellow,
        started_by=users[DAS.phone],
        started_at=h.ago(125),
        # Q4; on staging lapsed a few minutes ago.
        warning_until=h.ago(5) if cloud else h.ago(125) + timedelta(hours=24),
    )
    # Weeks of earlier wellbeing calls belong to an earlier, lapsed warning, or the
    # running campaign's progress would count seniors it never called (04 §2).
    h.past_campaign = Campaign(
        id=PAST_CAMPAIGN_ID,
        kind=CampaignKind.cold,
        level=WarningLevel.yellow,
        started_by=users[DAS.phone],
        started_at=h.ago(22 * 24 * 60),
        warning_until=h.ago(130),
    )
    green = "Se simte bine, știe ce zi este și are căldură"

    def today(minutes_ago: float) -> tuple[str, str]:
        named = h.day(minutes_ago)
        return named, f"{named.capitalize()}."

    # Maria Popescu: green, a quiet day.
    h.welcome("maria", 19)
    # A scare that was nothing: low certainty on "era să cad", and DAS found her fine.
    h.emergency(
        "maria",
        EventType.manual_request,
        300,
        "Era să cad din picioare, mi s-a făcut rău puțin.",
        "Spune că era să cadă",
        "Doamna Maria spune că era să cadă și i s-a făcut rău puțin. Transferată "
        "către DAS.",
        answered=True,
        location=(45.7502, 21.2154, 18.0),
        taken_by=DAS,
        resolved_minutes_ago=270,
        outcome=IncidentOutcome.false_alarm,
        note="Doamna Maria a scăpat o oală și s-a speriat; nu a căzut și nu are nimic. "
        "Nu are nevoie de ajutor. Fiul a fost anunțat.",
    )
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
    h.emergency(
        "elena",
        EventType.inactivity,
        560,
        "Am amețit rău și nu mă simt în stare să mă ridic.",
        "Amețeală, nu se simte în stare să se ridice",
        "Doamna Elena a amețit rău și nu se simte în stare să se ridice. Transferată "
        "către DAS.",
        answered=True,
        snapshot={"battery": 66},
        taken_by=DAS_2,
        resolved_minutes_ago=500,
        outcome=IncidentOutcome.team_sent,
        note="Echipa DAS a găsit-o cu tensiunea scăzută și a dus-o la Urgențe pentru "
        "control. Nepotul, Mihai, a fost anunțat.",
    )
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
        # Ends at the hand-over, as a real one does; the talk with DAS comes after.
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
        # The hand-over's talk, as Twilio transcribes it (04 §4.4 step 5).
        (
            DISPATCHER,
            "Bună ziua, doamna Elena, sunteți la dispeceratul DAS. Mă auziți?",
        ),
        (SENIOR, "Da, vă aud. Sunt jos, în baie."),
        (
            DISPATCHER,
            "Nu încercați să vă ridicați. Trimitem acum un echipaj la dumneavoastră.",
        ),
        (SENIOR, "Ușa e încuiată. Cheia o are vecina de la etajul doi."),
        (
            DISPATCHER,
            "Am notat. Echipajul ajunge în zece minute. Rămân la telefon cu dumneavoastră.",
        ),
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
    h.emergency(
        "gheorghe",
        EventType.high_pulse_at_rest,
        420,
        "Am o durere puternică în piept, mă sufoc.",
        "Durere în piept și greutate la respirație",
        "Domnul Gheorghe are o durere puternică în piept și se sufocă. Transferat "
        "către DAS.",
        answered=True,
        snapshot={"pulse": 141, "battery": 58},
        taken_by=DAS,
        resolved_minutes_ago=330,
        outcome=IncidentOutcome.called_112,
        note="Am apelat 112; ambulanța a ajuns în 12 minute și l-a dus la Urgențe. "
        "Nora, Laura, a plecat după el la spital și a fost anunțată.",
    )
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
    # The line dropped after his first words, and nobody could reach him again.
    h.emergency(
        "vasile",
        EventType.manual_request,
        700,
        "Mi-e foarte rău, nu mai pot să stau în picioare…",
        "Spune că îi este foarte rău, apelul s-a întrerupt",
        "Domnul Vasile a spus că îi este foarte rău, apoi apelul s-a întrerupt. "
        "Transferat către DAS, dar legătura nu s-a mai putut face.",
        location=(45.7398, 21.2056, 30.0),
        taken_by=DAS_2,
        resolved_minutes_ago=620,
        outcome=IncidentOutcome.not_reached,
        note="Am sunat de 3 ori înapoi și am încercat-o pe fiica Ioana, fără răspuns. "
        "Echipa a trecut pe la adresă: nu era acasă, iar vecinii spun că a plecat "
        "la țară.",
    )
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

    # The board's open column: handed over, and nobody at DAS has picked up yet.
    h.welcome("dumitru", 36)
    h.emergency(
        "dumitru",
        EventType.sos_button,
        18,
        "Mă strânge în piept și nu pot respira bine.",
        "Durere în piept, greutate la respirație",
        "Domnul Dumitru spune că îl strânge în piept și nu poate respira bine. "
        "Transferat către DAS.",
        snapshot={"pulse": 124, "battery": 58},
        location=(45.7489, 21.2087, 14.0),
    )
    h.watch("dumitru", WatchCondition.ok, 1, battery=57, pulse=121)

    h.welcome("aurelia", 53)
    call = h.cold_call(
        "aurelia",
        "campaign",
        56,
        feeling=("unwell", "Nu mă simt bine, am amețeli și mi-e frig."),
        day=today(56),
        shelter=("no", "Nu, centrala s-a stricat de ieri."),
        final=Severity.red,
        hand_over=True,
        reason="Amețeli și nu are căldură",
        summary="Doamna Aurelia are amețeli și nu are căldură în casă, centrala fiind "
        "stricată. Transferată către DAS.",
    )
    h.report(
        call,
        ReportSource.rules,
        Severity.red,
        call.reason,
        certainty=Certainty.high,
        quote="Nu, centrala s-a stricat de ieri.",
        position=6,
    )
    opened = h.turn_at(call, 6)
    h.status("aurelia", call, since=opened)
    h.incident("aurelia", call, opened)

    h.welcome("teodor", 27)
    h.emergency(
        "teodor",
        EventType.manual_request,
        7,
        "Nu-mi mai simt mâna stângă și vorbesc greu.",
        "Mâna stângă fără sensibilitate, vorbește greu",
        "Domnul Teodor nu își mai simte mâna stângă și vorbește greu. Transferat "
        "către DAS.",
        location=(45.7571, 21.2310, 20.0),
    )

    # In progress: DAS answered the hand-over and took the incident.
    h.welcome("viorica", 42)
    h.emergency(
        "viorica",
        EventType.high_pulse_at_rest,
        75,
        "Mi-e rău, inima îmi bate foarte tare și mi-e frică.",
        "Inima bate foarte tare, spune că îi este frică",
        "Doamna Viorica spune că inima îi bate foarte tare și că îi este frică. "
        "Transferată către DAS.",
        answered=True,
        snapshot={"pulse": 139, "battery": 47},
        taken_by=DAS,
    )
    h.watch("viorica", WatchCondition.ok, 3, battery=46, pulse=128)

    h.welcome("gavril", 64)
    h.emergency(
        "gavril",
        EventType.sos_button,
        33,
        "Am alunecat pe scări și mă doare tare șoldul.",
        "Căzătură pe scări, durere la șold",
        "Domnul Gavril a căzut pe scări și îl doare tare șoldul. Transferat către DAS.",
        answered=True,
        snapshot={"pulse": 96, "battery": 71},
        location=(45.7712, 21.2334, 9.0),
        taken_by=DAS_2,
    )
    h.watch("gavril", WatchCondition.ok, 2, battery=70, pulse=102)

    h.welcome("margareta", 34)
    h.emergency(
        "margareta",
        EventType.inactivity,
        48,
        "Am amețit, mă simt foarte slăbită și nu mă pot ridica din fotoliu.",
        "Amețeală, slăbiciune, nu se poate ridica",
        "Doamna Margareta a amețit, se simte foarte slăbită și nu se poate ridica "
        "din fotoliu. Transferată către DAS.",
        answered=True,
        snapshot={"battery": 39},
        taken_by=DAS,
    )
    h.watch("margareta", WatchCondition.ok, 1, battery=38, pulse=88)

    # Nicolae Lazăr said no on the welcome call.
    h.welcome("nicolae", 5, refused="Nu, nu vreau să fiu sunat.")

    # Ștefan Rusu never picked up, twice; Rodica Neagu's number was someone else's.
    # Each after DAS accepted them, 20 hours after registering (`register`).
    h.welcome_unreached("stefan", 5)
    h.welcome_unreached("rodica", 6, wrong=True)
    decline(h)
    histories(h)
    return h


def named_call(h: History, senior: str, name: str) -> Call:
    return next(c for c in h.calls if c.id == seed_id("call", senior, name))


def earlier(
    h: History, senior: str, *plan: tuple[float, tuple[str, str], tuple[str, str]]
) -> list[Call]:
    """Earlier answered campaign calls, oldest first, each (days ago, feeling, shelter)
    with the right day. At most one worrying answer each, so the rules give green or
    yellow (03 §3)."""
    form = h.seniors[senior].form_of_address
    calls = []
    for n, (days_ago, feeling, shelter) in enumerate(plan, start=1):
        minutes = days_ago * 24 * 60
        worrying = [
            q
            for q, bad in (
                (Question.feeling, feeling[0] == "unwell"),
                (Question.shelter, shelter[0] == "no"),
            )
            if bad
        ]
        assert len(worrying) <= 1, (senior, n)  # two would be red (03 §3)
        named = h.day(minutes)
        calls.append(
            h.cold_call(
                senior,
                f"earlier-{n}",
                minutes,
                feeling=feeling,
                day=(named, f"{named.capitalize()}."),
                shelter=shelter,
                final=Severity.yellow if worrying else Severity.green,
                reason=campaign_reason(worrying, CampaignKind.cold),
                summary=f"{form[:1].upper()}{form[1:]}: {feeling[1]} {shelter[1]}",
            )
        )
    return calls


def ask(topic: str, question: str, call: Call, quote: str) -> FollowUp:
    return FollowUp(topic=topic, question=question, call_id=call.id, quote=quote)


def histories(h: History) -> None:
    """Weeks of earlier wellbeing calls for every other active senior, and the summary
    version each answered wellbeing call would have produced, in call order, so the
    briefing and the incident dossier have something on them (staging seed design §4.4).
    Quotes are the senior's own words: an earlier call's answers, the current call's
    turns, or a citation carried from the version before (design §4)."""
    warm = ("yes", "Da, am căldură.")
    plain = "Vorbește clar și răspunde scurt."

    # Maria Popescu: goes out every week; knees on the stairs; a near-fall today.
    m1, m2, m3 = earlier(
        h,
        "maria",
        (12, ("ok", "Bine, mulțumesc, am fost la vecina la o cafea."), warm),
        (8, ("ok", "Bine, doar mă dor puțin genunchii când urc scările."), warm),
        (
            4,
            ("ok", "Bine, am ieșit la plimbare în parc."),
            ("yes", "Da, merge centrala."),
        ),
    )
    alarm, campaign = (
        named_call(h, "maria", "alarm"),
        named_call(h, "maria", "campaign"),
    )
    talk = ["Îi place să povestească; lăsați-o să termine."]
    knees = ask(
        "genunchii",
        "Cum vă mai simțiți genunchii, doamna Maria?",
        m2,
        "mă dor puțin genunchii când urc scările",
    )
    near = ask(
        "era să cadă",
        "Data trecută mi-ați spus că era să cădeți. Cum vă mai simțiți?",
        alarm,
        "era să cad din picioare",
    )
    h.summarize(
        "maria",
        m1,
        follow_ups=[],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Maria se descurcă singură și iese din casă; a fost la o "
        "vecină la cafea.",
    )
    h.summarize(
        "maria",
        m2,
        follow_ups=[knees],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Maria se descurcă singură, dar o dor genunchii când urcă "
        "scările.",
    )
    h.summarize(
        "maria",
        m3,
        follow_ups=[knees],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Maria iese în continuare din casă, la plimbare în parc. "
        "Genunchii o mai supără pe scări.",
    )
    h.summarize(
        "maria",
        alarm,
        follow_ups=[near, knees],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Maria a cerut să fie sunată: era să cadă și i s-a făcut rău "
        "puțin. A fost transferată către DAS, care a găsit-o bine.",
    )
    h.summarize(
        "maria",
        campaign,
        follow_ups=[near, knees],
        how_to_talk=talk,
        trends=[
            Trend(
                note="Iese din casă în fiecare săptămână: la vecină, în parc, la piață.",
                direction="steady",
                evidence=[
                    Citation(call_id=m1.id, quote="am fost la vecina la o cafea"),
                    Citation(call_id=m3.id, quote="am ieșit la plimbare în parc"),
                    Citation(
                        call_id=campaign.id, quote="am fost la piață azi-dimineață"
                    ),
                ],
            )
        ],
        narrative="Doamna Maria se simte bine și a fost la piață, la câteva ore după "
        "ce era să cadă. Iese din casă în fiecare săptămână; genunchii o supără pe "
        "scări.",
    )

    # Ion Dumitrescu: the block's heating never came on, colder from call to call.
    i1, i2, i3 = earlier(
        h,
        "ion",
        (12, ("ok", "Bine, mulțumesc."), ("yes", "Da, deocamdată e bine.")),
        (
            7,
            ("ok", "Bine, dar seara se face frig în casă."),
            ("yes", "Da, am un radiator electric."),
        ),
        (
            3,
            ("ok", "Merge, m-am îmbrăcat mai gros."),
            ("no", "Nu, nu ne-au dat încă drumul la căldură la bloc."),
        ),
    )
    last = named_call(h, "ion", "campaign-2")
    talk = ["Telefon fix: vorbiți rar și repetați întrebarea dacă nu răspunde."]
    evening = ask(
        "frigul de seara",
        "Mai e frig seara în casă, domnule Ion?",
        i2,
        "seara se face frig în casă",
    )
    heating = ask(
        "căldura la bloc",
        "Data trecută nu vă dăduseră drumul la căldură. S-a rezolvat?",
        i3,
        "nu ne-au dat încă drumul la căldură la bloc",
    )
    h.summarize(
        "ion",
        i1,
        follow_ups=[],
        how_to_talk=talk,
        trends=[],
        narrative="Domnul Ion se descurcă singur și are căldură deocamdată.",
    )
    h.summarize(
        "ion",
        i2,
        follow_ups=[evening],
        how_to_talk=talk,
        trends=[],
        narrative="Domnul Ion se simte bine, dar seara îi e frig în casă și folosește "
        "un radiator electric.",
    )
    h.summarize(
        "ion",
        i3,
        follow_ups=[heating, evening],
        how_to_talk=talk,
        trends=[],
        narrative="Domnul Ion nu are căldură: blocului nu i s-a dat încă drumul la "
        "căldură. S-a îmbrăcat mai gros.",
    )
    h.summarize(
        "ion",
        last,
        follow_ups=[
            ask(
                "durerea de cap",
                "Vă mai doare capul, domnule Ion?",
                last,
                "mă doare capul de dimineață",
            ),
            heating,
        ],
        how_to_talk=talk,
        trends=[
            Trend(
                note="Frigul din casă a crescut de la un apel la altul: întâi seara, "
                "apoi toată ziua.",
                direction="worse",
                evidence=[
                    Citation(call_id=i2.id, quote="seara se face frig în casă"),
                    Citation(
                        call_id=i3.id,
                        quote="nu ne-au dat încă drumul la căldură la bloc",
                    ),
                    Citation(call_id=last.id, quote="e frig la mine"),
                ],
            )
        ],
        narrative="Domnul Ion se simte rău, îl doare capul de dimineață și tot nu are "
        "căldură. Transferat către DAS.",
    )

    # Elena Stan: dizzy when she stands, then a dizzy spell, then a fall today.
    e1, e2 = earlier(
        h,
        "elena",
        (
            10,
            ("ok", "Bine, nepotul a fost la mine ieri."),
            ("yes", "Da, avem centrală."),
        ),
        (
            5,
            ("ok", "Bine, doar amețesc uneori când mă ridic."),
            ("yes", "Da, e cald în casă."),
        ),
    )
    alarm = named_call(h, "elena", "alarm")
    campaign, sos = named_call(h, "elena", "campaign"), named_call(h, "elena", "sos")
    talk = ["Vorbiți rar; îi place să audă de nepotul ei, Mihai."]
    standing = ask(
        "amețeala când se ridică",
        "Mai amețiți când vă ridicați, doamna Elena?",
        e2,
        "amețesc uneori când mă ridic",
    )
    spell = ask(
        "amețeala de azi-noapte",
        "Cum vă simțiți după amețeala de azi-noapte?",
        alarm,
        "am amețit rău",
    )
    h.summarize(
        "elena",
        e1,
        follow_ups=[],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Elena se descurcă bine; nepotul o vizitează.",
    )
    h.summarize(
        "elena",
        e2,
        follow_ups=[standing],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Elena se simte bine, dar amețește uneori când se ridică.",
    )
    h.summarize(
        "elena",
        alarm,
        follow_ups=[spell, standing],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Elena a amețit rău și nu s-a putut ridica. Echipa DAS a dus-o "
        "la Urgențe pentru control.",
    )
    h.summarize(
        "elena",
        campaign,
        follow_ups=[spell, standing],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Elena se simte bine după amețeala de azi-noapte și are "
        "căldură.",
    )
    h.summarize(
        "elena",
        sos,
        follow_ups=[
            ask(
                "căzătura din baie",
                "Cum vă simțiți după căzătura din baie, doamna Elena?",
                sos,
                "am căzut în baie și nu mă pot ridica",
            ),
            standing,
        ],
        how_to_talk=talk,
        trends=[
            Trend(
                note="Amețelile s-au înmulțit în ultimele zile și au dus la o căzătură.",
                direction="worse",
                evidence=[
                    Citation(call_id=e2.id, quote="amețesc uneori când mă ridic"),
                    Citation(call_id=alarm.id, quote="am amețit rău"),
                    Citation(call_id=sos.id, quote="am căzut în baie"),
                ],
            )
        ],
        narrative="Doamna Elena a căzut în baie și nu se poate ridica; ușa e încuiată "
        "și cheia o are vecina de la etajul doi. Transferată către DAS.",
    )

    # Gheorghe Ionescu: tires on the stairs; chest pain this morning; no heating yet.
    g1, g2 = earlier(
        h,
        "gheorghe",
        (14, ("ok", "Bine, mă descurc."), ("yes", "Da, am pornit radiatorul.")),
        (
            6,
            ("ok", "Bine, dar obosesc repede când urc scările."),
            ("yes", "Da, e destul de cald."),
        ),
    )
    alarm = named_call(h, "gheorghe", "alarm")
    campaign = named_call(h, "gheorghe", "campaign")
    talk = ["Răspunde scurt; întrebați-l direct cum se simte."]
    tired = ask(
        "oboseala pe scări",
        "Mai obosiți când urcați scările, domnule Gheorghe?",
        g2,
        "obosesc repede când urc scările",
    )
    chest = ask(
        "durerea în piept",
        "Cum vă simțiți după durerea în piept de azi-dimineață?",
        alarm,
        "am o durere puternică în piept",
    )
    h.summarize(
        "gheorghe",
        g1,
        follow_ups=[],
        how_to_talk=talk,
        trends=[],
        narrative="Domnul Gheorghe se descurcă singur.",
    )
    h.summarize(
        "gheorghe",
        g2,
        follow_ups=[tired],
        how_to_talk=talk,
        trends=[],
        narrative="Domnul Gheorghe se simte bine, dar obosește repede pe scări.",
    )
    h.summarize(
        "gheorghe",
        alarm,
        follow_ups=[chest, tired],
        how_to_talk=talk,
        trends=[],
        narrative="Domnul Gheorghe a avut o durere puternică în piept și se sufoca. DAS "
        "a sunat la 112 și ambulanța l-a dus la Urgențe.",
    )
    h.summarize(
        "gheorghe",
        campaign,
        follow_ups=[
            ask(
                "căldura",
                "V-au dat drumul la căldură, domnule Gheorghe?",
                campaign,
                "încă nu ne-au dat drumul la căldură",
            ),
            chest,
            tired,
        ],
        how_to_talk=talk,
        trends=[],
        narrative="Domnul Gheorghe spune că e bine după durerea în piept, dar încă nu "
        "are căldură în casă.",
    )

    # Ana Constantinescu: a racing heart in the evenings, palpitations today, better now.
    a1, a2 = earlier(
        h,
        "ana",
        (11, ("ok", "Bine, doar inima o ia uneori la galop seara."), warm),
        (
            6,
            ("ok", "Bine, am luat pastilele și m-am liniștit."),
            ("yes", "Da, e cald."),
        ),
    )
    pulse, campaign = named_call(h, "ana", "pulse-2"), named_call(h, "ana", "campaign")
    talk = ["Se liniștește dacă vorbiți calm; nu o grăbiți."]
    racing = ask(
        "inima seara",
        "Ați mai simțit inima bătând repede seara, doamna Ana?",
        a1,
        "inima o ia uneori la galop seara",
    )
    palpitations = ask(
        "palpitațiile",
        "Cum vă mai simțiți inima, doamna Ana?",
        pulse,
        "mi-e foarte rău, am palpitații",
    )
    h.summarize(
        "ana",
        a1,
        follow_ups=[racing],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Ana se descurcă, dar seara simte uneori inima bătând repede.",
    )
    h.summarize(
        "ana",
        a2,
        follow_ups=[racing],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Ana își ia pastilele și se simte liniștită.",
    )
    h.summarize(
        "ana",
        pulse,
        follow_ups=[palpitations, racing],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Ana a avut palpitații și i-a fost foarte rău. DAS a vorbit cu "
        "ea: palpitațiile au trecut după ce s-a odihnit.",
    )
    h.summarize(
        "ana",
        campaign,
        follow_ups=[palpitations],
        how_to_talk=talk,
        trends=[
            Trend(
                note="Se simte mai bine după palpitațiile de azi.",
                direction="better",
                evidence=[
                    Citation(call_id=pulse.id, quote="mi-e foarte rău, am palpitații"),
                    Citation(call_id=campaign.id, quote="mai bine acum"),
                ],
            )
        ],
        narrative="Doamna Ana se simte mai bine după palpitațiile de azi, a spus corect "
        "ziua și are căldură.",
    )

    # Florica Radu: dizzy mornings, a fall last night, a sore knee today.
    f1, f2 = earlier(
        h,
        "florica",
        (13, ("ok", "Bine, fiica m-a dus la cumpărături."), warm),
        (5, ("ok", "Bine, dar am amețit puțin dimineață."), ("yes", "Da, e cald.")),
    )
    fall = named_call(h, "florica", "request")
    campaign = named_call(h, "florica", "campaign")
    talk = [plain]
    dizzy = ask(
        "amețeala de dimineață",
        "Mai amețiți dimineața, doamna Florica?",
        f2,
        "am amețit puțin dimineață",
    )
    fell = ask(
        "căzătura",
        "Cum vă simțiți după căzătura de aseară?",
        fall,
        "am amețit și am căzut",
    )
    h.summarize(
        "florica",
        f1,
        follow_ups=[],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Florica se descurcă; fiica o ajută cu cumpărăturile.",
    )
    h.summarize(
        "florica",
        f2,
        follow_ups=[dizzy],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Florica se simte bine, dar a amețit puțin dimineață.",
    )
    h.summarize(
        "florica",
        fall,
        follow_ups=[fell, dizzy],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Florica a amețit și a căzut și nu s-a putut ridica. DAS a "
        "trimis o echipă.",
    )
    h.summarize(
        "florica",
        campaign,
        follow_ups=[
            ask(
                "genunchiul",
                "Vă mai doare genunchiul, doamna Florica?",
                campaign,
                "mă mai doare genunchiul",
            ),
            fell,
            dizzy,
        ],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Florica se simte bine după căzătura de aseară, dar o mai "
        "doare genunchiul.",
    )

    # Aurelia Marinescu: a noisy boiler, broken since yesterday.
    r1, r2 = earlier(
        h,
        "aurelia",
        (12, ("ok", "Bine, mulțumesc."), ("yes", "Da, merge centrala.")),
        (
            6,
            ("ok", "Bine, dar centrala face niște zgomote ciudate."),
            ("yes", "Da, deocamdată merge."),
        ),
    )
    campaign = named_call(h, "aurelia", "campaign")
    talk = [plain]
    noises = ask(
        "centrala",
        "Ați chemat pe cineva să vadă centrala, doamna Aurelia?",
        r2,
        "centrala face niște zgomote ciudate",
    )
    h.summarize(
        "aurelia",
        r1,
        follow_ups=[],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Aurelia se descurcă și are căldură.",
    )
    h.summarize(
        "aurelia",
        r2,
        follow_ups=[noises],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Aurelia se simte bine, dar centrala face zgomote ciudate.",
    )
    h.summarize(
        "aurelia",
        campaign,
        follow_ups=[
            ask(
                "centrala stricată",
                "S-a reparat centrala, doamna Aurelia?",
                campaign,
                "centrala s-a stricat de ieri",
            ),
            ask(
                "amețelile",
                "Mai aveți amețeli?",
                campaign,
                "am amețeli și mi-e frig",
            ),
        ],
        how_to_talk=talk,
        trends=[],
        narrative="Doamna Aurelia are amețeli și îi e frig: centrala s-a stricat de "
        "ieri, după ce făcuse zgomote. Transferată către DAS.",
    )

    # The six whose open incident came from the watch or "Sunați-mă": quiet weeks
    # before it, so their incident dossier has a briefing. Each: (senior, how the agent
    # addresses them, two earlier answers, the topic one raised, the alarm's topic and
    # quote, and the three narratives).
    quiet = (
        (
            "vasile",
            "domnule Vasile",
            ("Bine, am fost la pescuit cu un prieten.", "Bine, doar dorm cam prost."),
            ("somnul", "Ați dormit mai bine, domnule Vasile?", "dorm cam prost"),
            ("nu mai poate sta în picioare", "nu mai pot să stau în picioare"),
            (
                "Domnul Vasile se descurcă singur și iese cu prietenii.",
                "Domnul Vasile se simte bine, dar doarme prost.",
                (
                    "Domnul Vasile a spus că îi e foarte rău și nu mai poate sta în "
                    "picioare; apelul s-a întrerupt și nu a mai putut fi găsit."
                ),
            ),
        ),
        (
            "dumitru",
            "domnule Dumitru",
            ("Bine, am grijă de grădină.", "Bine, doar urc mai greu la etaj."),
            (
                "urcatul la etaj",
                "Mai urcați greu la etaj, domnule Dumitru?",
                "urc mai greu la etaj",
            ),
            ("strânsoarea în piept", "mă strânge în piept"),
            (
                "Domnul Dumitru se descurcă singur și se ocupă de grădină.",
                "Domnul Dumitru se simte bine, dar urcă mai greu la etaj.",
                (
                    "Domnul Dumitru spune că îl strânge în piept și nu poate respira "
                    "bine. Transferat către DAS."
                ),
            ),
        ),
        (
            "teodor",
            "domnule Teodor",
            ("Bine, mulțumesc, citesc mult.", "Bine, nepoata vine duminică."),
            (
                "vizita nepoatei",
                "A venit nepoata în vizită, domnule Teodor?",
                "nepoata vine duminică",
            ),
            ("mâna stângă și vorbitul", "nu-mi mai simt mâna stângă"),
            (
                "Domnul Teodor se descurcă singur și citește mult.",
                "Domnul Teodor se simte bine și așteaptă vizita nepoatei.",
                (
                    "Domnul Teodor nu își mai simte mâna stângă și vorbește greu. "
                    "Transferat către DAS."
                ),
            ),
        ),
        (
            "viorica",
            "doamna Viorica",
            ("Bine, am făcut prăjituri.", "Bine, doar mă cam agit seara."),
            (
                "agitația de seara",
                "Mai sunteți agitată seara, doamna Viorica?",
                "mă cam agit seara",
            ),
            ("inima bate tare", "inima îmi bate foarte tare"),
            (
                "Doamna Viorica se descurcă singură; a făcut prăjituri.",
                "Doamna Viorica se simte bine, dar seara se agită.",
                (
                    "Doamna Viorica spune că îi e rău, inima îi bate foarte tare și îi e "
                    "frică. Transferată către DAS."
                ),
            ),
        ),
        (
            "gavril",
            "domnule Gavril",
            (
                "Bine, fiica a trecut pe la mine.",
                "Bine, dar scările de afară sunt pline de frunze ude.",
            ),
            (
                "scările de afară",
                "Mai sunt frunze ude pe scări, domnule Gavril?",
                "scările de afară sunt pline de frunze ude",
            ),
            ("șoldul", "mă doare tare șoldul"),
            (
                "Domnul Gavril se descurcă singur; fiica trece pe la el.",
                (
                    "Domnul Gavril se simte bine, dar scările de afară sunt alunecoase de "
                    "la frunzele ude."
                ),
                (
                    "Domnul Gavril a alunecat pe scări și îl doare tare șoldul. "
                    "Transferat către DAS."
                ),
            ),
        ),
        (
            "margareta",
            "doamna Margareta",
            (
                "Bine, mulțumesc de întrebare.",
                "Bine, dar nu prea am poftă de mâncare.",
            ),
            (
                "pofta de mâncare",
                "Ați mai mâncat ceva bun, doamna Margareta?",
                "nu prea am poftă de mâncare",
            ),
            ("slăbiciunea", "mă simt foarte slăbită"),
            (
                "Doamna Margareta se descurcă singură.",
                "Doamna Margareta se simte bine, dar nu prea are poftă de mâncare.",
                (
                    "Doamna Margareta a amețit, se simte foarte slăbită și nu se poate "
                    "ridica din fotoliu. Transferată către DAS."
                ),
            ),
        ),
    )
    for senior, address, (said1, said2), raised, (topic, quote), stories in quiet:
        q1, q2 = earlier(h, senior, (10, ("ok", said1), warm), (5, ("ok", said2), warm))
        alarm = named_call(h, senior, "alarm")
        noted = ask(raised[0], raised[1], q2, raised[2])
        now = ask(topic, f"Cum vă simțiți acum, {address}?", alarm, quote)
        for call, follow_ups, narrative in (
            (q1, [], stories[0]),
            (q2, [noted], stories[1]),
            (alarm, [now, noted], stories[2]),
        ):
            h.summarize(
                senior,
                call,
                follow_ups=follow_ups,
                how_to_talk=[plain],
                trends=[],
                narrative=narrative,
            )


def decline(h: History) -> None:
    """Eugenia Tudor: six answered wellbeing calls over three weeks (design §6). The
    wrong day in two of the last three, going out less, and a broken heater at the end."""
    h.welcome("eugenia", 29)
    days = (21, 17, 13, 9, 6, 3)
    ok = ("yes", "Da, am căldură.")

    def right(m: float) -> tuple[str, str]:
        named = h.day(m * 24 * 60)
        return named, f"{named.capitalize()}."

    slips: list[str] = []  # what she said on each wrong day, as cited

    def wrong(m: float) -> tuple[str, str]:
        named = DAY_NAMES[(DAY_NAMES.index(h.day(m * 24 * 60)) + 1) % 7]
        slips.append(f"Cred că e {named}")
        return named, f"{slips[-1]}, nu?"

    plan = (
        (("ok", "Bine, mulțumesc, mă descurc."), right, ok),
        (("ok", "Bine, doar mă doare puțin spatele."), right, ok),
        (("ok", "Bine, dar am dormit prost."), right, ok),
        (("ok", "Bine, dar nu prea mai ies din casă."), wrong, ok),
        (("ok", "Bine, mulțumesc."), right, ok),
        (
            ("ok", "Mai merge, nu prea mai ies din casă."),
            wrong,
            ("no", "Nu merge caloriferul de câteva zile."),
        ),
    )
    calls: list[Call] = []
    for i, (feeling, day, shelter) in enumerate(plan):
        # 03 §3: a wrong day or no heat on a cold campaign is yellow.
        worrying = [
            q
            for q, bad in (
                (Question.orientation, day is wrong),
                (Question.shelter, shelter[0] == "no"),
            )
            if bad
        ]
        calls.append(
            h.cold_call(
                "eugenia",
                f"campaign-{i + 1}",
                days[i] * 24 * 60,
                previous=None,
                feeling=feeling,
                day=day(days[i]),
                shelter=shelter,
                final=Severity.yellow if worrying else Severity.green,
                reason=campaign_reason(worrying, CampaignKind.cold),
                summary=f"Doamna Eugenia: {feeling[1]} {shelter[1]}",
            )
        )
    h.status("eugenia", calls[-1])
    _, c2, c3, c4, _, c6 = (c.id for c in calls)
    back = FollowUp(
        topic="durerea de spate",
        question="Cum vă mai simțiți spatele, doamna Eugenia?",
        call_id=c2,
        quote="doar mă doare puțin spatele",
    )
    out = FollowUp(
        topic="nu prea mai iese din casă",
        question="Ați mai ieșit puțin la aer în zilele astea, doamna Eugenia?",
        call_id=c4,
        quote="nu prea mai ies din casă",
    )
    heater = FollowUp(
        topic="caloriferul nu merge",
        question="Data trecută mi-ați spus că nu merge caloriferul. S-a rezolvat?",
        call_id=c6,
        quote="nu merge caloriferul",
    )
    h.summarize(
        "eugenia",
        calls[0],
        follow_ups=[],
        how_to_talk=["Vorbește clar și răspunde scurt."],
        trends=[],
        narrative="Doamna Eugenia răspunde ușor și se descurcă singură. Nicio "
        "problemă la primul apel.",
    )
    h.summarize(
        "eugenia",
        calls[1],
        follow_ups=[back],
        how_to_talk=["Vorbește clar și răspunde scurt."],
        trends=[],
        narrative="Doamna Eugenia se descurcă singură, dar a amintit o durere ușoară "
        "de spate.",
    )
    h.summarize(
        "eugenia",
        calls[2],
        follow_ups=[
            back,
            FollowUp(
                topic="somnul",
                question="Ați dormit mai bine în ultimele nopți?",
                call_id=c3,
                quote="am dormit prost",
            ),
        ],
        how_to_talk=["Vorbește clar și răspunde scurt."],
        trends=[],
        narrative="Doamna Eugenia se descurcă singură. A amintit o durere de spate "
        "și un somn prost.",
    )
    h.summarize(
        "eugenia",
        calls[3],
        follow_ups=[out],
        how_to_talk=["Vorbiți rar și lăsați-o să răspundă fără grabă."],
        trends=[],
        narrative="Doamna Eugenia spune că nu prea mai iese din casă și a încurcat "
        "ziua săptămânii o dată.",
    )
    h.summarize(
        "eugenia",
        calls[4],
        follow_ups=[out],
        how_to_talk=["Vorbiți rar și lăsați-o să răspundă fără grabă."],
        trends=[],
        narrative="Doamna Eugenia a spus corect ziua și se simte bine, dar nu a "
        "ieșit din casă în ultima vreme.",
    )
    h.summarize(
        "eugenia",
        calls[5],
        follow_ups=[heater, out],
        how_to_talk=["Vorbiți rar și lăsați-o să răspundă fără grabă."],
        trends=[
            Trend(
                note="A încurcat ziua săptămânii în două dintre ultimele trei apeluri.",
                direction="worse",
                evidence=[
                    Citation(call_id=c4, quote=slips[0]),
                    Citation(call_id=c6, quote=slips[1]),
                ],
            )
        ],
        narrative="Doamna Eugenia nu prea mai iese din casă și a încurcat ziua în două "
        "din ultimele trei apeluri. Spune că nu merge caloriferul de câteva zile.",
    )


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
        await sync_senior_grant(
            session,
            senior.id,
            senior.phone_e164,
            senior.full_name[:120],
            landline=senior.phone_is_landline,
            granted_by=senior.medic_id,
        )
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
    await session.merge(history.past_campaign)
    await session.merge(history.campaign)
    await session.flush()
    session.add_all(history.calls)  # in order, so a redial follows its first attempt
    await session.flush()
    session.add_all(history.rows)
    await session.flush()
    session.add_all(history.summaries)  # in order, each after the one it follows
    await session.flush()


async def remove(session: AsyncSession) -> None:
    """The seed's seniors and everything about them, including what was added through
    the API since; their caregiver and senior grants go with them (ON DELETE CASCADE).
    Users, staff grants and the campaign stay."""
    seniors = select(Senior.id).where(SEEDED)
    calls = select(Call.id).where(Call.senior_id.in_(seniors))
    await session.execute(
        delete(SummaryVersion).where(SummaryVersion.senior_id.in_(seniors))
    )
    for table in (CallTurn, Answer, StatusReport):
        await session.execute(delete(table).where(table.call_id.in_(calls)))
    for table in (Incident, SeniorStatus, WatchState, WatchReading, Consent, Event):
        await session.execute(delete(table).where(table.senior_id.in_(seniors)))
    await session.execute(delete(Call).where(Call.senior_id.in_(seniors)))
    await session.execute(delete(Senior).where(SEEDED))


async def seed(
    reset: bool = False, now: datetime | None = None, confirm: str | None = None
) -> str:
    """Returns seeded, reseeded, or already seeded. A cloud database only from inside its
    Railway deployment with `confirm` naming it, as seed_cast.py; never production."""
    settings = get_settings()
    check_target(confirm)
    if settings.app_env == "production":
        raise SystemExit("Refusing to seed production: mock data never goes there.")
    cloud = not is_local_db(settings.database_url)
    if cloud and "*" in settings.dial_allowlist.split(","):
        # The seeded numbers are made up, in a premium-rate range (staging design §2).
        raise SystemExit(
            "Refusing to seed: DIAL_ALLOWLIST is *, so a campaign would ring the "
            "seeded numbers. Set it to the team's numbers first."
        )
    async with Session() as session:
        there = await session.scalar(select(Senior.id).where(SEEDED).limit(1))
        if there and not reset:
            return "already seeded"
        if there:
            await remove(session)
        history = build(
            now or datetime.now(UTC), await add_people(session), cloud=cloud
        )
        await save(session, history)
        await session.commit()
    return "reseeded" if there else "seeded"


def main() -> int:
    parser = argparse.ArgumentParser(description="Mock data, locally or on staging.")
    parser.add_argument("--reset", action="store_true", help="replace it, fresh times")
    parser.add_argument("--confirm", help="the APP_ENV of the cloud database seeded")
    args = parser.parse_args()
    result = asyncio.run(seed(args.reset, confirm=args.confirm))
    print(result)
    if result == "already seeded":
        print("Run with --reset to replace it with fresh times.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
