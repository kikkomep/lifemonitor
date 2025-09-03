"""add_resource_indexes

Revision ID: 1da398afc282
Revises: 9edbfbab3dc2
Create Date: 2025-08-28 09:56:02.099106

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '1da398afc282'
down_revision = '9edbfbab3dc2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('resource', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_resource_uri'), ['uri'], unique=False)
        batch_op.create_index(batch_op.f('ix_resource_uuid'), ['uuid'], unique=False)


def downgrade():
    with op.batch_alter_table('resource', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_resource_uuid'))
        batch_op.drop_index(batch_op.f('ix_resource_uri'))
