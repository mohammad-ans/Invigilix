"""Apply Alembic revisions and provision the configured demonstration accounts."""
import os

from pydantic import ValidationError

from backend.app.platform.database import database_engine, transactions
from backend.app.platform.identity import NewAccount, create_account
from backend.app.platform.migrate import upgrade

ROLES = ("admin", "examiner", "candidate")


def configured_accounts():
    variables = {role: f"FOLIO_SEED_{role.upper()}_PASSWORD" for role in ROLES}
    if all(name not in os.environ for name in variables.values()):
        return []

    accounts = []
    for role, name in variables.items():
        try:
            account = NewAccount(email=f"demo-{role}@example.test", display_name=f"Demo {role}",
                                 roles={role}, password=os.environ.get(name, ""))
        except ValidationError:
            raise SystemExit(f"Set {name} to a password between 12 and 256 characters.") from None
        accounts.append(account)
    return accounts


def predeploy(engine):
    accounts = configured_accounts()
    upgrade(engine)
    if not accounts:
        return
    connect = transactions(engine)
    with connect() as db:
        # Share the first-admin bootstrap lock, including across overlapping releases.
        db.execute("SELECT pg_advisory_xact_lock(67431022)")
        for account in accounts:
            exists = db.execute("SELECT 1 FROM account WHERE lower(trim(email))=%s",
                                (account.email,)).fetchone()
            if not exists:
                create_account(db, account)


if __name__ == "__main__":
    predeploy(database_engine())
