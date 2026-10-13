"""HTTP API: a thin FastAPI layer over the service layer."""

from bugflow.api.app import create_app

__all__ = ["create_app"]
