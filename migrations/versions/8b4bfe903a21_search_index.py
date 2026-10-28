"""Индекс поиска по русским словоформам."""

import sqlalchemy as sa
from alembic import op

revision = "8b4bfe903a21"
down_revision = "51757401ccab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_entries_search_ru",
        "entries",
        [sa.text("to_tsvector('russian', title || ' ' || coalesce(details, ''))")],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_entries_search_ru", table_name="entries")
