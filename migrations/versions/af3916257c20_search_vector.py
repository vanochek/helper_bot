"""Вычисляемый столбец поиска для воспроизводимого сравнения схемы."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TSVECTOR

revision = "af3916257c20"
down_revision = "8b4bfe903a21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_entries_search_ru", table_name="entries")
    op.add_column(
        "entries",
        sa.Column(
            "search_vector",
            TSVECTOR,
            sa.Computed(
                "to_tsvector('russian', title || ' ' || coalesce(details, ''))", persisted=True
            ),
            nullable=False,
        ),
    )
    op.create_index("ix_entries_search_ru", "entries", ["search_vector"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_entries_search_ru", table_name="entries")
    op.drop_column("entries", "search_vector")
    op.create_index(
        "ix_entries_search_ru",
        "entries",
        [sa.text("to_tsvector('russian', title || ' ' || coalesce(details, ''))")],
        postgresql_using="gin",
    )
