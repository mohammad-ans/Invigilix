import hashlib
import re
import secrets
from typing import Literal
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from ..features.results.ports import Actor

HASHER = PasswordHasher()
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))
SESSION_SECONDS = 12 * 60 * 60
COOKIE = "folio_session"
Role = Literal["admin", "examiner", "candidate"]
COLUMNS = """a.id, a.email, a.display_name, a.enabled,
    ARRAY(SELECT role_name FROM account_role WHERE account_id=a.id ORDER BY role_name) AS roles"""


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=254)
    password: SecretStr = Field(min_length=1, max_length=256)


class AccountAccess(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=150)
    roles: set[Role] = Field(min_length=1, max_length=3)
    enabled: bool = True

    @field_validator("display_name")
    @classmethod
    def validate_name(cls, name):
        if not name.strip():
            raise ValueError("Enter a display name.")
        return name.strip()


class NewAccount(AccountAccess, Credentials):
    password: SecretStr = Field(min_length=12, max_length=256)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        email = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValueError("Enter a valid email address.")
        return email


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_account(db, data):
    account_id = uuid4()
    try:
        db.execute("""INSERT INTO account(id,email,display_name,password_hash,enabled)
                      VALUES (%s,%s,%s,%s,%s)""",
                   (account_id, data.email, data.display_name,
                    HASHER.hash(data.password.get_secret_value()), data.enabled))
    except UniqueViolation:
        raise HTTPException(409, "This email already has an account.") from None
    db.executemany("INSERT INTO account_role VALUES (%s,%s)",
                   [(account_id, role) for role in sorted(data.roles)])
    return account_id


class Identity:
    def __init__(self, connect, secure_cookie):
        self.connect = connect
        self.secure_cookie = secure_cookie

    def account(self, request: Request):
        token = request.cookies.get(COOKIE)
        if token and len(token) <= 128:
            with self.connect() as db:
                account = db.execute(f"""SELECT {COLUMNS}, s.expires_at
                    FROM login_session s JOIN account a ON a.id=s.account_id
                    WHERE s.token_hash=%s AND s.expires_at>clock_timestamp() AND a.enabled""",
                    (digest(token),)).fetchone()
                if account:
                    return account
        raise HTTPException(401, "Sign in to continue.")

    def router(self):
        api = APIRouter()

        @api.get("/session")
        def session(account=Depends(self.account)):
            return account

        @api.post("/sessions")
        def login(data: Credentials, request: Request, response: Response):
            with self.connect() as db:
                row = db.execute(f"""SELECT {COLUMNS}, a.password_hash FROM account a
                    WHERE lower(trim(a.email))=%s FOR SHARE OF a""",
                    (data.email.strip().lower(),)).fetchone()
                stored_hash = row.pop("password_hash") if row else DUMMY_HASH
                try:
                    HASHER.verify(stored_hash, data.password.get_secret_value())
                except (VerificationError, InvalidHashError):
                    raise HTTPException(401, "Email or password is incorrect.") from None
                if not row or not row["enabled"]:
                    raise HTTPException(401, "Email or password is incorrect.")
                token = secrets.token_urlsafe(32)
                db.execute("DELETE FROM login_session WHERE token_hash=%s OR (account_id=%s AND expires_at<=now())",
                           (digest(request.cookies.get(COOKIE, "")), row["id"]))
                row["expires_at"] = db.execute("""INSERT INTO login_session VALUES
                    (%s,%s,now() + %s * interval '1 second') RETURNING expires_at""",
                    (digest(token), row["id"], SESSION_SECONDS)).fetchone()["expires_at"]
            response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                                secure=self.secure_cookie, samesite="lax", path="/")
            return row

        @api.delete("/session", status_code=204)
        def logout(request: Request, response: Response):
            with self.connect() as db:
                db.execute("DELETE FROM login_session WHERE token_hash=%s",
                           (digest(request.cookies.get(COOKIE, "")),))
            response.delete_cookie(COOKIE, path="/", secure=self.secure_cookie,
                                   httponly=True, samesite="lax")

        def admin(account=Depends(self.account)):
            if "admin" not in account["roles"]:
                raise HTTPException(403, "Administrator access required.")
            return account

        @api.get("/admin/accounts")
        def accounts(_=Depends(admin)):
            with self.connect() as db:
                return db.execute(f"SELECT {COLUMNS} FROM account a ORDER BY lower(a.display_name), a.email").fetchall()

        @api.post("/admin/accounts", status_code=201)
        def add(data: NewAccount, _=Depends(admin)):
            with self.connect() as db:
                return {"id": create_account(db, data)}

        @api.patch("/admin/accounts/{account_id}")
        def update(account_id: UUID, data: AccountAccess, caller=Depends(admin)):
            if caller["id"] == account_id and (not data.enabled or "admin" not in data.roles):
                raise HTTPException(409, "Keep administrator access on your current account.")
            with self.connect() as db:
                old = db.execute(f"SELECT {COLUMNS} FROM account a WHERE id=%s FOR UPDATE", (account_id,)).fetchone()
                if not old:
                    raise HTTPException(404, "Account unavailable.")
                db.execute("UPDATE account SET display_name=%s,enabled=%s WHERE id=%s",
                           (data.display_name, data.enabled, account_id))
                db.execute("DELETE FROM account_role WHERE account_id=%s", (account_id,))
                db.executemany("INSERT INTO account_role VALUES (%s,%s)",
                               [(account_id, role) for role in sorted(data.roles)])
                if not data.enabled or set(old["roles"]) != data.roles:
                    db.execute("DELETE FROM login_session WHERE account_id=%s", (account_id,))
                return {"id": account_id}

        @api.get("/me/results")
        def released(account=Depends(self.account)):
            if "candidate" not in account["roles"]:
                raise HTTPException(403, "Candidate access required.")
            with self.connect() as db:
                return db.execute("""SELECT a.id AS attempt_id,e.title,e.results_published_at
                    FROM attempt a JOIN exam e ON e.id=a.exam_id
                    WHERE a.candidate_id=%s AND a.finalized_at IS NOT NULL
                    AND e.results_published_at IS NOT NULL ORDER BY e.results_published_at DESC""",
                    (account["id"],)).fetchall()
        return api


def role_dependencies(identity):
    def actor(account=Depends(identity.account)):
        return Actor(account["id"], frozenset(account["roles"]))

    def account_id(account=Depends(identity.account)):
        return account["id"]

    return actor, account_id
