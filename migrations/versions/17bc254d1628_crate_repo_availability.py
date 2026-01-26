# Copyright (c) 2020-2026 CRS4
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

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
