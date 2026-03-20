"""
Main Entry Point — Agentic Autonomous Website Monitoring System.

Usage:
    python main.py

Flow:
    1. Launch Playwright browser
    2. Navigate to login page
    3. Perform login with configured credentials
    4. Detect successful login (URL redirect + session)
    5. Create session → Start AgentOrchestrator
    6. Monitor continuously until logout/session expiry/SIGINT
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from playwright.async_api import async_playwright, Page, Browser
from core.config import (
    LOGIN_URL,
    LOGIN_EMAIL,
    LOGIN_PASSWORD,
    BROWSER_HEADLESS,
    DATA_DIR,
)
from core.session_manager import SessionManager
from orchestrator import AgentOrchestrator

# ─── Logging Setup ────────────────────────────────────────────────────────────

LOG_FORMAT = (
    "%(asctime)s │ %(levelname)-8s │ %(name)-18s │ %(message)s"
)
LOG_FILE = DATA_DIR / "agent_system.log"


def setup_logging() -> None:
    """Configure logging to both console and file."""
    DATA_DIR.mkdir(exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Console handler (INFO level)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(console_handler)

    # File handler (DEBUG level)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(file_handler)


logger = logging.getLogger("Main")

# ─── Login ────────────────────────────────────────────────────────────────────

async def perform_login(page: Page) -> bool:
    """
    Pause and let the user log in manually.
    Automatically resumes once dashboard.html is reached.
    """
    logger.info(f"Navigating to login page: {LOGIN_URL}")
    await page.goto(LOGIN_URL, wait_until="networkidle")

    logger.info("============================================================")
    logger.info("   ACTION REQUIRED: Please log in manually in the browser.  ")
    logger.info("   The system will resume after you reach the dashboard.    ")
    logger.info("============================================================")

    # Wait for URL to match dashboard
    try:
        # Wait for user to reach dashboard
        await page.wait_for_url("**/dashboard.html", timeout=120000) 
        logger.info("✓ Dashboard detected. Starting monitoring system...")
        return True
    except Exception:
        logger.error("✗ Login wait timed out or failed.")
        return False


async def detect_session(page: Page) -> dict | None:
    """
    Verify session is active after login.
    Reads session data from localStorage.
    """
    try:
        if "dashboard.html" not in page.url:
            return None

        session_data = await page.evaluate("""
            () => {
                const session = localStorage.getItem('session');
                return session ? JSON.parse(session) : null;
            }
        """)
        if session_data:
            logger.info(f"✓ Session detected: {session_data}")
            return session_data
        else:
            logger.warning("No session found in localStorage.")
            return {"user_email": "Unknown User", "session_id": "manual_session"}
    except Exception as e:
        logger.error(f"Failed to read session: {e}")
        return None
        return None


async def detect_logout(page: Page) -> bool:
    """Check if the user has been logged out (navigated away from dashboard)."""
    try:
        current_url = page.url
        return "dashboard" not in current_url.lower()
    except Exception:
        return True


# ─── Main Loop ────────────────────────────────────────────────────────────────

async def main() -> None:
    """Main entry point for the monitoring system."""
    setup_logging()

    logger.info("=" * 60)
    logger.info("  AGENTIC AUTONOMOUS MONITORING SYSTEM")
    logger.info(f"  Started: {datetime.now().isoformat()}")
    logger.info("=" * 60)

    session_manager = SessionManager()
    orchestrator = None

    async with async_playwright() as pw:
        # Launch browser
        logger.info("Launching browser...")
        browser: Browser = await pw.chromium.launch(
            headless=BROWSER_HEADLESS,
            args=["--disable-blink-features=AutomationControlled"],
        )

        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        # ── Login Phase ───────────────────────────────────────────────
        login_success = await perform_login(page)

        if not login_success:
            logger.error("Login failed. Exiting.")
            await browser.close()
            return

        # Verify session
        session_data = await detect_session(page)
        if not session_data:
            logger.error("No valid session detected. Exiting.")
            await browser.close()
            return

        # Create monitoring session
        user_id = session_data.get("email", LOGIN_EMAIL)
        session = session_manager.create_session(user_id)
        logger.info(f"Monitoring session created: {session.session_id}")

        # ── Agent Activation ──────────────────────────────────────────
        orchestrator = AgentOrchestrator(session.session_id)

        # Wait for dashboard to fully load
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(2000)

        # Start the orchestrator
        await orchestrator.start(page)

        # ── Continuous Monitoring ─────────────────────────────────────
        logger.info("Entering continuous monitoring mode. Press Ctrl+C to stop.")

        shutdown_event = asyncio.Event()

        # Handle graceful shutdown
        def signal_handler():
            logger.info("Shutdown signal received.")
            shutdown_event.set()

        # Register signal handlers
        loop = asyncio.get_event_loop()
        try:
            loop.add_signal_handler(signal.SIGINT, signal_handler)
            loop.add_signal_handler(signal.SIGTERM, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler for SIGINT
            pass

        try:
            # Monitor session and detect logout
            while not shutdown_event.is_set():
                try:
                    # Check for logout / session expiry
                    if await detect_logout(page):
                        logger.warning("Session ended — user logged out or session expired.")
                        break

                    # Check page health (browser crash detection)
                    try:
                        await page.evaluate("() => document.readyState")
                    except Exception:
                        logger.warning("Page disconnected — attempting recovery...")
                        new_page = await orchestrator.recover_browser(
                            browser, context, perform_login
                        )
                        if new_page:
                            page = new_page
                        else:
                            logger.error("Browser recovery failed. Exiting.")
                            break

                    await asyncio.sleep(5)

                except asyncio.CancelledError:
                    break
                except KeyboardInterrupt:
                    break

        finally:
            # ── Shutdown ──────────────────────────────────────────────
            logger.info("Initiating graceful shutdown...")

            if orchestrator:
                await orchestrator.stop()

            session_manager.deactivate_session(session.session_id)

            try:
                await context.close()
                await browser.close()
            except Exception:
                pass

            logger.info("=" * 60)
            logger.info("  MONITORING SYSTEM SHUT DOWN")
            logger.info(f"  Time: {datetime.now().isoformat()}")
            logger.info("=" * 60)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown by user.")
