"""Store latest device heartbeat without adding synthetic GPS points."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("devices", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("devices", sa.Column("health", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("devices", "health")
    op.drop_column("devices", "heartbeat_at")
