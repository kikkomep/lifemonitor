"""Add CRATE property to keep track of repository availability

Revision ID: 17bc254d1628
Revises: 1da398afc282
Create Date: 2025-08-28 10:09:16.165622

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '17bc254d1628'
down_revision = '1da398afc282'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ro_crate', schema=None) as batch_op:
        batch_op.add_column(sa.Column('repo_exists', sa.Boolean()))

    # Update all existing records to set repo_exists to True
    op.execute("UPDATE ro_crate SET repo_exists = TRUE")

    # Alter the table to set the record as not nullable
    op.alter_column('ro_crate', 'repo_exists', nullable=False)


def downgrade():
    with op.batch_alter_table('ro_crate', schema=None) as batch_op:
        batch_op.drop_column('repo_exists')
