"""add traffic telemetry samples table

Revision ID: 003_traffic_telemetry
Revises: 002_five_regions
Create Date: 2026-11-19 01:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '003_traffic_telemetry'
down_revision: Union[str, None] = '002_five_regions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'traffic_samples',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('batch_id', sa.String(length=64), nullable=False),
        sa.Column('gateway_instance_id', sa.String(length=64), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('interval_seconds', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('client_ingress_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('client_egress_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('client_ingress_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('client_egress_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('upstream_ingress_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('upstream_egress_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('upstream_ingress_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('upstream_egress_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('request_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('request_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('status_2xx', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status_3xx', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status_4xx', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status_5xx', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rate_limited_429', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('latency_avg_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('latency_p50_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('latency_p95_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('latency_p99_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('regional_traffic_json', sa.JSON(), nullable=True),
        sa.Column('traffic_sources_json', sa.JSON(), nullable=True),
        sa.Column('dropped_telemetry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_traffic_samples_batch_id'), 'traffic_samples', ['batch_id'], unique=True)
    op.create_index(op.f('ix_traffic_samples_timestamp'), 'traffic_samples', ['timestamp'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_traffic_samples_timestamp'), table_name='traffic_samples')
    op.drop_index(op.f('ix_traffic_samples_batch_id'), table_name='traffic_samples')
    op.drop_table('traffic_samples')
