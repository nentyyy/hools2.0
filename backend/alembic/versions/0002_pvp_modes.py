"""Separate wheel and ice rounds

Revision ID: 0002_pvp_modes
Revises: 0001_initial
Create Date: 2026-08-20 07:55:05.879454
"""

from alembic import op
import sqlalchemy as sa


revision = '0002_pvp_modes'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing rounds were all wheel rounds, which the server default covers.
    op.add_column('pvp_games', sa.Column('mode', sa.String(length=16), server_default='wheel', nullable=False))
    op.create_index('ix_pvp_games_mode_status', 'pvp_games', ['mode', 'status', 'created_at'], unique=False)
    op.create_check_constraint(op.f('ck_pvp_games_mode_valid'), 'pvp_games', "mode IN ('wheel', 'ice')")


def downgrade() -> None:
    op.drop_constraint(op.f('ck_pvp_games_mode_valid'), 'pvp_games', type_='check')
    op.drop_index('ix_pvp_games_mode_status', table_name='pvp_games')
    op.drop_column('pvp_games', 'mode')
