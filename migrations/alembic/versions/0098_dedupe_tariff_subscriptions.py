"""dedupe multi-tariff subscriptions — superseded by a startup service (no-op)

The duplicate-subscription cleanup originally lived here as a SQL DELETE, but a
DB-only delete would orphan the Remnawave panel users behind those rows: a normal
subscription deletion removes the panel user too (see ``my_subscriptions`` ->
``delete_remnawave_user``). Deleting panel users needs the async panel API, which
a synchronous migration can't drive, so the cleanup moved to
``app.services.subscription_dedup_service.dedupe_expired_tariff_subscriptions`` —
run in the background on startup, removing the DB row and the panel user together.

This migration is intentionally a no-op, kept only to preserve the revision chain.

Revision ID: 0098
Revises: 0097
Create Date: 2026-06-02

Note (GhostVPN fork): upstream shipped this as revision 0088, but the fork's
chain already occupies 0088..0097 (custom payment-gateway tables). Re-chained
to 0098 after 0097 during the upstream merge. Safe because the body is a no-op.
"""

from typing import Sequence, Union

revision: str = '0098'
down_revision: Union[str, None] = '0097'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No-op — duplicate cleanup runs in the startup dedup service so that the
    # Remnawave panel users are removed alongside the DB rows (no orphans).
    pass


def downgrade() -> None:
    pass
