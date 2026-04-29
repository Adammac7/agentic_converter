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
import tempfile
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from orchestrator.orchestrator import (
    cleanup_session_output,
    run_pipeline,
    run_regeneration_pipeline,
)

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


# ── Background pipeline runner ────────────────────────────────────────────────
#
# Spawned by upload_rtl via asyncio.create_task so the POST handler can return
# task_id immediately.  Progress strings are pushed into an asyncio.Queue that
# the /progress SSE endpoint drains.  call_soon_threadsafe is required because
# run_pipeline (and therefore every _emit call) executes inside a thread-pool
# worker, not the event loop thread.

async def _run_pipeline_background(
    task_id: str,
    rtl_code: str,
    customization_text: str,
) -> None:
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = _tasks[task_id]["progress_queue"]

    def progress_callback(msg: str) -> None:
        loop.call_soon_threadsafe(q.put_nowait, {"type": "progress", "message": msg})

    session_output_dir = None
    try:
        logger.info("Starting background pipeline for task %s", task_id)
        final = await asyncio.to_thread(
            run_pipeline,
            rtl_code,
            customization_text,  # user_style_prompt
            "",                  # user_edit_prompt — empty → should_customize returns "no"
            progress_callback=progress_callback,
        )
        session_output_dir = final.get("session_output_dir")

        svg_output = final.get("svg_output")
        if not svg_output:
            raise ValueError("Pipeline completed but returned no SVG output.")

        svg_url = _save_svg(task_id, svg_output)
        logger.info("Task %s complete — diagram saved to %s", task_id, svg_url)

        _tasks[task_id].update({
            "status": "done",
            "svg_url": svg_url,
            "cumulative_style_prompt": (customization_text or "").strip(),
            "verified_json": final["verified_json"],
            "style_map": final["style_map"],
            "dot_source": final["dot_source"],
        })
        loop.call_soon_threadsafe(
            q.put_nowait, {"type": "done", "svg_url": svg_url}
        )

    except Exception as exc:
        logger.error("Pipeline failed for task %s:\n%s", task_id, traceback.format_exc())
        _tasks[task_id].update({"status": "error", "error": str(exc)})
        loop.call_soon_threadsafe(
            q.put_nowait, {"type": "pipeline_error", "message": str(exc)}
        )

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


# ── POST /upload-rtl ──────────────────────────────────────────────────────────

@app.post("/upload-rtl")
async def upload_rtl(
    rtl_file: UploadFile = File(...),
    customization_text: str = Form(""),
):
    """
    1. Validate file extension.
    2. Save the upload to raw/ and read its text.
    3. Register the task in _tasks with an asyncio.Queue for progress events.
    4. Spawn _run_pipeline_background as a fire-and-forget asyncio task.
    5. Return {task_id} immediately — the client polls /progress/{task_id} for updates.
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

    with save_path.open("wb") as dest:
        shutil.copyfileobj(rtl_file.file, dest)

    rtl_code = save_path.read_text(encoding="utf-8")

    # Register the task before spawning the background coroutine so that the
    # /progress endpoint can always find it, even if the client connects before
    # the first _emit fires.
    _tasks[task_id] = {
        "status": "running",
        "progress_queue": asyncio.Queue(),
        "rtl_code": rtl_code,
        "customization_text": customization_text,
        "cumulative_style_prompt": None,
        "verified_json": None,
        "style_map": None,
        "dot_source": None,
        "svg_url": None,
        "error": None,
    }

    asyncio.create_task(_run_pipeline_background(task_id, rtl_code, customization_text))

    return JSONResponse(
        content={"task_id": task_id},
        media_type="application/json",
    )


# ── GET /progress/{task_id} ───────────────────────────────────────────────────

@app.get("/progress/{task_id}")
async def progress_stream(task_id: str):
    """
    Server-Sent Events stream for pipeline progress.

    Yields plain `data:` lines for each progress message, then a terminal
    named event — either `event: done` (with svg_url) or `event: pipeline_error`
    (with message) — and closes.

    If the pipeline already finished before the client connects, the terminal
    event is sent immediately from the cached task status.
    """
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    async def event_generator():
        # Handle the case where the client connects after the pipeline finished.
        if task["status"] == "done":
            yield f"event: done\ndata: {json.dumps({'svg_url': task['svg_url']})}\n\n"
            return
        if task["status"] == "error":
            yield f"event: pipeline_error\ndata: {json.dumps({'message': task['error']})}\n\n"
            return

        q: asyncio.Queue = task["progress_queue"]
        while True:
            item = await q.get()
            if item["type"] == "progress":
                # Plain `data:` line — picked up by EventSource.onmessage.
                yield f"data: {item['message']}\n\n"
            elif item["type"] == "done":
                yield f"event: done\ndata: {json.dumps({'svg_url': item['svg_url']})}\n\n"
                break
            elif item["type"] == "pipeline_error":
                yield f"event: pipeline_error\ndata: {json.dumps({'message': item['message']})}\n\n"
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # prevents nginx from buffering the stream
            "Connection": "keep-alive",
        },
    )


# ── POST /regenerate/{task_id} ────────────────────────────────────────────────

class RegenerateRequest(BaseModel):
    edit_prompt: str


@app.post("/regenerate/{task_id}")
async def regenerate(task_id: str, body: RegenerateRequest):
    """
    Re-style an existing diagram from stored verified_json.
    Skips Architect/Auditor and only runs style->DOT->SVG.
    The latest edit is merged into a cumulative style prompt so prior edits
    are preserved unless explicitly overridden.
    Returns a new { task_id, svg_url }.
    """
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    verified_json = task.get("verified_json")
    if not verified_json:
        raise HTTPException(status_code=500, detail="Task is missing verified_json.")

    cumulative_style_prompt = task.get("cumulative_style_prompt")
    if cumulative_style_prompt is None:
        cumulative_style_prompt = task.get("customization_text", "")
    edit_prompt = body.edit_prompt
    merged_style_prompt = _merge_style_intent(cumulative_style_prompt, edit_prompt)

    session_output_dir = None
    try:
        logger.info("Regenerating from task %s", task_id)
        final = await asyncio.to_thread(
            run_regeneration_pipeline,
            verified_json,
            merged_style_prompt,
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
