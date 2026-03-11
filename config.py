"""Centralized configuration for GEO Analyzer."""
import os
import secrets

# ── JWT ──
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 72

# ── Google API Keys (optional — app works without these) ──
API_KEYS = {
    "kg_api_key":     os.environ.get("GOOGLE_KG_KEY", os.environ.get("ENTITYOS_KG_KEY", "")),
    "places_api_key": os.environ.get("GOOGLE_PLACES_KEY", os.environ.get("ENTITYOS_PLACES_KEY", "")),
    "nlp_api_key":    os.environ.get("GOOGLE_NLP_KEY", os.environ.get("ENTITYOS_NLP_KEY", "")),
    "gemini_api_key": os.environ.get("GOOGLE_GEMINI_KEY", os.environ.get("ENTITYOS_GEMINI_KEY", "")),
}

# ── Plan Limits (analyses per day) ──
PLAN_LIMITS = {
    "free":    3,
    "starter": 25,
    "pro":     100,
    "admin":   999999,
}

# ── Database ──
DB_PATH = os.path.join(os.path.dirname(__file__), "geo_analyzer.db")

# ── Analysis Defaults ──
DEFAULT_TIMEOUT = 30
MAX_SITEMAP_PAGES = 50
