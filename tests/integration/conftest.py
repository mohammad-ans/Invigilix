import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url

from backend.app.platform.database import database_engine


@pytest.fixture
def isolated_database(monkeypatch):
    dsn = os.getenv("FOLIO_TEST_DSN")
    if not dsn:
        pytest.skip("Set FOLIO_TEST_DSN to a disposable PostgreSQL database")
    schema = "integration_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as setup:
        setup.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    url = make_url(dsn).update_query_dict({"options": "-csearch_path=" + schema})
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    engine = database_engine()
    try:
        yield engine
    finally:
        engine.dispose()
        with psycopg.connect(dsn, autocommit=True) as setup:
            setup.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
