"""Vercel serverless entry point for GEO Analyzer."""
import sys
import os

# Add parent directory to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set DB path to /tmp (only writable dir on Vercel)
os.environ.setdefault("DB_PATH", "/tmp/geo_analyzer.db")

from api_server import app  # noqa: E402
