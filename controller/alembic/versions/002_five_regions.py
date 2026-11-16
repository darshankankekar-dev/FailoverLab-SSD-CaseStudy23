"""add five regions support

Revision ID: 002_five_regions
Revises: 001_initial
Create Date: 2026-11-16 22:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column

revision: str = '002_five_regions'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Reference regions table
regions_table = table(
    'regions',
    column('id', sa.String),
    column('name', sa.String),
    column('cloud_zone', sa.String),
    column('role', sa.String),
    column('health', sa.String),
    column('status', sa.String),
    column('accepts_writes', sa.Boolean),
    column('ingress_traffic_percent', sa.Integer),
    column('ingress_rps', sa.Integer),
    column('app_servers_healthy', sa.Integer),
    column('app_servers_total', sa.Integer),
    column('active_connections', sa.Integer),
    column('iops', sa.Integer),
    column('fencing_epoch', sa.BigInteger),
    column('is_fenced', sa.Boolean),
)


def upgrade() -> None:
    # Insert new regions: Frankfurt (region-c), Virginia (region-d), São Paulo (region-e)
    op.bulk_insert(
        regions_table,
        [
            {
                'id': 'region-c',
                'name': 'Frankfurt',
                'cloud_zone': 'eu-central-1',
                'role': 'STANDBY',
                'health': 'HEALTHY',
                'status': 'healthy',
                'accepts_writes': False,
                'ingress_traffic_percent': 0,
                'ingress_rps': 0,
                'app_servers_healthy': 12,
                'app_servers_total': 12,
                'active_connections': 0,
                'iops': 110,
                'fencing_epoch': 101,
                'is_fenced': False,
            },
            {
                'id': 'region-d',
                'name': 'Virginia',
                'cloud_zone': 'us-east-1',
                'role': 'STANDBY',
                'health': 'HEALTHY',
                'status': 'healthy',
                'accepts_writes': False,
                'ingress_traffic_percent': 0,
                'ingress_rps': 0,
                'app_servers_healthy': 12,
                'app_servers_total': 12,
                'active_connections': 0,
                'iops': 115,
                'fencing_epoch': 101,
                'is_fenced': False,
            },
            {
                'id': 'region-e',
                'name': 'São Paulo',
                'cloud_zone': 'sa-east-1',
                'role': 'STANDBY',
                'health': 'HEALTHY',
                'status': 'healthy',
                'accepts_writes': False,
                'ingress_traffic_percent': 0,
                'ingress_rps': 0,
                'app_servers_healthy': 12,
                'app_servers_total': 12,
                'active_connections': 0,
                'iops': 95,
                'fencing_epoch': 101,
                'is_fenced': False,
            },
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM regions WHERE id IN ('region-c', 'region-d', 'region-e')")
