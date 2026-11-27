"""Create the institution's first administrator from an interactive terminal."""
from getpass import getpass

from pydantic import ValidationError

from .database import database_engine, transactions
from .identity import NewAccount, create_account


def first_admin(connect, data):
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(67431022)")
        if db.execute("""SELECT 1 FROM account_role r JOIN account a ON a.id=r.account_id
                        WHERE r.role_name='admin' AND a.enabled LIMIT 1""").fetchone():
            raise SystemExit("An active administrator already exists. Use the account register.")
        return create_account(db, data)


if __name__ == "__main__":
    try:
        account = NewAccount(email=input("Administrator email: "), display_name=input("Display name: "),
                             password=getpass("Password (at least 12 characters): "), roles={"admin"})
    except ValidationError as error:
        raise SystemExit("; ".join(e["msg"] for e in error.errors(include_input=False))) from None
    first_admin(transactions(database_engine()), account)
    print("Administrator created. You can now sign in.")
