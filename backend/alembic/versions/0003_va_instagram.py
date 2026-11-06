"""Replace the VA email with a private Instagram link.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def _refuse_if_any_va(reason: str) -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM va_profiles)")):
        raise RuntimeError(f"Migration 0003 stopped, va_profiles contains rows: {reason}")


def upgrade() -> None:
    _refuse_if_any_va("an Instagram link cannot be derived from an email.")
    op.drop_column('va_profiles', 'email')
    op.add_column('va_profiles', sa.Column('instagram_url', sa.Text(), nullable=False))
    op.create_check_constraint(
        op.f('ck_va_profiles_instagram_length'), 'va_profiles', 'char_length(instagram_url) <= 2048'
    )


def downgrade() -> None:
    _refuse_if_any_va("an email cannot be derived from an Instagram link.")
    op.drop_constraint(op.f('ck_va_profiles_instagram_length'), 'va_profiles', type_='check')
    op.drop_column('va_profiles', 'instagram_url')
    op.add_column('va_profiles', sa.Column('email', sa.String(length=254), nullable=False))
