"""Add read-only website accounts; existing owners keep full access."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("admins", sa.Column("read_only", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("admins", "read_only")
