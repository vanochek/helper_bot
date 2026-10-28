"""Начальная схема сессий и записей

Ревизия: 51757401ccab
Предыдущая ревизия:
Дата создания: 2026-10-28 20:48:05.237880

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Идентификаторы ревизии Alembic.
revision: str = "51757401ccab"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Применить изменения схемы."""
    op.create_table(
        "browser_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("details", sa.String(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_on", sa.Date(), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ends_at IS NULL OR (kind = 'meeting' AND scheduled_at IS NOT NULL "
            "AND ends_at > scheduled_at)",
            name="ck_entries_end",
        ),
        sa.CheckConstraint(
            "kind = 'task' OR scheduled_at IS NOT NULL", name="ck_entries_required_time"
        ),
        sa.CheckConstraint("kind IN ('task','reminder','meeting')", name="ck_entries_kind"),
        sa.CheckConstraint("status IN ('open','done','cancelled')", name="ck_entries_status"),
        sa.CheckConstraint(
            "details IS NULL OR length(details) <= 10000", name="ck_entries_details"
        ),
        sa.CheckConstraint("length(trim(title)) BETWEEN 1 AND 500", name="ck_entries_title"),
        sa.CheckConstraint(
            "scheduled_at IS NULL OR scheduled_on IS NULL", name="ck_entries_schedule"
        ),
        sa.ForeignKeyConstraint(["session_id"], ["browser_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_entries_owner_created", "entries", ["session_id", "created_at"], unique=False
    )
    op.create_index(
        "ix_entries_owner_date", "entries", ["session_id", "scheduled_on"], unique=False
    )
    op.create_index(
        "ix_entries_owner_time", "entries", ["session_id", "scheduled_at"], unique=False
    )


def downgrade() -> None:
    """Откатить изменения схемы."""
    op.drop_index("ix_entries_owner_time", table_name="entries")
    op.drop_index("ix_entries_owner_date", table_name="entries")
    op.drop_index("ix_entries_owner_created", table_name="entries")
    op.drop_table("entries")
    op.drop_table("browser_sessions")
