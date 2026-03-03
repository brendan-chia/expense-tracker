"""Vercel serverless entrypoint — re-exports the FastAPI app."""
import os
from dotenv import load_dotenv

# Load .env if present (local dev); on Vercel env vars come from the dashboard.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

from server.main import app  # noqa: E402 — must come after load_dotenv

__all__ = ["app"]
