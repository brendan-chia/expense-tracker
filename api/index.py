"""Vercel serverless entrypoint — re-exports the FastAPI app."""

from server.main import app

__all__ = ["app"]
