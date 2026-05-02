"""
Upload canonical pipeline artifacts to S3 under:

    users/{user_id}/projects/{project_id}/runs/{run_id}/

Objects:
    metadata.json
    rtl/input.sv
    structured/input_structure.json
    style/input_style.json
    dot/input.dot
    diagram/input.svg

Enable by setting S3_ARTIFACTS_BUCKET. On EC2, grant the instance role s3:PutObject
on that bucket (and optionally a prefix condition). Optional S3_ARTIFACTS_USER_ID /
S3_ARTIFACTS_PROJECT_ID default to anonymous / default.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Canonical artifact stem under each run prefix (shared across rtl / structured / …).
_ARTIFACT_STEM = "input"


def _sanitize_path_component(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", (label or "").strip())
    return cleaned or "unknown"


@dataclass(frozen=True)
class S3ArtifactConfig:
    bucket: str
    user_id: str
    project_id: str


def load_s3_artifact_config() -> Optional[S3ArtifactConfig]:
    bucket = (os.environ.get("S3_ARTIFACTS_BUCKET") or "").strip()
    if not bucket:
        return None
    user_id = (os.environ.get("S3_ARTIFACTS_USER_ID") or "anonymous").strip() or "anonymous"
    project_id = (os.environ.get("S3_ARTIFACTS_PROJECT_ID") or "default").strip() or "default"
    return S3ArtifactConfig(
        bucket=bucket,
        user_id=_sanitize_path_component(user_id),
        project_id=_sanitize_path_component(project_id),
    )


def _run_prefix(cfg: S3ArtifactConfig, run_id: str) -> str:
    rid = _sanitize_path_component(run_id)
    return (
        f"users/{cfg.user_id}/projects/{cfg.project_id}/runs/{rid}/"
    )


def upload_run_artifacts_to_s3(
    cfg: S3ArtifactConfig,
    run_id: str,
    *,
    rtl_code: str,
    verified_json: dict[str, Any],
    style_map: dict[str, Any],
    dot_source: str,
    svg_output: str,
) -> dict[str, str]:
    """
    Upload six objects; return map of logical name -> S3 key (no bucket).
    Raises on boto3 / permission errors.
    """
    import boto3

    stem = _ARTIFACT_STEM
    prefix = _run_prefix(cfg, run_id)
    created_at = datetime.now(timezone.utc).isoformat()

    structured_body = json.dumps(verified_json, indent=2)
    style_body = json.dumps(style_map, indent=2)

    keys = {
        "metadata": f"{prefix}metadata.json",
        "rtl": f"{prefix}rtl/{stem}.sv",
        "structured": f"{prefix}structured/{stem}_structure.json",
        "style": f"{prefix}style/{stem}_style.json",
        "dot": f"{prefix}dot/{stem}.dot",
        "diagram": f"{prefix}diagram/{stem}.svg",
    }

    metadata = {
        "user_id": cfg.user_id,
        "project_id": cfg.project_id,
        "run_id": _sanitize_path_component(run_id),
        "created_at": created_at,
        "artifacts": {k: keys[k] for k in keys},
    }
    metadata_body = json.dumps(metadata, indent=2)

    client = boto3.client("s3")
    uploads: list[tuple[str, bytes, str]] = [
        (keys["metadata"], metadata_body.encode("utf-8"), "application/json"),
        (keys["rtl"], rtl_code.encode("utf-8"), "text/plain; charset=utf-8"),
        (keys["structured"], structured_body.encode("utf-8"), "application/json"),
        (keys["style"], style_body.encode("utf-8"), "application/json"),
        (keys["dot"], (dot_source or "").encode("utf-8"), "text/plain; charset=utf-8"),
        (keys["diagram"], (svg_output or "").encode("utf-8"), "image/svg+xml"),
    ]
    for key, body, content_type in uploads:
        client.put_object(
            Bucket=cfg.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
        logger.info("S3 artifact written s3://%s/%s", cfg.bucket, key)

    return keys
