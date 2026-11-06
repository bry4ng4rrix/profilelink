"""Move from self-registered owners to VA profiles managed by an administrator.

Tables are dropped and recreated rather than renamed: the guards below ensure they are empty.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def _refuse_if_any(table: str, reason: str) -> None:
    if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
        raise RuntimeError(f"Migration 0002 stopped, {table} contains rows: {reason}")


def upgrade() -> None:
    _refuse_if_any("users", "every existing account would become an administrator.")
    _refuse_if_any("profiles", "an age and an email cannot be invented for existing profiles.")
    op.create_table('va_profiles',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('username', sa.String(length=30), nullable=False),
    sa.Column('first_name', sa.String(length=100), nullable=False),
    sa.Column('last_name', sa.String(length=100), nullable=False),
    sa.Column('age', sa.SmallInteger(), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('photo_url', sa.Text(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("username ~ '^[a-z0-9][a-z0-9_-]{2,29}$'", name=op.f('ck_va_profiles_username_format')),
    sa.CheckConstraint('age BETWEEN 1 AND 120', name=op.f('ck_va_profiles_age_range')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_va_profiles')),
    sa.UniqueConstraint('username', name=op.f('uq_va_profiles_username'))
    )
    op.create_table('va_external_links',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('va_profile_id', sa.Uuid(), nullable=False),
    sa.Column('destination_url', sa.Text(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('char_length(destination_url) <= 2048', name=op.f('ck_va_external_links_destination_length')),
    sa.ForeignKeyConstraint(['va_profile_id'], ['va_profiles.id'], name=op.f('fk_va_external_links_va_profile_id_va_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_va_external_links')),
    sa.UniqueConstraint('va_profile_id', name=op.f('uq_va_external_links_va_profile_id'))
    )
    op.add_column('click_events', sa.Column('va_profile_id', sa.Uuid(), nullable=False))
    op.drop_index(op.f('ix_click_events_profile_time'), table_name='click_events')
    op.create_index('ix_click_events_profile_time', 'click_events', ['va_profile_id', sa.literal_column('clicked_at DESC')], unique=False)
    op.create_index('ix_click_events_time', 'click_events', [sa.literal_column('clicked_at DESC')], unique=False)
    op.drop_constraint(op.f('fk_click_events_profile_id_profiles'), 'click_events', type_='foreignkey')
    op.create_foreign_key(op.f('fk_click_events_va_profile_id_va_profiles'), 'click_events', 'va_profiles', ['va_profile_id'], ['id'], ondelete='CASCADE')
    op.drop_column('click_events', 'profile_id')
    op.add_column('profile_visits', sa.Column('va_profile_id', sa.Uuid(), nullable=False))
    op.drop_index(op.f('ix_profile_visits_profile_time'), table_name='profile_visits')
    op.create_index('ix_profile_visits_profile_time', 'profile_visits', ['va_profile_id', sa.literal_column('visited_at DESC')], unique=False)
    op.create_index('ix_profile_visits_time', 'profile_visits', [sa.literal_column('visited_at DESC')], unique=False)
    op.drop_constraint(op.f('fk_profile_visits_profile_id_profiles'), 'profile_visits', type_='foreignkey')
    op.create_foreign_key(op.f('fk_profile_visits_va_profile_id_va_profiles'), 'profile_visits', 'va_profiles', ['va_profile_id'], ['id'], ondelete='CASCADE')
    op.drop_column('profile_visits', 'profile_id')
    op.drop_table('external_links')
    op.drop_index(op.f('ix_profiles_active_updated'), table_name='profiles', postgresql_where='is_active')
    op.drop_table('profiles')


def downgrade() -> None:
    _refuse_if_any("va_profiles", "going back would delete every VA.")
    op.create_table('profiles',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False),
    sa.Column('user_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('username', sa.VARCHAR(length=30), autoincrement=False, nullable=False),
    sa.Column('first_name', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('last_name', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('bio', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('photo_url', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('is_active', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.CheckConstraint("username::text ~ '^[a-z0-9][a-z0-9_-]{2,29}$'::text", name=op.f('ck_profiles_username_format')),
    sa.CheckConstraint('char_length(bio) <= 500', name=op.f('ck_profiles_bio_length')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_profiles_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_profiles')),
    sa.UniqueConstraint('user_id', name=op.f('uq_profiles_user_id'), postgresql_include=[], postgresql_nulls_not_distinct=False),
    sa.UniqueConstraint('username', name=op.f('uq_profiles_username'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_index(op.f('ix_profiles_active_updated'), 'profiles', ['updated_at'], unique=False, postgresql_where='is_active')
    op.create_table('external_links',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False),
    sa.Column('profile_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('destination_url', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('is_active', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.CheckConstraint('char_length(destination_url) <= 2048', name=op.f('ck_external_links_destination_length')),
    sa.ForeignKeyConstraint(['profile_id'], ['profiles.id'], name=op.f('fk_external_links_profile_id_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_external_links')),
    sa.UniqueConstraint('profile_id', name=op.f('uq_external_links_profile_id'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.add_column('profile_visits', sa.Column('profile_id', sa.UUID(), autoincrement=False, nullable=False))
    op.drop_constraint(op.f('fk_profile_visits_va_profile_id_va_profiles'), 'profile_visits', type_='foreignkey')
    op.create_foreign_key(op.f('fk_profile_visits_profile_id_profiles'), 'profile_visits', 'profiles', ['profile_id'], ['id'], ondelete='CASCADE')
    op.drop_index('ix_profile_visits_time', table_name='profile_visits')
    op.drop_index('ix_profile_visits_profile_time', table_name='profile_visits')
    op.create_index(op.f('ix_profile_visits_profile_time'), 'profile_visits', ['profile_id', sa.literal_column('visited_at DESC')], unique=False)
    op.drop_column('profile_visits', 'va_profile_id')
    op.add_column('click_events', sa.Column('profile_id', sa.UUID(), autoincrement=False, nullable=False))
    op.drop_constraint(op.f('fk_click_events_va_profile_id_va_profiles'), 'click_events', type_='foreignkey')
    op.create_foreign_key(op.f('fk_click_events_profile_id_profiles'), 'click_events', 'profiles', ['profile_id'], ['id'], ondelete='CASCADE')
    op.drop_index('ix_click_events_time', table_name='click_events')
    op.drop_index('ix_click_events_profile_time', table_name='click_events')
    op.create_index(op.f('ix_click_events_profile_time'), 'click_events', ['profile_id', sa.literal_column('clicked_at DESC')], unique=False)
    op.drop_column('click_events', 'va_profile_id')
    op.drop_table('va_external_links')
    op.drop_table('va_profiles')
