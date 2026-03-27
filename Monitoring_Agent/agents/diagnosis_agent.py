"""
Agent 2 — DiagnosisAgent
RAG-Based Error Understanding.

Responsibilities:
  - Receive structured error payload from SnapshotAgent
  - Perform semantic retrieval against the Knowledge Base via FAISS
  - Parse resolution steps into executable actions
  - Ground NL instructions to CSS selectors using snapshot data
  - Generate ExecutionPlan and forward to ExecutionAgent
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from pathlib import Path

import groq
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from core.config import (
    RAG_KNOWLEDGE_BASE,
    RAG_MODEL_NAME,
    RAG_TOP_K,
    RAG_VECTOR_STORE,
    GROQ_API_KEY,
    GROQ_MODEL,
)
from core.models import (
    ActionType,
    ErrorEntry,
    ExecutionPlan,
    ExecutionStep,
    SiteSnapshot,
)
from core.shared_memory import get_cached_plan, save_to_cache

logger = logging.getLogger("DiagnosisAgent")


class DiagnosisAgent:
    """RAG-powered error diagnosis and LLM-driven execution plan generation."""

    def __init__(self):
        logger.info("Initializing DiagnosisAgent — loading RAG & Gemini components...")
        self._model = SentenceTransformer(RAG_MODEL_NAME, token=False)
        self._kb = self._load_knowledge_base()
        self._index = self._load_vector_store()
        
        # Initialize Groq
        if not GROQ_API_KEY:
            logger.warning("GROQ_API_KEY not found in environment. LLM generation will fail.")
        self._client = groq.Groq(api_key=GROQ_API_KEY)
        self._model_name = GROQ_MODEL
        
        logger.info(f"DiagnosisAgent ready. KB size: {len(self._kb)}, Index size: {self._index.ntotal}")

    #Public API

    async def diagnose(self, error: ErrorEntry, snapshot: SiteSnapshot | None = None) -> ExecutionPlan:
        """
        Main entry point: receive an error, retrieve fix steps via RAG, 
        ground to UI via LLM, and return an executable plan.
        """
        logger.info(f"Diagnosing error: {error.error_id} — '{error.error_message}'")

        # 1. Retrieve the best-match fix from the knowledge base (RAG)
        match = self.retrieve_fix(error.error_message)
        logger.info(f"RAG match: '{match['issue_type']}'")

        # 2. Check Selector Cache for previous grounding
        raw_resolution_steps = match.get("resolution_steps", "")
        cached_steps_data = get_cached_plan(match["issue_type"], error.error_message)
        
        if cached_steps_data:
            logger.info("✓ Using cached execution plan (skipping LLM call)")
            grounded_steps = self._process_cached_steps(cached_steps_data, error)
        else:
            logger.info("Calling Gemini for step grounding...")
            grounded_steps = await self._generate_grounded_steps(
                raw_resolution_steps, snapshot, error
            )
            
            # FALLBACK: If Gemini fails, try to use the cache as a safety net
            if not grounded_steps and cached_steps_data:
                logger.warning("Gemini grounding failed. Falling back to pre-seeded cache.")
                grounded_steps = self._process_cached_steps(cached_steps_data, error)
            
            # Save to cache if successful and not already there
            if grounded_steps and not cached_steps_data:
                save_to_cache(
                    match["issue_type"], 
                    error.error_message, 
                    [s.model_dump() for s in grounded_steps]
                )

        # 3. Build execution plan
        plan = ExecutionPlan(
            error_id=error.error_id,
            error_message=error.error_message,
            execution_steps=grounded_steps,
        )

        logger.info(f"Execution plan created for {error.error_id}: {len(grounded_steps)} steps")
        return plan

    def _process_cached_steps(self, cached_steps_data: list[dict], error: ErrorEntry) -> list[ExecutionStep]:
        """Convert raw cache data into ExecutionStep objects with dynamic values."""
        grounded_steps = []
        for s in cached_steps_data:
            selector = s["selector"].format(error_id=error.error_id) if "{error_id}" in s["selector"] else s["selector"]
            value = s.get("value", "")
            grounded_steps.append(ExecutionStep(
                action=ActionType(s["action"]),
                selector=selector,
                value=str(value),
                description=s.get("description", "")
            ))
        return grounded_steps

    # RAG Retrieval

    def retrieve_fix(self, error_message: str) -> dict:
        """Semantic search against the FAISS index to find the best fix."""
        query_embedding = self._model.encode([error_message])
        query_embedding = np.array(query_embedding, dtype=np.float32)

        distances, indices = self._index.search(query_embedding, RAG_TOP_K)
        best_idx = indices[0][0]

        if 0 <= best_idx < len(self._kb):
            return self._kb[best_idx]

        logger.warning(f"No match found for: {error_message}")
        return {"issue_type": "unknown", "resolution_steps": ""}

    # LLM Grounding
    async def _generate_grounded_steps(
        self, 
        nl_steps: str, 
        snapshot: SiteSnapshot | None, 
        error: ErrorEntry
    ) -> list[ExecutionStep]:
        """
        Calls Gemini to convert NL instructions into structured JSON steps 
        strictly using element IDs from the DOM snapshot.
        """
        if not snapshot or not snapshot.elements:
            logger.warning("No snapshot available for grounding. Returning empty steps.")
            return []

        # Prepare snapshot summary for the LLM — FOCUS ON IDs
        element_summary = []
        for el in snapshot.elements:
            # We provide all info but explicitly ask for ID in the output
            info = {
                "tag": el.tag,
                "id": el.id,
                "selector": el.selector,
                "text": el.text,
                "attributes": el.attributes
            }
            element_summary.append(info)
        
        snapshot_json = json.dumps(element_summary, indent=2)

        prompt = f"""
You are an expert Automation Agent. Your task is to convert high-level resolution steps into a structured JSON execution plan strictly using element IDs.

### Context:
Error Message: {error.error_message}
Reported Extra Data (context): {json.dumps(error.extra_data)}

### Current DOM Snapshot (JSON):
{snapshot_json}

### Desired Resolution Steps (Natural Language):
{nl_steps}

### Instructions:
1. Map each natural language step to concrete UI actions.
2. The 'selector' in your JSON MUST be the '#' followed by the 'id' of the element (e.g., "#email-input"). 
3. If an element has no ID or the ID seems dynamic/temporary, use its stable 'selector' path provided in the snapshot, but ALWAYS prioritize the 'id' field if it exists.
4. Supported Action Types: "click", "fill", "select", "wait", "navigate", "refresh".
5. Use placeholders like "{{error_id}}" in selectors if the ID contains the error ID.
6. Return a JSON array of objects with keys: "action", "selector", "value", "description".

Example Output:
[
  {{ "action": "click", "selector": "#sidebar-link-cart", "value": "", "description": "Open cart" }},
  {{ "action": "fill", "selector": "#email-field", "value": "user@example.com", "description": "Enter email" }}
]
"""

        try:
            logger.info("Calling Groq for step grounding...")
            response = await asyncio.to_thread(
                self._client.chat.completions.create,
                model=self._model_name,
                messages=[
                    {"role": "system", "content": "You are an expert Automation Agent. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            raw_json = response.choices[0].message.content.strip()
            # Clean up potential markdown code blocks if the model ignored instructions
            if "```json" in raw_json:
                raw_json = raw_json.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_json:
                raw_json = raw_json.split("```")[1].split("```")[0].strip()

            steps_data = json.loads(raw_json)
            grounded_steps = []

            for step_dict in steps_data:
                # Replace placeholder error_id in selectors if necessary
                selector = step_dict.get("selector", "")
                if "{error_id}" in selector:
                    selector = selector.format(error_id=error.error_id)
                
                grounded_steps.append(ExecutionStep(
                    action=ActionType(step_dict["action"]),
                    selector=selector,
                    value=str(step_dict.get("value", "")),
                    description=step_dict.get("description", "")
                ))

            logger.info(f"LLM successfully generated {len(grounded_steps)} ID-based grounded steps.")
            return grounded_steps

        except Exception as e:
            logger.error(f"LLM grounding failed: {e}", exc_info=True)
            return []

    # Private Helpers

    def _load_knowledge_base(self) -> list[dict]:
        """Load the JSON knowledge base."""
        try:
            with open(RAG_KNOWLEDGE_BASE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load knowledge base: {e}")
            return []

    def _load_vector_store(self) -> faiss.IndexFlatL2:
        """Load the FAISS vector index."""
        try:
            return faiss.read_index(str(RAG_VECTOR_STORE))
        except Exception as e:
            logger.error(f"Failed to load FAISS index: {e}")
            return faiss.IndexFlatL2(384)
