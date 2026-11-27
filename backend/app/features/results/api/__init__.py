"""FastAPI layer for the results feature."""
from .errors import ResultsRoute, error_body, render_error
from .router import build_router

__all__ = ["ResultsRoute", "build_router", "error_body", "render_error"]
