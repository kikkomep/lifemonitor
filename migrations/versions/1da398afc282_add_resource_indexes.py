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
