"""Add what is needed to count one click per person for each VA.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('click_events', sa.Column('visitor_hash', sa.CHAR(length=64), nullable=True))
    op.create_index('ix_click_events_va_ip', 'click_events', ['va_profile_id', 'ip_hash'])
    op.create_index('ix_click_events_va_visitor', 'click_events', ['va_profile_id', 'visitor_hash'])


def downgrade() -> None:
    op.drop_index('ix_click_events_va_visitor', table_name='click_events')
    op.drop_index('ix_click_events_va_ip', table_name='click_events')
    op.drop_column('click_events', 'visitor_hash')
