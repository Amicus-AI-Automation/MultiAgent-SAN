"""
Orchestrator — Agent Coordinator & Lifecycle Manager.

Coordinates the three agents:
  SnapshotAgent → DiagnosisAgent → ExecutionAgent

Handles:
  - Agent initialization and shutdown
  - Error pipeline: detect → diagnose → execute → verify → log
  - Browser crash recovery
  - Continuous monitoring loop
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from playwright.async_api import Page, Browser, BrowserContext

from agents.snapshot_agent import SnapshotAgent
from agents.diagnosis_agent import DiagnosisAgent
from agents.execution_agent import ExecutionAgent
from core.models import (
    ErrorEntry,
    ErrorStatus,
    ExecutionResult,
    ResolutionStatus,
)
from core.shared_memory import (
    read_snapshot,
    update_error_status,
)

logger = logging.getLogger("Orchestrator")


class AgentOrchestrator:
    """Coordinates all three agents and manages the error resolution pipeline."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._running = False
        self._processing_lock = asyncio.Lock()
        self._active_errors: set[str] = set()  # Currently being processed

        # Initialize agents
        self.snapshot_agent = SnapshotAgent(session_id)
        self.diagnosis_agent = DiagnosisAgent()
        self.execution_agent = ExecutionAgent()

        # Register error callback
        self.snapshot_agent.set_error_callback(self._on_error_detected)

        logger.info(f"Orchestrator initialized for session {session_id}")

    # ─── Public API ───────────────────────────────────────────────────────

    async def start(self, page: Page) -> None:
        """
        Start the orchestrator and all agents.
        Begins the continuous monitoring loop.
        """
        logger.info("=" * 60)
        logger.info("  AGENTIC MONITORING SYSTEM ACTIVATED")
        logger.info(f"  Session: {self.session_id}")
        logger.info(f"  Time: {datetime.now().isoformat()}")
        logger.info("=" * 60)

        self._running = True
        self._page = page

        # Start the SnapshotAgent monitoring loop
        await self.snapshot_agent.start(page)

        logger.info("All agents active. Monitoring dashboard...")

    async def stop(self) -> None:
        """Gracefully stop all agents."""
        logger.info("Shutting down orchestrator...")
        self._running = False
        await self.snapshot_agent.stop()
        logger.info("All agents stopped. Orchestrator shutdown complete.")

    # ─── Error Pipeline ───────────────────────────────────────────────────

    async def _on_error_detected(self, error: ErrorEntry) -> None:
        """
        Pipeline triggered when SnapshotAgent detects a new error.
        
        Flow:
          1. SnapshotAgent detected error
          2. DiagnosisAgent retrieves fix steps from RAG
          3. ExecutionAgent executes corrective actions
          4. Verify resolution
          5. Log result
          6. Continue monitoring
        """
        # Prevent duplicate processing
        if error.error_id in self._active_errors:
            logger.debug(f"Error {error.error_id} already being processed — skipping.")
            return

        async with self._processing_lock:
            self._active_errors.add(error.error_id)

            try:
                logger.info("─" * 50)
                logger.info(f"ERROR PIPELINE STARTED: {error.error_id}")
                logger.info(f"  Message: {error.error_message}")
                logger.info("─" * 50)

                # Mark error as in-progress
                update_error_status(error.error_id, ErrorStatus.IN_PROGRESS.value)

                # Step 1: Get current snapshot for UI grounding
                snapshot = read_snapshot()

                # Step 2: DiagnosisAgent — retrieve fix and create execution plan
                logger.info("[PHASE 2] DiagnosisAgent analyzing error...")
                plan = await self.diagnosis_agent.diagnose(error, snapshot)

                if not plan.execution_steps:
                    logger.warning(f"No execution steps generated for {error.error_id}")
                    update_error_status(error.error_id, ErrorStatus.FAILED.value)
                    return

                # Step 3: ExecutionAgent — execute the plan
                logger.info("[PHASE 3] ExecutionAgent executing resolution...")
                result: ExecutionResult = await self.execution_agent.execute(
                    plan, self._page
                )

                # Step 4: Log and report
                if result.resolution_status == ResolutionStatus.RESOLVED:
                    logger.info(
                        f"✅ ERROR {error.error_id} RESOLVED SUCCESSFULLY"
                    )
                    logger.info(f"  Steps: {result.steps_completed}/{result.steps_total}")
                else:
                    logger.warning(
                        f"⚠️ ERROR {error.error_id} RESOLUTION FAILED"
                    )
                    logger.warning(f"  Details: {result.details}")

                logger.info("─" * 50)
                logger.info("Returning to monitoring mode...")
                logger.info("─" * 50)

            except Exception as e:
                logger.error(
                    f"Pipeline error for {error.error_id}: {e}",
                    exc_info=True,
                )
                update_error_status(error.error_id, ErrorStatus.FAILED.value)

            finally:
                self._active_errors.discard(error.error_id)

    # ─── Browser Recovery ─────────────────────────────────────────────────

    async def recover_browser(
        self,
        browser: Browser,
        context: BrowserContext,
        login_func,
    ) -> Page | None:
        """
        Attempt to recover from browser crash.
        Re-launches context, re-authenticates, and returns new page.
        """
        logger.warning("Attempting browser crash recovery...")

        try:
            # Stop current agents
            await self.stop()

            # Close old context
            try:
                await context.close()
            except Exception:
                pass

            # Create new context and page
            new_context = await browser.new_context()
            new_page = await new_context.new_page()

            # Re-authenticate
            await login_func(new_page)

            # Restart monitoring
            self.snapshot_agent = SnapshotAgent(self.session_id)
            self.snapshot_agent.set_error_callback(self._on_error_detected)
            await self.start(new_page)

            logger.info("Browser recovery successful!")
            return new_page

        except Exception as e:
            logger.error(f"Browser recovery failed: {e}", exc_info=True)
            return None
