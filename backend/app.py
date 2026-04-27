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
import logging
import shutil
import tempfile
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from orchestrator.orchestrator import cleanup_session_output, run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Paths (relative to project root, where uvicorn is launched) ───────────────

_HERE = Path(__file__).parent  # backend/
_ROOT = _HERE.parent  # project root

# Runtime artifacts should live outside the repo so uvicorn --reload does not
# restart the server while handling uploads/regenerations.
_RUNTIME_DIR = Path(tempfile.gettempdir()) / "agentic_converter_runtime"
RAW_DIR = _RUNTIME_DIR / "raw"
OUTPUT_DIR = _RUNTIME_DIR / "output"

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


def _merge_style_intent(previous: str, new_edit: str) -> str:
    """
    Build a cumulative style prompt from previous intent + latest edit.
    Latest instruction should win only when it conflicts with older ones.
    """
    prev = (previous or "").strip()
    edit = (new_edit or "").strip()
    if not edit:
        return prev
    if not prev:
        return edit

    return (
        "Apply these styling instructions cumulatively.\n"
        "Keep earlier constraints unless a newer instruction explicitly conflicts.\n\n"
        f"Existing style intent:\n{prev}\n\n"
        f"Latest user edit:\n{edit}"
    )


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
    session_output_dir = None
    try:
        logger.info("Starting pipeline for task %s", task_id)

        final = await asyncio.to_thread(
            run_pipeline,
            rtl_code,
            customization_text,   # user_style_prompt
            "",                   # user_edit_prompt — empty → should_customize returns "no"
        )
        session_output_dir = final.get("session_output_dir")

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
    finally:
        if session_output_dir:
            try:
                cleanup_session_output(session_output_dir)
            except Exception as cleanup_error:
                logger.warning(
                    "Failed to cleanup session output %s: %s",
                    session_output_dir,
                    cleanup_error,
                )

    # Store state for subsequent regenerations.
    _tasks[task_id] = {
        "rtl_code": rtl_code,
        "customization_text": customization_text,
        "cumulative_style_prompt": (customization_text or "").strip(),
        "verified_json": final["verified_json"],
        "style_map": final["style_map"],
        "dot_source": final["dot_source"],
        "svg_url": svg_url,
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
    Re-run the full orchestrator for an existing RTL input, including
    the Architect/Auditor loop. The latest edit is merged into a cumulative
    style prompt so prior edits are preserved unless explicitly overridden.
    Returns a new { task_id, svg_url }.
    """
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    rtl_code = task["rtl_code"]
    cumulative_style_prompt = task.get("cumulative_style_prompt")
    if cumulative_style_prompt is None:
        cumulative_style_prompt = task.get("customization_text", "")
    edit_prompt = body.edit_prompt
    merged_style_prompt = _merge_style_intent(cumulative_style_prompt, edit_prompt)

    session_output_dir = None
    try:
        logger.info("Regenerating from task %s", task_id)
        final = await asyncio.to_thread(
            run_pipeline,
            rtl_code,
            merged_style_prompt,
            "",
        )
        session_output_dir = final.get("session_output_dir")
        style_map = final.get("style_map")
        dot_source = final.get("dot_source")
        svg = final.get("svg_output")

        if not svg or not style_map or not dot_source:
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
    finally:
        if session_output_dir:
            try:
                cleanup_session_output(session_output_dir)
            except Exception as cleanup_error:
                logger.warning(
                    "Failed to cleanup session output %s: %s",
                    session_output_dir,
                    cleanup_error,
                )

    _tasks[new_task_id] = {
        **task,
        "cumulative_style_prompt": merged_style_prompt,
        "style_map": style_map,
        "dot_source": dot_source,
        "svg_url": svg_url,
    }

    return JSONResponse(
        content={"task_id": new_task_id, "svg_url": svg_url},
        media_type="application/json",
    )


@app.get("/task/{task_id}/dot")
async def get_task_dot(task_id: str):
    """
    Return DOT source for a task so the interactive viewer can render/collapse
    clusters client-side.
    """
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    dot_source = task.get("dot_source")
    if not dot_source:
        raise HTTPException(status_code=404, detail="DOT source not found for task.")

    return JSONResponse(
        content={"task_id": task_id, "dot_source": dot_source},
        media_type="application/json",
    )


# ── Static files (mounted last so API routes are never shadowed) ──────────────
# Serves runtime output at /static/output/<id>.svg
app.mount("/static", StaticFiles(directory=str(_RUNTIME_DIR)), name="static")
