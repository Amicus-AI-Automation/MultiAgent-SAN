"""
Pydantic data models for structured inter-agent communication.
All agents exchange data exclusively through these models.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Enums ────────────────────────────────────────────────────────────────────

class ErrorStatus(str, Enum):
    UNRESOLVED = "unresolved"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    FAILED = "failed"


class ActionType(str, Enum):
    CLICK = "click"
    FILL = "fill"
    NAVIGATE = "navigate"
    WAIT = "wait"
    REFRESH = "refresh"
    SELECT = "select"


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    FAILED = "failed"


# ─── Session ──────────────────────────────────────────────────────────────────

class SessionInfo(BaseModel):
    """Represents a bound user session."""
    user_id: str = Field(description="User email or unique identifier")
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    login_timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    is_active: bool = True


# ─── Snapshot Models ──────────────────────────────────────────────────────────

class SnapshotElement(BaseModel):
    """A single DOM element captured in a snapshot."""
    tag: str
    id: Optional[str] = None
    classes: list[str] = []
    text: str = ""
    selector: str = ""
    attributes: dict[str, str] = {}
    children_count: int = 0


class SiteSnapshot(BaseModel):
    """Full UI state snapshot of the monitored page."""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    session_id: str = ""
    url: str = ""
    elements: list[SnapshotElement] = []


# ─── Live Changes ────────────────────────────────────────────────────────────

class LiveChange(BaseModel):
    """A single DOM mutation captured by MutationObserver."""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    mutation_type: str = ""        # "childList", "attributes", "characterData"
    target_selector: str = ""
    added_nodes: int = 0
    removed_nodes: int = 0
    attribute_name: Optional[str] = None
    details: str = ""


# ─── Error Models ─────────────────────────────────────────────────────────────

class ErrorEntry(BaseModel):
    """An error detected on the dashboard."""
    error_id: str = ""
    error_message: str = ""
    element_reference: str = ""     # CSS selector of the error source
    status: ErrorStatus = ErrorStatus.UNRESOLVED
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    resolved_time: Optional[str] = None
    session_id: str = ""
    extra_data: dict[str, Any] = {}  # e.g. reported email/password for customer errors


# ─── Execution Models ────────────────────────────────────────────────────────

class ExecutionStep(BaseModel):
    """A single UI action to perform."""
    action: ActionType
    selector: str = ""              # CSS selector to target
    value: str = ""                 # Value for fill/navigate actions
    description: str = ""           # Human-readable step description
    timeout_ms: int = 10000


class ExecutionPlan(BaseModel):
    """Ordered list of steps to resolve an error."""
    error_id: str
    error_message: str = ""
    execution_steps: list[ExecutionStep] = []
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class ExecutionResult(BaseModel):
    """Outcome of executing a resolution plan."""
    error_id: str
    resolution_status: ResolutionStatus
    steps_completed: int = 0
    steps_total: int = 0
    details: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
