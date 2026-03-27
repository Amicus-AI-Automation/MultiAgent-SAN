"""
Shared memory utilities for inter-agent file I/O.
Thread-safe read/write for all shared JSON and CSV artifacts.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from threading import Lock

from core.config import (
    ERROR_LOG_FILE,
    EXECUTION_HISTORY_FILE,
    LIVE_CHANGES_FILE,
    SITE_SNAPSHOT_FILE,
    SELECTOR_CACHE_FILE,
)
from core.models import (
    ErrorEntry,
    ExecutionResult,
    LiveChange,
    SiteSnapshot,
)

logger = logging.getLogger("SharedMemory")

# Global lock for file operations
_file_lock = Lock()


# Site Snapshot 
def write_snapshot(snapshot: SiteSnapshot) -> None:
    """Save a site snapshot to disk."""
    with _file_lock:
        SITE_SNAPSHOT_FILE.write_text(
            snapshot.model_dump_json(indent=2),
            encoding="utf-8",
        )
    logger.debug("Snapshot saved.")


def read_snapshot() -> SiteSnapshot | None:
    """Load the latest site snapshot from disk."""
    if not SITE_SNAPSHOT_FILE.exists():
        return None
    try:
        data = json.loads(SITE_SNAPSHOT_FILE.read_text(encoding="utf-8"))
        return SiteSnapshot(**data)
    except Exception as e:
        logger.warning(f"Could not read snapshot: {e}")
        return None


# Live Changes 

def append_live_changes(changes: list[LiveChange]) -> None:
    """Append mutation records to the live changes file."""
    with _file_lock:
        existing = []
        if LIVE_CHANGES_FILE.exists():
            try:
                existing = json.loads(LIVE_CHANGES_FILE.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        existing.extend([c.model_dump() for c in changes])
        # Keep only last 500 entries to prevent unbounded growth
        if len(existing) > 500:
            existing = existing[-500:]
        LIVE_CHANGES_FILE.write_text(
            json.dumps(existing, indent=2, default=str),
            encoding="utf-8",
        )
    logger.debug(f"Appended {len(changes)} live changes.")


def read_live_changes() -> list[LiveChange]:
    """Read all live changes from disk."""
    if not LIVE_CHANGES_FILE.exists():
        return []
    try:
        data = json.loads(LIVE_CHANGES_FILE.read_text(encoding="utf-8"))
        return [LiveChange(**entry) for entry in data]
    except Exception as e:
        logger.warning(f"Could not read live changes: {e}")
        return []


# Error Log (CSV) 

ERROR_CSV_HEADERS = [
    "timestamp", "session_id", "error_id", "message", "status", "resolved_time"
]


def _ensure_error_log_exists() -> None:
    """Create error_log.csv with headers if it doesn't exist."""
    if not ERROR_LOG_FILE.exists():
        with open(ERROR_LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(ERROR_CSV_HEADERS)


def append_error_log(error: ErrorEntry) -> None:
    """Append an error entry to error_log.csv."""
    with _file_lock:
        _ensure_error_log_exists()
        with open(ERROR_LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                error.timestamp,
                error.session_id,
                error.error_id,
                error.error_message,
                error.status.value,
                error.resolved_time or "",
            ])
    logger.debug(f"Error logged: {error.error_id}")


def update_error_status(error_id: str, status: str, resolved_time: str | None = None) -> None:
    """Update the status of an error in error_log.csv."""
    with _file_lock:
        _ensure_error_log_exists()
        rows = []
        with open(ERROR_LOG_FILE, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 3 and row[2] == error_id:
                    row[4] = status
                    if resolved_time:
                        row[5] = resolved_time
                rows.append(row)
        with open(ERROR_LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
    logger.debug(f"Error status updated: {error_id} → {status}")


def read_error_log() -> list[dict]:
    """Read all error log entries."""
    _ensure_error_log_exists()
    entries = []
    with open(ERROR_LOG_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append(dict(row))
    return entries


# Execution History 

def append_execution_history(result: ExecutionResult) -> None:
    """Append an execution result to the history file."""
    with _file_lock:
        existing = []
        if EXECUTION_HISTORY_FILE.exists():
            try:
                existing = json.loads(
                    EXECUTION_HISTORY_FILE.read_text(encoding="utf-8")
                )
            except Exception:
                existing = []
        existing.append(result.model_dump())
        EXECUTION_HISTORY_FILE.write_text(
            json.dumps(existing, indent=2, default=str),
            encoding="utf-8",
        )
    logger.debug(f"Execution result logged: {result.error_id} → {result.resolution_status.value}")


def read_execution_history() -> list[ExecutionResult]:
    """Read all execution history entries."""
    if not EXECUTION_HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(EXECUTION_HISTORY_FILE.read_text(encoding="utf-8"))
        return [ExecutionResult(**entry) for entry in data]
    except Exception as e:
        logger.warning(f"Could not read execution history: {e}")
        return []
# Selector Cache 

def get_cached_plan(issue_type: str, error_message: str) -> list[dict] | None:
    """Retrieve a previously grounded execution plan from cache."""
    if not SELECTOR_CACHE_FILE.exists():
        return None
    
    with _file_lock:
        try:
            cache = json.loads(SELECTOR_CACHE_FILE.read_text(encoding="utf-8"))
            # Match by issue_type (exact) and error_message (normalized)
            cache_key = f"{issue_type}|{error_message.strip().lower()}"
            return cache.get(cache_key)
        except Exception as e:
            logger.warning(f"Could not read selector cache: {e}")
            return None


def save_to_cache(issue_type: str, error_message: str, steps: list[dict]) -> None:
    """Save grounded execution steps to the selector cache."""
    with _file_lock:
        cache = {}
        if SELECTOR_CACHE_FILE.exists():
            try:
                cache = json.loads(SELECTOR_CACHE_FILE.read_text(encoding="utf-8"))
            except Exception:
                cache = {}
        
        cache_key = f"{issue_type}|{error_message.strip().lower()}"
        cache[cache_key] = steps
        
        SELECTOR_CACHE_FILE.write_text(
            json.dumps(cache, indent=2),
            encoding="utf-8",
        )
    logger.info(f"Execution plan cached for: {issue_type}")
