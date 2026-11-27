from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def install_request_security(app: FastAPI, public_origin: str):
    """Apply the same CSRF and response policies to all mounted routers."""
    @app.middleware("http")
    async def secure_api(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("origin") != public_origin:
            response = JSONResponse({"detail": "Request origin is not permitted."}, 403)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
