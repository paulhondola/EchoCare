"""create tables

Every other table in the data model (05 §1) with the constraints the database enforces
(05 §3), on top of the auth layer's users and grants: users gets on_duty (P10), grants
gets its senior foreign key (AL6) and the one-senior-grant index (AL7).

Revision ID: 741f75a7dbe1
Revises: 5d0c8c3a7f21
Create Date: 2026-10-10 20:38:47.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "741f75a7dbe1"
down_revision: str | Sequence[str] | None = "5d0c8c3a7f21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column(
            "on_duty", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.create_index(
        "uq_users_on_duty",
        "users",
        ["on_duty"],
        unique=True,
        postgresql_where=sa.text("on_duty"),
    )
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("heat", "cold", name="campaignkind", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column(
            "level",
            sa.Enum("yellow", "red", name="warninglevel", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("started_by", sa.Uuid(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("warning_until", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["started_by"], ["users.id"], name=op.f("fk_campaigns_started_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campaigns")),
    )
    op.create_table(
        "push_tokens",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token", sa.String(length=512), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_push_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_tokens")),
        sa.UniqueConstraint("token", name=op.f("uq_push_tokens_token")),
    )
    op.create_index(
        op.f("ix_push_tokens_user_id"), "push_tokens", ["user_id"], unique=False
    )
    op.create_table(
        "seniors",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("medic_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("form_of_address", sa.String(length=120), nullable=False),
        sa.Column("phone_e164", sa.String(length=16), nullable=False),
        sa.Column("phone_is_landline", sa.Boolean(), nullable=False),
        sa.Column("street", sa.String(length=200), nullable=True),
        sa.Column("street_number", sa.String(length=20), nullable=True),
        sa.Column("block", sa.String(length=20), nullable=True),
        sa.Column("staircase", sa.String(length=20), nullable=True),
        sa.Column("floor", sa.String(length=20), nullable=True),
        sa.Column("apartment", sa.String(length=20), nullable=True),
        sa.Column("intercom_code", sa.String(length=40), nullable=True),
        sa.Column("key_holder", sa.String(length=200), nullable=True),
        sa.Column("landmark", sa.String(length=200), nullable=True),
        sa.Column("call_window", sa.String(length=60), nullable=True),
        sa.Column(
            "enrollment_state",
            sa.Enum(
                "draft",
                "submitted",
                "accepted",
                "active",
                "refused",
                "wrong_number",
                "unreachable",
                name="enrollmentstate",
                native_enum=False,
                length=32,
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["medic_id"], ["users.id"], name=op.f("fk_seniors_medic_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_seniors")),
    )
    op.create_index(op.f("ix_seniors_medic_id"), "seniors", ["medic_id"], unique=False)
    op.create_table(
        "calls",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("senior_id", sa.Uuid(), nullable=False),
        sa.Column(
            "trigger",
            sa.Enum(
                "campaign",
                "watch",
                "manual",
                "welcome",
                name="calltrigger",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("previous_call_id", sa.Uuid(), nullable=True),
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "starting_severity",
            sa.Enum(
                "green", "yellow", "red", name="severity", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.Enum(
                "queued",
                "ringing",
                "in_progress",
                "unanswered",
                "failed",
                "completed",
                "handed_over",
                "dropped",
                name="callstate",
                native_enum=False,
                length=32,
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("twilio_call_id", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "final_severity",
            sa.Enum(
                "green", "yellow", "red", name="severity", native_enum=False, length=32
            ),
            nullable=True,
        ),
        sa.Column(
            "final_certainty",
            sa.Enum(
                "low", "medium", "high", name="certainty", native_enum=False, length=32
            ),
            nullable=True,
        ),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "welcome_outcome",
            sa.Enum(
                "confirmed",
                "not_available",
                "wrong_number",
                "no_answer",
                name="welcomeoutcome",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("handover_answered", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            name=op.f("fk_calls_campaign_id_campaigns"),
        ),
        sa.ForeignKeyConstraint(
            ["previous_call_id"],
            ["calls.id"],
            name=op.f("fk_calls_previous_call_id_calls"),
        ),
        sa.ForeignKeyConstraint(
            ["senior_id"], ["seniors.id"], name=op.f("fk_calls_senior_id_seniors")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calls")),
        sa.UniqueConstraint("twilio_call_id", name=op.f("uq_calls_twilio_call_id")),
    )
    op.create_index(
        op.f("ix_calls_campaign_id"), "calls", ["campaign_id"], unique=False
    )
    op.create_index(
        "ix_calls_queued_due_at",
        "calls",
        ["due_at"],
        unique=False,
        postgresql_where=sa.text("state IN ('queued')"),
    )
    op.create_index(op.f("ix_calls_senior_id"), "calls", ["senior_id"], unique=False)
    op.create_index(
        "uq_calls_live_senior",
        "calls",
        ["senior_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('in_progress', 'queued', 'ringing')"),
    )
    op.create_foreign_key(
        op.f("fk_grants_senior_id_seniors"),
        "grants",
        "seniors",
        ["senior_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_grants_senior_id"), "grants", ["senior_id"], unique=False)
    op.create_index(
        "uq_grants_one_senior_per_user",
        "grants",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("role = 'senior'"),
    )
    op.create_table(
        "watch_states",
        sa.Column("senior_id", sa.Uuid(), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "ok",
                "not_worn",
                "offline",
                name="watchcondition",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("last_check_in_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("battery", sa.Integer(), nullable=True),
        sa.Column("worn", sa.Boolean(), nullable=True),
        sa.Column("last_pulse", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["senior_id"],
            ["seniors.id"],
            name=op.f("fk_watch_states_senior_id_seniors"),
        ),
        sa.PrimaryKeyConstraint("senior_id", name=op.f("pk_watch_states")),
    )
    op.create_table(
        "answers",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column(
            "field",
            sa.Enum(
                "feeling",
                "orientation",
                "shelter",
                name="question",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("value", sa.String(length=60), nullable=False),
        sa.Column("clear", sa.Boolean(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["call_id"], ["calls.id"], name=op.f("fk_answers_call_id_calls")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answers")),
    )
    op.create_index(op.f("ix_answers_call_id"), "answers", ["call_id"], unique=False)
    op.create_table(
        "call_turns",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "speaker",
            sa.Enum(
                "senior",
                "agent",
                "system",
                name="speaker",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "kind",
            sa.Enum("speech", "keys", name="turnkind", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["call_id"], ["calls.id"], name=op.f("fk_call_turns_call_id_calls")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_call_turns")),
        sa.UniqueConstraint("call_id", "position", name=op.f("uq_call_turns_call_id")),
    )
    op.create_table(
        "consents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("senior_id", sa.Uuid(), nullable=False),
        sa.Column(
            "decision",
            sa.Enum(
                "given",
                "refused",
                "withdrawn",
                name="consentdecision",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "method",
            sa.Enum(
                "call",
                "signature",
                "medic",
                name="consentmethod",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("text_version", sa.String(length=40), nullable=False),
        sa.Column("call_id", sa.Uuid(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "signature_strokes", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("recorded_by", sa.Uuid(), nullable=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["call_id"], ["calls.id"], name=op.f("fk_consents_call_id_calls")
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"], ["users.id"], name=op.f("fk_consents_recorded_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["senior_id"], ["seniors.id"], name=op.f("fk_consents_senior_id_seniors")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consents")),
    )
    op.create_index(
        op.f("ix_consents_senior_id"), "consents", ["senior_id"], unique=False
    )
    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("senior_id", sa.Uuid(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "high_pulse_at_rest",
                "inactivity",
                "sos_button",
                "manual_request",
                name="eventtype",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("location_accuracy_m", sa.Float(), nullable=True),
        sa.Column("located_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("call_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["call_id"], ["calls.id"], name=op.f("fk_events_call_id_calls")
        ),
        sa.ForeignKeyConstraint(
            ["senior_id"], ["seniors.id"], name=op.f("fk_events_senior_id_seniors")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index(op.f("ix_events_senior_id"), "events", ["senior_id"], unique=False)
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("senior_id", sa.Uuid(), nullable=False),
        sa.Column("opened_by_call_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "in_progress",
                "resolved",
                name="incidentstatus",
                native_enum=False,
                length=32,
            ),
            server_default="open",
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("taken_by", sa.Uuid(), nullable=True),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "outcome",
            sa.Enum(
                "senior_ok",
                "team_sent",
                "called_112",
                "not_reached",
                "false_alarm",
                name="incidentoutcome",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status != 'resolved' OR (resolved_by IS NOT NULL AND outcome IS NOT NULL)",
            name=op.f("ck_incidents_resolved_has_outcome"),
        ),
        sa.ForeignKeyConstraint(
            ["opened_by_call_id"],
            ["calls.id"],
            name=op.f("fk_incidents_opened_by_call_id_calls"),
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"], ["users.id"], name=op.f("fk_incidents_resolved_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["senior_id"], ["seniors.id"], name=op.f("fk_incidents_senior_id_seniors")
        ),
        sa.ForeignKeyConstraint(
            ["taken_by"], ["users.id"], name=op.f("fk_incidents_taken_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
    )
    op.create_index(
        op.f("ix_incidents_senior_id"), "incidents", ["senior_id"], unique=False
    )
    op.create_index(
        "uq_incidents_unresolved_senior",
        "incidents",
        ["senior_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('in_progress', 'open')"),
    )
    op.create_table(
        "senior_statuses",
        sa.Column("senior_id", sa.Uuid(), nullable=False),
        sa.Column(
            "code",
            sa.Enum(
                "green", "yellow", "red", name="severity", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_call_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["senior_id"],
            ["seniors.id"],
            name=op.f("fk_senior_statuses_senior_id_seniors"),
        ),
        sa.ForeignKeyConstraint(
            ["source_call_id"],
            ["calls.id"],
            name=op.f("fk_senior_statuses_source_call_id_calls"),
        ),
        sa.PrimaryKeyConstraint("senior_id", name=op.f("pk_senior_statuses")),
    )
    op.create_table(
        "status_reports",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "rules",
                "raise_concern",
                "alarm_tier1",
                "alarm_tier2",
                "request_human",
                "trigger",
                "unanswered",
                name="reportsource",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "green", "yellow", "red", name="severity", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column(
            "certainty",
            sa.Enum(
                "low", "medium", "high", name="certainty", native_enum=False, length=32
            ),
            nullable=True,
        ),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["call_id"], ["calls.id"], name=op.f("fk_status_reports_call_id_calls")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_status_reports")),
    )
    op.create_index(
        op.f("ix_status_reports_call_id"), "status_reports", ["call_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_status_reports_call_id"), table_name="status_reports")
    op.drop_table("status_reports")
    op.drop_table("senior_statuses")
    op.drop_index(op.f("ix_incidents_senior_id"), table_name="incidents")
    op.drop_index(
        "uq_incidents_unresolved_senior",
        table_name="incidents",
        postgresql_where=sa.text("status IN ('in_progress', 'open')"),
    )
    op.drop_table("incidents")
    op.drop_index(op.f("ix_events_senior_id"), table_name="events")
    op.drop_table("events")
    op.drop_index(op.f("ix_consents_senior_id"), table_name="consents")
    op.drop_table("consents")
    op.drop_table("call_turns")
    op.drop_index(op.f("ix_answers_call_id"), table_name="answers")
    op.drop_table("answers")
    op.drop_table("watch_states")
    op.drop_index(
        "uq_grants_one_senior_per_user",
        table_name="grants",
        postgresql_where=sa.text("role = 'senior'"),
    )
    op.drop_index(op.f("ix_grants_senior_id"), table_name="grants")
    op.drop_constraint(
        op.f("fk_grants_senior_id_seniors"), "grants", type_="foreignkey"
    )
    op.drop_index(op.f("ix_calls_campaign_id"), table_name="calls")
    op.drop_index(
        "ix_calls_queued_due_at",
        table_name="calls",
        postgresql_where=sa.text("state IN ('queued')"),
    )
    op.drop_index(op.f("ix_calls_senior_id"), table_name="calls")
    op.drop_index(
        "uq_calls_live_senior",
        table_name="calls",
        postgresql_where=sa.text("state IN ('in_progress', 'queued', 'ringing')"),
    )
    op.drop_table("calls")
    op.drop_index(op.f("ix_seniors_medic_id"), table_name="seniors")
    op.drop_table("seniors")
    op.drop_index(op.f("ix_push_tokens_user_id"), table_name="push_tokens")
    op.drop_table("push_tokens")
    op.drop_table("campaigns")
    op.drop_index(
        "uq_users_on_duty", table_name="users", postgresql_where=sa.text("on_duty")
    )
    op.drop_column("users", "on_duty")
