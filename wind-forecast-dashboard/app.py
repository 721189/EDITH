"""Vercel entrypoint for FastAPI."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
from src.app import app  # noqa: E402
