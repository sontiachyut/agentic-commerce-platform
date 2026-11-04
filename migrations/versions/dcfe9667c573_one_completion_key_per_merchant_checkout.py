"""one completion key per merchant checkout"""

import sqlalchemy as sa
from alembic import op

revision = "dcfe9667c573"
down_revision = "1fa4520c7735"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "protocol_commands", sa.Column("checkout_scope", sa.String(length=64), nullable=True)
    )
    op.create_unique_constraint(
        "protocol_commands_checkout_scope_key", "protocol_commands", ["checkout_scope"]
    )


def downgrade():
    op.drop_constraint("protocol_commands_checkout_scope_key", "protocol_commands", type_="unique")
    op.drop_column("protocol_commands", "checkout_scope")
