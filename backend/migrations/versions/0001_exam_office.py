"""Baseline schema shared by authoring, delivery, results and identity."""
from pathlib import Path

from alembic import op

revision = "0001_exam_office"
down_revision = None


def upgrade():
    path = Path(__file__).resolve().parents[3] / "contracts" / "exam_schema.sql"
    # The standalone contract owns a transaction when run with psql.
    # Alembic owns that transaction here, including its version row.
    ddl = path.read_text().split("\nBEGIN;\n", 1)[1].rsplit("\nCOMMIT;", 1)[0]
    op.get_bind().exec_driver_sql(ddl)
