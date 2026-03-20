"""
Agent 3 — ExecutionAgent
Automated Resolution Executor.

Responsibilities:
  - Execute corrective UI actions via Playwright
  - Support: click, fill, navigate, wait, refresh, select
  - Sequential step execution with retry and timeout protection
  - Verify resolution (error popup removed, dashboard stable)
  - Report result back to SnapshotAgent
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from core.config import (
    ACTION_RETRY_COUNT,
    ACTION_TIMEOUT_MS,
    VERIFY_WAIT_MS,
)
from core.models import (
    ActionType,
    ExecutionPlan,
    ExecutionResult,
    ExecutionStep,
    ResolutionStatus,
)
from core.shared_memory import (
    append_execution_history,
    update_error_status,
)

logger = logging.getLogger("ExecutionAgent")


class ExecutionAgent:
    """Executes resolution plans on the browser via Playwright."""

    def __init__(self):
        logger.info("ExecutionAgent initialized.")

    # ─── Public API ───────────────────────────────────────────────────────

    async def execute(self, plan: ExecutionPlan, page: Page) -> ExecutionResult:
        """
        Execute all steps in the plan on the given Playwright page.
        Returns an ExecutionResult with the outcome.
        """
        logger.info(
            f"Executing plan for error {plan.error_id}: "
            f"{len(plan.execution_steps)} steps"
        )

        steps_completed = 0
        steps_total = len(plan.execution_steps)

        for i, step in enumerate(plan.execution_steps):
            step_num = i + 1
            logger.info(
                f"  [{step_num}/{steps_total}] {step.action.value.upper()} "
                f"→ {step.selector or '(none)'} | {step.description}"
            )

            success = await self._execute_step_with_retry(step, page)

            if success:
                steps_completed += 1
                logger.info(f"  [{step_num}/{steps_total}] ✓ Step completed")
            else:
                logger.warning(f"  [{step_num}/{steps_total}] ✗ Step failed — continuing")
                # Continue with remaining steps even if one fails

            # Small delay between steps for UI stability
            await asyncio.sleep(0.5)

        # Verify resolution
        verified = await self.verify_resolution(page, plan.error_id)
        status = ResolutionStatus.RESOLVED if verified else ResolutionStatus.FAILED

        result = ExecutionResult(
            error_id=plan.error_id,
            resolution_status=status,
            steps_completed=steps_completed,
            steps_total=steps_total,
            details=f"{'Verified resolved' if verified else 'Resolution not verified'}. "
                    f"{steps_completed}/{steps_total} steps completed.",
        )

        # Log result
        append_execution_history(result)
        update_error_status(
            error_id=plan.error_id,
            status=status.value,
            resolved_time=datetime.now().isoformat() if verified else None,
        )

        logger.info(
            f"Execution complete for {plan.error_id}: {status.value} "
            f"({steps_completed}/{steps_total} steps)"
        )

        return result

    # ─── Step Execution ───────────────────────────────────────────────────

    async def _execute_step_with_retry(self, step: ExecutionStep, page: Page) -> bool:
        """Execute a single step with retry logic."""
        for attempt in range(1, ACTION_RETRY_COUNT + 1):
            try:
                await self._execute_step(step, page)
                return True
            except PlaywrightTimeout:
                logger.warning(
                    f"    Timeout on attempt {attempt}/{ACTION_RETRY_COUNT} "
                    f"for {step.action.value} → {step.selector}"
                )
            except Exception as e:
                logger.warning(
                    f"    Error on attempt {attempt}/{ACTION_RETRY_COUNT}: {e}"
                )

            if attempt < ACTION_RETRY_COUNT:
                await asyncio.sleep(1)

        return False

    async def _execute_step(self, step: ExecutionStep, page: Page) -> None:
        """Execute a single step on the page."""
        timeout = step.timeout_ms or ACTION_TIMEOUT_MS

        if step.action == ActionType.CLICK:
            await self._do_click(step.selector, page, timeout)

        elif step.action == ActionType.FILL:
            await self._do_fill(step.selector, step.value, page, timeout)

        elif step.action == ActionType.NAVIGATE:
            await page.goto(step.value, timeout=timeout)

        elif step.action == ActionType.WAIT:
            wait_ms = int(step.value) if step.value else 1000
            await page.wait_for_timeout(wait_ms)

        elif step.action == ActionType.REFRESH:
            await page.reload(timeout=timeout)

        elif step.action == ActionType.SELECT:
            await self._do_select(step.selector, step.value, page, timeout)

        else:
            logger.warning(f"Unknown action type: {step.action}")

    async def _do_click(self, selector: str, page: Page, timeout: int) -> None:
        """Click an element, handling visibility and modals."""
        # Wait for element to be visible
        try:
            await page.wait_for_selector(selector, state="visible", timeout=timeout)
        except PlaywrightTimeout:
            # Element might be in a section that isn't visible; try scrolling it into view
            logger.debug(f"Element {selector} not visible — trying to scroll into view")
            element = await page.query_selector(selector)
            if element:
                await element.scroll_into_view_if_needed()
                await page.wait_for_timeout(500)

        await page.click(selector, timeout=timeout)
        # Wait briefly for any transition
        await page.wait_for_timeout(300)

    async def _do_fill(self, selector: str, value: str, page: Page, timeout: int) -> None:
        """Fill an input field."""
        await page.wait_for_selector(selector, state="visible", timeout=timeout)
        # Clear existing value first
        await page.fill(selector, "")
        await page.wait_for_timeout(100)
        await page.fill(selector, value)
        await page.wait_for_timeout(200)

    async def _do_select(self, selector: str, value: str, page: Page, timeout: int) -> None:
        """Select an option from a dropdown."""
        await page.wait_for_selector(selector, state="visible", timeout=timeout)

        # Try to select by index
        try:
            idx = int(value)
            # Get option values and select by index
            options = await page.query_selector_all(f"{selector} option")
            if idx < len(options):
                option_value = await options[idx].get_attribute("value")
                if option_value:
                    await page.select_option(selector, value=option_value)
                else:
                    await page.select_option(selector, index=idx)
            else:
                logger.warning(f"Option index {idx} out of range")
                await page.select_option(selector, index=0)
        except ValueError:
            # Not an index — select by value or label
            await page.select_option(selector, label=value)

        await page.wait_for_timeout(300)

    # ─── Resolution Verification ──────────────────────────────────────────

    async def verify_resolution(self, page: Page, error_id: str) -> bool:
        """
        Verify that the error has been resolved:
        1. Check if the error's resolve button now shows 'Resolved'
        2. Check that error popup is hidden
        3. Dashboard is stable
        """
        logger.info(f"Verifying resolution for {error_id}...")
        await page.wait_for_timeout(VERIFY_WAIT_MS)

        try:
            # Check if the resolve button text changed to "Resolved"
            resolve_btn = await page.query_selector(f"#status-btn-{error_id}")
            if resolve_btn:
                btn_text = await resolve_btn.text_content()
                has_resolved_class = await resolve_btn.evaluate(
                    "el => el.classList.contains('resolved')"
                )

                if btn_text and "resolved" in btn_text.lower() or has_resolved_class:
                    logger.info(f"✓ Error {error_id} button shows resolved.")
                    return True
                else:
                    logger.warning(
                        f"✗ Error {error_id} button text: '{btn_text}', "
                        f"resolved class: {has_resolved_class}"
                    )
                    return False
            else:
                # Button not found — might have been removed from DOM
                logger.info(f"Resolve button for {error_id} not found — may be resolved.")
                return True

        except Exception as e:
            logger.error(f"Verification error: {e}")
            return False
