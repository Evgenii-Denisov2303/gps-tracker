"""Separate hardware identity and durable FLEX telemetry; unknown GPS accuracy."""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('devices') as batch:
        batch.add_column(sa.Column('kind', sa.String(20), nullable=False, server_default='android'))
        batch.add_column(sa.Column('imei', sa.String(15), nullable=True))
        batch.create_unique_constraint('uq_devices_imei', ['imei'])
    with op.batch_alter_table('location_points') as batch:
        batch.alter_column('accuracy', existing_type=sa.Float(), nullable=True)
    op.create_table('hardware_records',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('device_id', sa.Integer(), sa.ForeignKey('devices.id'), nullable=False),
        sa.Column('record_hash', sa.String(64), nullable=False),
        sa.Column('event_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fields', sa.JSON(), nullable=False),
        sa.Column('rejection', sa.String(50), nullable=True),
        sa.UniqueConstraint('device_id', 'record_hash', name='uq_hardware_record'))


def downgrade():
    # Do not invent accuracy or destroy hardware history to make rollback pass.
    count = op.get_bind().execute(sa.text('SELECT count(*) FROM location_points WHERE accuracy IS NULL')).scalar()
    if count:
        raise RuntimeError('Export hardware points and restore the pre-upgrade backup before downgrade')
    op.drop_table('hardware_records')
    with op.batch_alter_table('location_points') as batch:
        batch.alter_column('accuracy', existing_type=sa.Float(), nullable=False)
    with op.batch_alter_table('devices') as batch:
        batch.drop_constraint('uq_devices_imei', type_='unique')
        batch.drop_column('imei')
        batch.drop_column('kind')
