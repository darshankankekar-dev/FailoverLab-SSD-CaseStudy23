"""initial schema

Revision ID: 001_initial
Revises: 
Create Date: 2026-10-31 22:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Regions
    op.create_table(
        'regions',
        sa.Column('id', sa.String(length=32), primary_key=True),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('cloud_zone', sa.String(length=64), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('health', sa.String(length=16), nullable=False, server_default='HEALTHY'),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='healthy'),
        sa.Column('accepts_writes', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('ingress_traffic_percent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ingress_rps', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('app_servers_healthy', sa.Integer(), nullable=False, server_default='12'),
        sa.Column('app_servers_total', sa.Integer(), nullable=False, server_default='12'),
        sa.Column('active_connections', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('iops', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('fencing_epoch', sa.BigInteger(), nullable=False, server_default='101'),
        sa.Column('is_fenced', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # 2. Policies
    op.create_table(
        'policies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('health_check_interval_sec', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('failure_threshold_consecutive', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('quorum_size', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('majority_required', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('acceptable_replication_lag_sec', sa.Float(), nullable=False, server_default='5.0'),
        sa.Column('fencing_duration_sec', sa.Float(), nullable=False, server_default='2.0'),
        sa.Column('route_propagation_sec', sa.Float(), nullable=False, server_default='2.0'),
        sa.Column('route_verification_sec', sa.Float(), nullable=False, server_default='2.0'),
        sa.Column('auto_failover_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # 3. Controller State
    op.create_table(
        'controller_state',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('current_state', sa.String(length=32), nullable=False, server_default='HEALTHY'),
        sa.Column('active_region', sa.String(length=32), nullable=False, server_default='region-a'),
        sa.Column('fencing_epoch', sa.BigInteger(), nullable=False, server_default='101'),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_health_check_sim_time', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('simulated_time_seconds', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('blocked_reason', sa.Text(), nullable=True),
        sa.Column('blocked_at_state', sa.String(length=32), nullable=True),
        sa.Column('is_sequence_in_progress', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('route_retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('persisted_intent', sa.String(length=64), nullable=True),
        sa.Column('is_paused_interrupted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # 4. Replication State
    op.create_table(
        'replication_state',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='STREAMING'),
        sa.Column('lag_seconds', sa.Float(), nullable=False, server_default='0.8'),
        sa.Column('lag_ms', sa.Integer(), nullable=False, server_default='800'),
        sa.Column('bandwidth_mbps', sa.Integer(), nullable=False, server_default='450'),
        sa.Column('packet_loss_percent', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('pending_bytes', sa.Integer(), nullable=False, server_default='12400'),
        sa.Column('bytes_transferred', sa.BigInteger(), nullable=False, server_default='45000000'),
        sa.Column('mode', sa.String(length=32), nullable=False, server_default='ASYNCHRONOUS_RECORD'),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # 5. Route State
    op.create_table(
        'route_state',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('active_target', sa.String(length=32), nullable=False, server_default='region-a'),
        sa.Column('dns_ttl_seconds', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('propagation_percent', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('verification_status', sa.String(length=32), nullable=False, server_default='VERIFIED'),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # 6. Quorum Voters
    op.create_table(
        'quorum_voters',
        sa.Column('id', sa.String(length=32), primary_key=True),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('location', sa.String(length=128), nullable=False),
        sa.Column('vote', sa.String(length=32), nullable=False, server_default='PRIMARY_HEALTHY'),
        sa.Column('latency_ms', sa.Integer(), nullable=False, server_default='25'),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # 7. Audit Events
    op.create_table(
        'audit_events',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('simulated_time_seconds', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('wall_clock_timestamp', sa.String(length=64), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('subsystem', sa.String(length=32), nullable=False),
        sa.Column('transition', sa.String(length=128), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # 8. Transition Intents
    op.create_table(
        'transition_intents',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('transition_name', sa.String(length=64), nullable=False),
        sa.Column('source_state', sa.String(length=32), nullable=False),
        sa.Column('target_state', sa.String(length=32), nullable=False),
        sa.Column('target_region', sa.String(length=32), nullable=False),
        sa.Column('fencing_epoch', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='IN_PROGRESS'),
        sa.Column('blocked_reason', sa.Text(), nullable=True),
        sa.Column('step_details', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('transition_intents')
    op.drop_table('audit_events')
    op.drop_table('quorum_voters')
    op.drop_table('route_state')
    op.drop_table('replication_state')
    op.drop_table('controller_state')
    op.drop_table('policies')
    op.drop_table('regions')

