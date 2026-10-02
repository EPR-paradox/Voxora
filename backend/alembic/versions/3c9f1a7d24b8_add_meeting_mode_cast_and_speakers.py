"""add meeting-mode cast and message speakers

Revision ID: 3c9f1a7d24b8
Revises: 5d07a878bd32
Create Date: 2026-10-02 18:05:00.000000

Meeting mode (docs/meeting-mode-v0.1.md §2, §3) lets several AI participants speak inside one turn.
That needs three things:

- ``scenarios.cast``: the participants array. Nullable, so existing scenarios keep working as
  single-character scenario.
- ``messages.speaker_key``: who said it. Empty string for the learner — not NULL, because PostgreSQL
  treats NULLs as distinct and the per-turn uniqueness rule would stop protecting learner turns.
- ``messages.seq``: display order inside a session. ``created_at`` cannot do this job: ``now()`` is
  constant inside a transaction, so all rows one turn writes share a timestamp and ordering by it is
  unstable.

The per-turn unique constraint widens from (session, turn, role) to (session, turn, role, speaker).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "3c9f1a7d24b8"
down_revision: str | Sequence[str] | None = "5d07a878bd32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Backfill order for existing history: by turn, the learner before the AI, then creation time and id
# as tie-breakers. The sort key is 0 for the learner, so the learner's line comes first in a turn.
_BACKFILL_SEQ = """
WITH ordered AS (
    SELECT id,
           row_number() OVER (
               PARTITION BY session_id
               ORDER BY turn_index ASC,
                        CASE WHEN role = 'assistant' THEN 1 ELSE 0 END ASC,
                        created_at ASC,
                        id ASC
           ) AS position
    FROM messages
)
UPDATE messages
SET seq = ordered.position
FROM ordered
WHERE messages.id = ordered.id
"""


def upgrade() -> None:
    op.add_column(
        "scenarios",
        sa.Column("cast", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # Nullable first, backfilled, then tightened: existing rows get a real order, not a default.
    op.add_column("messages", sa.Column("seq", sa.Integer(), nullable=True))
    op.execute(_BACKFILL_SEQ)
    op.alter_column("messages", "seq", nullable=False)

    op.add_column(
        "messages",
        sa.Column("speaker_key", sa.String(length=32), nullable=False, server_default=""),
    )
    op.create_check_constraint("ck_messages_seq", "messages", "seq > 0")

    op.drop_constraint("uq_messages_turn_role", "messages", type_="unique")
    op.create_unique_constraint(
        "uq_messages_turn_speaker",
        "messages",
        ["session_id", "turn_index", "role", "speaker_key"],
    )


def downgrade() -> None:
    """Only valid while no multi-participant turn has been written.

    Restoring ``uq_messages_turn_role`` fails loudly if a turn holds two assistant rows, which is
    intended behaviour: dropping those rows to make the downgrade "succeed" would silently delete
    meeting history.
    """
    op.drop_constraint("uq_messages_turn_speaker", "messages", type_="unique")
    op.create_unique_constraint(
        "uq_messages_turn_role", "messages", ["session_id", "turn_index", "role"]
    )
    op.drop_constraint("ck_messages_seq", "messages", type_="check")
    op.drop_column("messages", "speaker_key")
    op.drop_column("messages", "seq")
    op.drop_column("scenarios", "cast")
