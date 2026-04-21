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
import os
import shutil
import traceback
import uuid
from pathlib import Path

from typing import Optional

import psycopg
from dotenv import load_dotenv

load_dotenv()  # populate SUPABASE_DB_URL / GOOGLE_* / SECRET_KEY before any import that reads them

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from backend.auth import get_current_user, router as auth_router
from orchestrator.orchestrator import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Paths (relative to project root, where uvicorn is launched) ───────────────

_HERE       = Path(__file__).parent                        # backend/
_ROOT       = _HERE.parent                                 # project root
RAW_DIR     = _ROOT / "agents" / "converter_agent" / "data" / "raw"
OUTPUT_DIR  = _HERE / "static" / "output"

RAW_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── App & middleware ──────────────────────────────────────────────────────────

app = FastAPI(title="RTL-to-Diagram API", version="1.0.0")

# SessionMiddleware must precede routes. Signed-cookie store keyed by SECRET_KEY.
# CORS comes first so preflights from the SPA don't go through session logic.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SECRET_KEY"],
    same_site="lax",
    https_only=False,  # set True in prod behind HTTPS
)

app.include_router(auth_router)

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


def _record_session(session_id: str, user_id: str, svg_output: str, notes: str) -> None:
    """Upsert a sessions row: ownership + current SVG + current editable notes."""
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sessions (id, user_id, svg_output, notes, created_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (id) DO UPDATE
                   SET svg_output = EXCLUDED.svg_output,
                       notes      = EXCLUDED.notes;
                """,
                (session_id, user_id, svg_output, notes),
            )


def _fetch_session_notes(session_id: str, user_id: str) -> Optional[str]:
    """Return notes for a session iff the current user owns it; else None."""
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT notes FROM sessions WHERE id = %s AND user_id = %s;",
                (session_id, user_id),
            )
            row = cur.fetchone()
            return row[0] if row else None


def _record_prompt(session_id: str, prompt_type: str, content: str) -> None:
    """Log one prompt row; human-readable mirror of the checkpointed prompt_history."""
    if not content:
        return
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO prompts (session_id, type, content, created_at) VALUES (%s, %s, %s, NOW());",
                (session_id, prompt_type, content),
            )


# ── POST /upload-rtl ──────────────────────────────────────────────────────────

@app.post("/upload-rtl")
async def upload_rtl(
    rtl_file: UploadFile = File(...),
    customization_text: str = Form(""),
    user: dict = Depends(get_current_user),
):
    """
    1. Validate file extension.
    2. Save the upload to agents/converter_agent/data/raw/ using shutil.
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

        # task_id doubles as the LangGraph thread_id so state (including the
        # accumulated prompt history) is persisted to Supabase via
        # PostgresSaver and can be resumed on subsequent /regenerate calls.
        final = await asyncio.to_thread(
            run_pipeline,
            rtl_code,
            customization_text,   # user_style_prompt
            "",                   # user_edit_prompt — empty on fresh run
            task_id,              # thread_id
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

    # session_id = task_id = LangGraph thread_id. Owner is baked into the
    # `sessions` row so /regenerate can enforce it, and the raw prompt is
    # logged to `prompts` for human-readable display alongside the opaque
    # LangGraph checkpoint state.
    _record_session(task_id, user["id"], svg_output, customization_text)
    _record_prompt(task_id, "style", customization_text)

    _tasks[task_id] = {
        "session_id":         task_id,
        "user_id":             user["id"],
        "rtl_code":           rtl_code,
        "customization_text": customization_text,
        "verified_json":      final["verified_json"],
        "style_map":          final["style_map"],
        "dot_source":         final["dot_source"],
        "svg_url":            svg_url,
        "prompt_history":     final.get("prompt_history", []),
    }

    return JSONResponse(
        content={"task_id": task_id, "session_id": task_id, "svg_url": svg_url},
        media_type="application/json",
    )


# ── POST /regenerate/{task_id} ────────────────────────────────────────────────

class RegenerateRequest(BaseModel):
    edit_prompt: str


@app.post("/regenerate/{task_id}")
async def regenerate(
    task_id: str,
    body: RegenerateRequest,
    user: dict = Depends(get_current_user),
):
    """
    Re-style an existing diagram by resuming the LangGraph thread.

    The graph's conditional entry point routes directly to `update_dot`
    (skipping Architect/Auditor) when `verified_json` is present in the
    checkpointed state. The prompt history accumulates on the original
    session_id so the Stylist sees every prior request.
    Returns a new { task_id, svg_url }.
    """
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task.get("user_id") != user["id"]:
        # 404 (not 403) so we don't leak that the task exists under another owner.
        raise HTTPException(status_code=404, detail="Task not found.")

    session_id  = task["session_id"]
    edit_prompt = body.edit_prompt

    try:
        logger.info("Regenerating on session %s (from task %s)", session_id, task_id)

        final = await asyncio.to_thread(
            run_pipeline,
            task["rtl_code"],
            task["customization_text"],  # ignored when resuming; kept for API shape
            edit_prompt,                  # user_edit_prompt → routes through update_dot
            session_id,                   # thread_id — resume from checkpoint
        )

        svg = final.get("svg_output") if final else None
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

    _record_session(session_id, user["id"], svg, edit_prompt)
    _record_prompt(session_id, "edit", edit_prompt)

    _tasks[new_task_id] = {
        **task,
        "style_map":      final["style_map"],
        "dot_source":     final["dot_source"],
        "svg_url":        svg_url,
        "prompt_history": final.get("prompt_history", task.get("prompt_history", [])),
    }

    return JSONResponse(
        content={"task_id": new_task_id, "session_id": session_id, "svg_url": svg_url},
        media_type="application/json",
    )


# ── GET /session/{session_id}/notes ───────────────────────────────────────────

@app.get("/session/{session_id}/notes")
async def get_session_notes(session_id: str, user: dict = Depends(get_current_user)):
    """Return the persisted editable customization notes for a thread.

    404s if the session does not exist, or if the caller does not own it,
    so one user cannot probe for another user's session ids.
    """
    notes = _fetch_session_notes(session_id, user["id"])
    if notes is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"session_id": session_id, "notes": notes}


# ── Static files (mounted last so API routes are never shadowed) ──────────────
# Serves backend/static/ at /static → diagrams at /static/output/<id>.svg
app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")
