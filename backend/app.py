"""
backend/app.py — FastAPI service for the RTL-to-Diagram agentic pipeline.

Start from the project root:
    uvicorn backend.app:app --reload --port 8000

Endpoints
---------
POST /upload-rtl
    Accepts an RTL source file + optional customization_text.
    Saves the file, runs the full pipeline, persists the SVG, and
    returns { task_id, svg_url }.

POST /regenerate/{task_id}
    Re-styles an existing diagram with new feedback text.
    Skips the expensive Architect/Auditor loop — only Stylist +
    DOT Compiler + Graphviz render are re-executed.
    Returns a new { task_id, svg_url }.

GET /static/output/<task_id>.svg
    Generated diagrams served as static files.
"""

import asyncio
import json
import logging
import shutil
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from orchestrator.orchestrator import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Paths (relative to project root, where uvicorn is launched) ───────────────

_HERE       = Path(__file__).parent                        # backend/
_ROOT       = _HERE.parent                                 # project root
RAW_DIR     = _ROOT / "data" / "raw"
OUTPUT_DIR  = _HERE / "static" / "output"

RAW_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── App & middleware ──────────────────────────────────────────────────────────

app = FastAPI(title="RTL-to-Diagram API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# NOTE: StaticFiles mount is registered at the bottom of this file, after all
# route definitions.  Mounting early can cause Starlette to shadow API routes.

# ── In-memory task store ──────────────────────────────────────────────────────
# Keyed by task_id.  Stores the pipeline state so /regenerate can reuse
# verified_json without repeating the Architect/Auditor loop.

_tasks: dict[str, dict] = {}

ALLOWED_SUFFIXES = {".v", ".sv", ".vh", ".svh"}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _save_svg(task_id: str, svg_text: str) -> str:
    """Persist SVG to disk; return its public URL path."""
    (OUTPUT_DIR / f"{task_id}.svg").write_text(svg_text, encoding="utf-8")
    return f"/static/output/{task_id}.svg"


# ── POST /upload-rtl ──────────────────────────────────────────────────────────

@app.post("/upload-rtl")
async def upload_rtl(
    rtl_file: UploadFile = File(...),
    customization_text: str = Form(""),
):
    """
    1. Validate file extension.
    2. Save the upload to data/raw/ using shutil.
    3. Run the agentic pipeline in a thread (it is synchronous/blocking).
    4. Persist the resulting SVG and return its URL.
    """
    suffix = Path(rtl_file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{suffix}'. "
                f"Accepted: {', '.join(sorted(ALLOWED_SUFFIXES))}"
            ),
        )

    task_id   = str(uuid.uuid4())
    save_path = RAW_DIR / f"{task_id}{suffix}"

    # Use shutil.copyfileobj so the file is streamed to disk without loading
    # the entire contents into memory first.
    with save_path.open("wb") as dest:
        shutil.copyfileobj(rtl_file.file, dest)

    rtl_code = save_path.read_text(encoding="utf-8")

    # run_pipeline is synchronous (LangGraph/LangChain); run it in a thread
    # pool so FastAPI's async event loop is not blocked.
    # The entire block — pipeline execution, svg_output validation, and file
    # persistence — is wrapped so no exception escapes as a bare 500.
    try:
        logger.info("Starting pipeline for task %s", task_id)

        final = await asyncio.to_thread(
            run_pipeline,
            rtl_code,
            customization_text,   # user_style_prompt
            "",                   # user_edit_prompt — empty → should_customize returns "no"
        )

        # Guard: pipeline must return a non-empty SVG string.
        svg_output = final.get("svg_output") if final else None
        if not svg_output:
            raise ValueError(
                "Pipeline completed but returned no SVG output. "
                "Ensure run_pipeline populates state['svg_output'] before returning."
            )

        svg_url = _save_svg(task_id, svg_output)
        logger.info("Task %s complete — diagram saved to %s", task_id, svg_url)

    except HTTPException:
        raise  # already formatted, pass through as-is
    except Exception as exc:
        logger.error(
            "Pipeline failed for task %s:\n%s",
            task_id,
            traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline error: {type(exc).__name__}: {exc}",
        ) from exc

    # Store state for fast regeneration (avoids re-running Architect/Auditor).
    _tasks[task_id] = {
        "rtl_code":           rtl_code,
        "customization_text": customization_text,
        "verified_json":      final["verified_json"],
        "style_map":          final["style_map"],
        "dot_source":         final["dot_source"],
        "svg_url":            svg_url,
    }

    return JSONResponse(
        content={"task_id": task_id, "svg_url": svg_url},
        media_type="application/json",
    )


# ── POST /regenerate/{task_id} ────────────────────────────────────────────────

class RegenerateRequest(BaseModel):
    edit_prompt: str


@app.post("/regenerate/{task_id}")
async def regenerate(task_id: str, body: RegenerateRequest):
    """
    Re-style an existing diagram using the stored verified_json.
    Only Stylist → DOT Compiler → Graphviz render are executed;
    the expensive Architect/Auditor loop is skipped entirely.
    Returns a new { task_id, svg_url }.
    """
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    # These imports are read-only — we never modify files inside agents/.
    from agents.stylist.agent import run_stylist_agent
    from agents.dot_compiler.agent import run_dot_compiler_agent
    from tools.graphviz_quickchart                 import render_dot_to_svg

    verified_json = task["verified_json"]
    edit_prompt   = body.edit_prompt

    def _regen() -> tuple[dict, str, str]:
        style_result = run_stylist_agent(
            architect_json=json.dumps(verified_json, indent=2),
            user_request=edit_prompt,
        )
        dot_source = run_dot_compiler_agent(verified_json, style_result.model_dump())
        svg        = render_dot_to_svg(dot_source)
        return style_result.model_dump(), dot_source, svg

    try:
        logger.info("Regenerating from task %s", task_id)
        style_map, dot_source, svg = await asyncio.to_thread(_regen)

        if not svg:
            raise ValueError("Regeneration produced no SVG output.")

        new_task_id = str(uuid.uuid4())
        svg_url     = _save_svg(new_task_id, svg)
        logger.info("Regeneration complete — new task %s", new_task_id)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Regeneration failed from task %s:\n%s",
            task_id,
            traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Regeneration error: {type(exc).__name__}: {exc}",
        ) from exc

    _tasks[new_task_id] = {**task, "style_map": style_map, "dot_source": dot_source, "svg_url": svg_url}

    return JSONResponse(
        content={"task_id": new_task_id, "svg_url": svg_url},
        media_type="application/json",
    )


# ── Static files (mounted last so API routes are never shadowed) ──────────────
# Serves backend/static/ at /static → diagrams at /static/output/<id>.svg
app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")
