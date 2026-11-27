import os
from contextlib import contextmanager

from psycopg.rows import dict_row
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


def database_engine():
    url = make_url(os.environ["DATABASE_URL"])
    if url.get_backend_name() not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must point to PostgreSQL.")
    return create_engine(url.set(drivername="postgresql+psycopg"), pool_pre_ping=True,
                         hide_parameters=True)


def transactions(engine):
    """Use the same connection pool and isolation level in all three features."""
    @contextmanager
    def connect():
        with engine.begin() as connection:
            with connection.connection.driver_connection.cursor(row_factory=dict_row) as cursor:
                yield cursor
    return connect
