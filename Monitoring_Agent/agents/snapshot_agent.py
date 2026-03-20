"""
Agent 1 — SnapshotAgent
Monitoring & UI State Intelligence.

Responsibilities:
  - Continuously observe dashboard via Playwright
  - Capture DOM snapshots → site_snapshot.json
  - Inject MutationObserver for live change tracking → live_changes.json
  - Detect errors and maintain error lifecycle → error_log.csv
  - Trigger DiagnosisAgent when unresolved errors are found
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Callable, Coroutine

from playwright.async_api import Page

from core.config import (
    MONITOR_POLL_INTERVAL_SEC,
    MUTATION_FLUSH_INTERVAL_SEC,
)
from core.models import (
    ErrorEntry,
    ErrorStatus,
    LiveChange,
    SiteSnapshot,
    SnapshotElement,
)
from core.shared_memory import (
    append_error_log,
    append_live_changes,
    write_snapshot,
)

logger = logging.getLogger("SnapshotAgent")


# JavaScript to inject MutationObserver into the page
MUTATION_OBSERVER_JS = """
() => {
    if (window.__monitorObserverActive) return;
    window.__liveChanges = [];
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((m) => {
            const entry = {
                timestamp: new Date().toISOString(),
                mutation_type: m.type,
                target_selector: (m.target.id ? '#' + m.target.id : m.target.tagName || ''),
                added_nodes: m.addedNodes ? m.addedNodes.length : 0,
                removed_nodes: m.removedNodes ? m.removedNodes.length : 0,
                attribute_name: m.attributeName || null,
                details: ''
            };
            // Track error popup visibility changes
            if (m.target.id === 'simPopupContainer' || m.target.id === 'errorTableBody') {
                entry.details = 'error_related';
            }
            window.__liveChanges.push(entry);
            // Cap at 200 to prevent memory issues
            if (window.__liveChanges.length > 200) {
                window.__liveChanges = window.__liveChanges.slice(-200);
            }
        });
    });
    observer.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['class', 'style', 'hidden']
    });
    window.__monitorObserverActive = true;
    console.log('[SnapshotAgent] MutationObserver injected.');
}
"""

# JavaScript to capture DOM snapshot of key interactive elements
SNAPSHOT_JS = """
() => {
    const selectors = 'button, input, select, a, [role="alert"], .error, .alert-danger, .resolve-btn, tr[id^="row-ERR-"], #simPopupContainer, #simPopupMessage, #errorTableBody, .menu-item, .product-card';
    const elements = document.querySelectorAll(selectors);
    const result = [];
    elements.forEach(el => {
        result.push({
            tag: el.tagName.toLowerCase(),
            id: el.id || null,
            classes: Array.from(el.classList),
            text: (el.textContent || '').trim().substring(0, 200),
            selector: el.id ? '#' + el.id : (el.className ? el.tagName.toLowerCase() + '.' + Array.from(el.classList).join('.') : el.tagName.toLowerCase()),
            attributes: {
                type: el.getAttribute('type') || '',
                href: el.getAttribute('href') || '',
                disabled: el.disabled ? 'true' : 'false',
                hidden: el.classList.contains('hidden') ? 'true' : 'false',
                value: (el.value || '').substring(0, 100)
            },
            children_count: el.children.length
        });
    });
    return result;
}
"""

# JavaScript to read the error table rows from the dashboard
ERROR_TABLE_JS = """
() => {
    // Try to find the error table dynamically
    const tables = document.querySelectorAll('table');
    let errorTable = null;
    for (const table of tables) {
        if (table.textContent.toLowerCase().includes('error id')) {
            errorTable = table;
            break;
        }
    }

    if (!errorTable) return [];

    const rows = errorTable.querySelectorAll('tbody tr, tr:not(:first-child)');
    const errors = [];
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length >= 3) {
            const resolveBtn = row.querySelector('button');
            const isResolved = resolveBtn ? (resolveBtn.classList.contains('resolved') || resolveBtn.textContent.toLowerCase().includes('resolved')) : false;
            
            const error_id = cells[0].textContent.trim();
            if (error_id && error_id.startsWith('ERR-')) {
                errors.push({
                    id: error_id,
                    error_id: error_id,
                    message: cells[1].textContent.trim(),
                    time: cells[2].textContent.trim(),
                    is_resolved: isResolved,
                    button_text: resolveBtn ? resolveBtn.textContent.trim() : ''
                });
            }
        }
    });
    return errors;
}
"""

# JavaScript to flush and clear live changes
FLUSH_CHANGES_JS = """
() => {
    const changes = window.__liveChanges || [];
    window.__liveChanges = [];
    return changes;
}
"""


class SnapshotAgent:
    """Monitors the dashboard, captures snapshots, detects errors."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._running = False
        self._known_errors: set[str] = set()  # Track error IDs we've already processed
        self._on_error_callback: Callable[[ErrorEntry], Coroutine] | None = None
        self._monitor_task: asyncio.Task | None = None
        self._mutation_task: asyncio.Task | None = None

    # ─── Public API ───────────────────────────────────────────────────────

    def set_error_callback(self, callback: Callable[[ErrorEntry], Coroutine]) -> None:
        """Register a callback to invoke when a new unresolved error is detected."""
        self._on_error_callback = callback

    async def start(self, page: Page) -> None:
        """Begin monitoring the dashboard page."""
        logger.info(f"[Session {self.session_id}] SnapshotAgent starting...")
        self._running = True

        # Inject MutationObserver
        await self.inject_mutation_observer(page)

        # Start monitoring loops
        self._monitor_task = asyncio.create_task(self._monitoring_loop(page))
        self._mutation_task = asyncio.create_task(self._mutation_flush_loop(page))

        logger.info(f"[Session {self.session_id}] SnapshotAgent active — monitoring dashboard.")

    async def stop(self) -> None:
        """Stop monitoring."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
        if self._mutation_task:
            self._mutation_task.cancel()
        logger.info(f"[Session {self.session_id}] SnapshotAgent stopped.")

    # ─── Core Loops ───────────────────────────────────────────────────────

    async def _monitoring_loop(self, page: Page) -> None:
        """Main monitoring loop: capture snapshot → detect errors → trigger."""
        while self._running:
            try:
                # 1. Capture DOM snapshot
                snapshot = await self.capture_snapshot(page)
                write_snapshot(snapshot)

                # 2. Detect errors from the error table
                errors = await self.detect_errors(page)

                # 3. Process new unresolved errors
                for error in errors:
                    if error.error_id not in self._known_errors and error.status == ErrorStatus.UNRESOLVED:
                        self._known_errors.add(error.error_id)
                        append_error_log(error)
                        logger.info(f"New error detected: {error.error_id} — {error.error_message}")

                        # Trigger diagnosis
                        if self._on_error_callback:
                            await self._on_error_callback(error)

                await asyncio.sleep(MONITOR_POLL_INTERVAL_SEC)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}", exc_info=True)
                await asyncio.sleep(MONITOR_POLL_INTERVAL_SEC)

    async def _mutation_flush_loop(self, page: Page) -> None:
        """Periodically flush MutationObserver data to disk."""
        while self._running:
            try:
                changes_raw = await page.evaluate(FLUSH_CHANGES_JS)
                if changes_raw:
                    changes = [LiveChange(**c) for c in changes_raw]
                    append_live_changes(changes)

                await asyncio.sleep(MUTATION_FLUSH_INTERVAL_SEC)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Mutation flush error: {e}")
                await asyncio.sleep(MUTATION_FLUSH_INTERVAL_SEC)

    # ─── Snapshot Generation ──────────────────────────────────────────────

    async def inject_mutation_observer(self, page: Page) -> None:
        """Inject the MutationObserver script into the page."""
        try:
            await page.evaluate(MUTATION_OBSERVER_JS)
            logger.info("MutationObserver injected successfully.")
        except Exception as e:
            logger.error(f"Failed to inject MutationObserver: {e}")

    async def capture_snapshot(self, page: Page) -> SiteSnapshot:
        """Capture a structured snapshot of the current DOM state."""
        try:
            elements_raw = await page.evaluate(SNAPSHOT_JS)
            elements = [SnapshotElement(**el) for el in elements_raw]
            url = page.url

            snapshot = SiteSnapshot(
                session_id=self.session_id,
                url=url,
                elements=elements,
            )
            return snapshot
        except Exception as e:
            logger.error(f"Snapshot capture failed: {e}")
            return SiteSnapshot(session_id=self.session_id)

    # ─── Error Detection ─────────────────────────────────────────────────

    async def detect_errors(self, page: Page) -> list[ErrorEntry]:
        """Scan for unresolved errors dynamically."""
        errors: list[ErrorEntry] = []
        try:
            table_errors = await page.evaluate(ERROR_TABLE_JS)

            for err in table_errors:
                if not err.get("is_resolved", False):
                    # For extra data, we can look for any active alert/popup
                    extra_data = {}
                    try:
                        # Dynamic search for alert text
                        alert_text = await page.evaluate("""
                            () => {
                                const alerts = document.querySelectorAll('[role="alert"], .alert, #custAlertMsg, .error-msg');
                                for (const a of alerts) {
                                    if (a.offsetParent !== null) return a.textContent.trim();
                                }
                                return '';
                            }
                        """)
                        if alert_text:
                            extra_data["alert_text"] = alert_text
                    except Exception:
                        pass

                    error_entry = ErrorEntry(
                        error_id=err["error_id"],
                        error_message=err["message"],
                        element_reference=f"text='{err['error_id']}'", 
                        status=ErrorStatus.UNRESOLVED,
                        session_id=self.session_id,
                        extra_data=extra_data,
                    )
                    errors.append(error_entry)

        except Exception as e:
            logger.error(f"Error detection failed: {e}")

        return errors

    def mark_error_known(self, error_id: str) -> None:
        """Mark an error as already processed (after resolution attempt)."""
        self._known_errors.add(error_id)
