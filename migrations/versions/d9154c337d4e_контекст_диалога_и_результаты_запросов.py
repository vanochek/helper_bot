"""Контекст диалога и результаты запросов

Ревизия: d9154c337d4e
Предыдущая ревизия: af3916257c20
Дата создания: 2026-10-28 21:01:25.140480

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Идентификаторы ревизии Alembic.
revision: str = "d9154c337d4e"
down_revision: Union[str, Sequence[str], None] = "af3916257c20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Применить изменения схемы."""
    op.create_table(
        "chat_messages",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.String(length=2000), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["browser_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", "request_id"),
    )
    op.add_column(
        "browser_sessions",
        sa.Column("draft", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Откатить изменения схемы."""
    op.drop_column("browser_sessions", "draft")
    op.drop_table("chat_messages")
