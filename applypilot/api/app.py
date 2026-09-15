"""FastAPI application for local profile parsing and form planning."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from applypilot.api.contracts import (
    FormPlanRequest,
    FormPlanResponse,
    FeedbackRequest,
    FeedbackResponse,
    ParseRequest,
    ParseResponse,
    ReconcileRequest,
    ReconcileResponse,
)
from applypilot.api.mapping import build_form_plan
from applypilot.api.service import profile_facts, reconcile_profiles
from applypilot.modules.profile.ingestion import ResumeIngestionError, ResumeIngestionService

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_TEXT_CHARS = 1_000_000


def _check_token(request: Request) -> None:
    expected = os.getenv("APPLYPILOT_API_TOKEN")
    if not expected:
        return
    authorization = request.headers.get("authorization", "")
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid API token")


def create_app() -> FastAPI:
    app = FastAPI(title="ApplyPilot Local API", version="0.1.0", docs_url="/docs", redoc_url=None)
    allowed_origins = os.getenv("APPLYPILOT_API_ALLOWED_ORIGINS", "")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin for origin in allowed_origins.split(",") if origin] or [],
        allow_origin_regex=r"chrome-extension://.*|http://localhost(:\d+)?|http://127\.0\.0\.1(:\d+)?",
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )

    @app.get("/healthz", dependencies=[Depends(_check_token)])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "applypilot-api", "version": app.version}

    @app.post("/v1/forms/plan", response_model=FormPlanResponse, dependencies=[Depends(_check_token)])
    async def form_plan(payload: FormPlanRequest) -> FormPlanResponse:
        return build_form_plan(payload)

    @app.post("/v1/profiles/reconcile", response_model=ReconcileResponse, dependencies=[Depends(_check_token)])
    async def reconcile(payload: ReconcileRequest) -> ReconcileResponse:
        profile, conflicts = reconcile_profiles(payload.base_profile, payload.incoming_profile)
        return ReconcileResponse(request_id=f"req_{uuid.uuid4().hex[:16]}", profile=profile, conflicts=conflicts)

    @app.post("/v1/forms/feedback", response_model=FeedbackResponse, dependencies=[Depends(_check_token)])
    async def form_feedback(payload: FeedbackRequest) -> FeedbackResponse:
        if payload.corrected_profile_path.startswith(("/", "profile.")) is False:
            raise HTTPException(status_code=422, detail="corrected_profile_path must be a profile path")
        return FeedbackResponse(accepted=True, message="已接收脱敏纠错规则；当前服务不会持久化原始页面或字段值")

    @app.post("/v1/profiles/parse", response_model=ParseResponse, dependencies=[Depends(_check_token)])
    async def parse_profile(request: Request) -> ParseResponse:
        content_type = request.headers.get("content-type", "").lower()
        source_name = "resume"
        base_profile = None
        text = ""
        temporary_path: Path | None = None
        try:
            if "multipart/form-data" in content_type:
                form = await request.form()
                source_name = str(form.get("source_name") or "resume")
                text = str(form.get("text") or "")
                base_value = form.get("base_profile")
                if base_value:
                    from applypilot.domain.profile import CandidateProfile

                    base_profile = CandidateProfile.model_validate(json.loads(str(base_value)))
                upload = form.get("file")
                if isinstance(upload, UploadFile) or (upload is not None and hasattr(upload, "read") and hasattr(upload, "filename")):
                    data = await upload.read(MAX_UPLOAD_BYTES + 1)
                    if len(data) > MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail="Resume file exceeds 50 MB")
                    suffix = Path(upload.filename or "resume.pdf").suffix or ".pdf"
                    with tempfile.NamedTemporaryFile(prefix="applypilot-resume-", suffix=suffix, delete=False) as handle:
                        handle.write(data)
                        temporary_path = Path(handle.name)
                    source_name = upload.filename or source_name
            else:
                payload = ParseRequest.model_validate(await request.json())
                text = payload.text or ""
                source_name = payload.source_name
                base_profile = payload.base_profile
            if len(text) > MAX_TEXT_CHARS:
                raise HTTPException(status_code=413, detail="Resume text exceeds 1,000,000 characters")
            service = ResumeIngestionService()
            try:
                profile = await service.parse_file(temporary_path) if temporary_path else await service.parse_text(text)
            except ResumeIngestionError as error:
                status = 503 if "API key" in str(error) or "request failed" in str(error) else 422
                raise HTTPException(status_code=status, detail=str(error)) from error
            conflicts = []
            if base_profile is not None:
                profile, conflicts = reconcile_profiles(base_profile, profile)
            warnings = ["未在原文中定位到的值需要人工核验"] if any(fact.needs_review for fact in profile_facts(profile, source_name, text)) else []
            return ParseResponse(request_id=f"req_{uuid.uuid4().hex[:16]}", profile_draft=profile, facts=profile_facts(profile, source_name, text), conflicts=conflicts, warnings=warnings)
        finally:
            if temporary_path:
                temporary_path.unlink(missing_ok=True)

    return app


app = create_app()
