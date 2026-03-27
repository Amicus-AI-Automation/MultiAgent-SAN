"""
Centralized configuration for the Monitoring Agent system.
All settings, URLs, paths, and tunables in one place.
"""

import os
from dotenv import load_dotenv
from pathlib import Path
# Always load .env from the project root (WebOps/.env or WebOps/Monitoring_Agent/.env)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PATHS = [
	PROJECT_ROOT / '.env',
	PROJECT_ROOT / 'Monitoring_Agent' / '.env',
]
for dotenv_path in DOTENV_PATHS:
	if dotenv_path.exists():
		load_dotenv(dotenv_path=dotenv_path, override=True)

# Base Paths 
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAG_DIR = BASE_DIR / "rag_sys"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

# Target Website
TARGET_URL = os.getenv("MONITOR_TARGET_URL", "https://multi-agent-san.vercel.app/")
LOGIN_URL = os.getenv("MONITOR_LOGIN_URL", "https://multi-agent-san.vercel.app/")
DASHBOARD_URL = os.getenv("MONITOR_DASHBOARD_URL", "https://multi-agent-san.vercel.app/dashboard.html")

# Credentials
LOGIN_EMAIL = os.getenv("MONITOR_USERNAME", "oparch19@gmail.com")
LOGIN_PASSWORD = os.getenv("MONITOR_PASSWORD", "123456789")

# Shared Data Files
SITE_SNAPSHOT_FILE = DATA_DIR / "site_snapshot.json"
LIVE_CHANGES_FILE = DATA_DIR / "live_changes.json"
ERROR_LOG_FILE = DATA_DIR / "error_log.csv"
EXECUTION_HISTORY_FILE = DATA_DIR / "execution_history.json"
SESSION_REGISTRY_FILE = DATA_DIR / "session_registry.json"
SELECTOR_CACHE_FILE = DATA_DIR / "selector_cache.json"

# Timing & Retry
MONITOR_POLL_INTERVAL_SEC = 5        # How often to scan for errors (seconds)
MUTATION_FLUSH_INTERVAL_SEC = 3      # How often to flush mutation logs
ACTION_TIMEOUT_MS = 10000            # Timeout per action step (ms)
ACTION_RETRY_COUNT = 3               # Retries per action step
VERIFY_WAIT_MS = 3000                # Wait after fix before verifying
BROWSER_HEADLESS = False             # Set True for headless mode

# RAG & LLM Configuration
RAG_KNOWLEDGE_BASE = RAG_DIR / "Knowledge_base.json"
RAG_VECTOR_STORE = RAG_DIR / "vector_store.index"
RAG_MODEL_NAME = "all-MiniLM-L6-v2"
RAG_TOP_K = 1  # Number of nearest matches to retrieve

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.0-flash"

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "openai/gpt-oss-20b" 
