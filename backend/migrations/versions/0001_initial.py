"""Initial schema, deliberately frozen independently of application models."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("admins", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("username", sa.String(100), nullable=False, unique=True),
                    sa.Column("password_hash", sa.String(255), nullable=False))
    op.create_table("admin_sessions", sa.Column("token_hash", sa.String(64), primary_key=True),
                    sa.Column("admin_id", sa.Integer(), sa.ForeignKey("admins.id", ondelete="CASCADE"), nullable=False),
                    sa.Column("csrf_token", sa.String(64), nullable=False),
                    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_admin_sessions_expires_at", "admin_sessions", ["expires_at"])
    op.create_table("login_limits", sa.Column("key", sa.String(64), primary_key=True),
                    sa.Column("count", sa.Integer(), nullable=False),
                    sa.Column("reset_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("vehicles", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("name", sa.String(100), nullable=False), sa.Column("plate", sa.String(30), nullable=False),
                    sa.Column("description", sa.String(500), nullable=False), sa.Column("active", sa.Boolean(), nullable=False))
    op.create_table("devices", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False),
                    sa.Column("name", sa.String(100), nullable=False),
                    sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
                    sa.Column("active", sa.Boolean(), nullable=False),
                    sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_devices_vehicle_id", "devices", ["vehicle_id"])
    op.create_table("location_points", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("event_id", sa.String(36), nullable=False),
                    sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False),
                    sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id"), nullable=False),
                    sa.Column("latitude", sa.Float(), nullable=False), sa.Column("longitude", sa.Float(), nullable=False),
                    sa.Column("speed", sa.Float(), nullable=True), sa.Column("accuracy", sa.Float(), nullable=False),
                    sa.Column("heading", sa.Float(), nullable=True), sa.Column("battery_level", sa.Integer(), nullable=True),
                    sa.Column("charging", sa.Boolean(), nullable=True),
                    sa.Column("gps_timestamp", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
                    sa.UniqueConstraint("device_id", "event_id", name="uq_device_event"))
    op.create_index("ix_vehicle_gps", "location_points", ["vehicle_id", "gps_timestamp"])


def downgrade():
    for table in ("location_points", "devices", "vehicles", "login_limits", "admin_sessions", "admins"):
        op.drop_table(table)
