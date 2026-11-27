import os
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .features import results
from .features.authoring.adapters.sql import SqlDatabase
from .features.authoring.api.router import build_router as authoring_router
from .features.authoring.services import AuthoringModule
from .features.delivery.router import create_router as delivery_router
from .features.delivery.worker import expiry_worker
from .platform.database import database_engine, transactions
from .platform.identity import HASHER, Identity, role_dependencies
from .platform.security import install_request_security


def create_app():
    origin = os.environ["PUBLIC_ORIGIN"].rstrip("/")
    url = urlsplit(origin)
    local_http = url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
    if not url.hostname or url.path or url.query or url.fragment or url.username or (url.scheme != "https" and not local_http):
        raise ValueError("PUBLIC_ORIGIN must be the frontend HTTPS origin, or HTTP on localhost.")
    engine = database_engine()
    connect = transactions(engine)
    identity = Identity(connect, secure_cookie=not local_http)
    actor, account_id = role_dependencies(identity)

    @asynccontextmanager
    async def lifespan(app):
        try:
            async with expiry_worker(connect, results.score_objective):
                yield
        finally:
            engine.dispose()

    app = FastAPI(title="Folio Examination Office", lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)

    install_request_security(app, origin)

    @app.get("/api/health", responses={503: {"description": "Database unavailable or schema missing"}})
    def health():
        try:
            with engine.connect() as connection:
                connection.exec_driver_sql("SELECT id FROM account LIMIT 0")
        except SQLAlchemyError:
            return JSONResponse({"status": "unavailable"}, 503)
        return {"status": "ok"}

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Pydantic includes the original input in its default validation response.
        issues = [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in error.errors()]
        return JSONResponse({"error": {"message": "Check the submitted fields.", "issues": issues}}, 422)

    authoring = AuthoringModule(SqlDatabase(engine, hasher=HASHER.hash).unit_of_work)
    reports = results.ResultsModule(results.sql_uow_factory(engine), results.ReportLabPdfRenderer())
    for router in (identity.router(), authoring_router(authoring, actor),
                   delivery_router(connect, account_id, results.score_objective), results.build_router(reports, actor)):
        app.include_router(router, prefix="/api")
    return app
