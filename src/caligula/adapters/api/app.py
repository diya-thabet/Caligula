"""HTTP API over the case service, for the web interface.

Reads return the JSON views of `presenters/case_views.py`; writes are the
case's checkpoints (open, approve the plan, pause, stop, decide a scope,
sign off). Live progress streams as server-sent events. Who acts is taken
from the `X-Caligula-User` header and written to the ledger with the act;
it is an identity, not yet an authentication (see docs/api.md).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Annotated
from urllib.parse import unquote

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from caligula.adapters.presenters import case_views as views
from caligula.adapters.presenters.markdown_report import build_report
from caligula.application.cases.events import Event
from caligula.application.cases.service import Case, CaseError, CaseService, NotFound
from caligula.application.investigation.plan import PlannedTask
from caligula.application.investigation.workspace import Mode

USER_HEADER = "X-Caligula-User"


class OpenCase(BaseModel):
    claim: str = Field(min_length=1)
    mode: Mode = Mode.INVESTIGATE
    poc: bool = True
    case_id: str | None = None


class PlanEdit(BaseModel):
    tasks: list[PlannedTask]


class Decision(BaseModel):
    note: str = ""


class ScopeDecision(BaseModel):
    approve: bool
    note: str = ""


def _user(x_caligula_user: Annotated[str | None, Header()] = None) -> str:
    """Who acts. Headers are ASCII, so names are sent URL-encoded as UTF-8 ("Ma%C3%AEtre ...")."""
    name = unquote(x_caligula_user or "").strip()
    if not name:
        raise HTTPException(401, f"say who acts: the {USER_HEADER} header is required for this action")
    return name


User = Annotated[str, Depends(_user)]


def _event(event: Event) -> dict:
    return {"seq": event.seq, "at": event.at.isoformat(), "kind": event.kind, "data": event.data}


def _sse(event: Event) -> str:
    data = json.dumps(_event(event), ensure_ascii=False, default=str)
    return f"id: {event.seq}\nevent: {event.kind}\ndata: {data}\n\n"


def create_app(service: CaseService, cors_origins: list[str] | None = None, heartbeat: float = 15.0) -> FastAPI:
    app = FastAPI(title="Caligula", version="0.1.0",
                  description="Cases, their evidence and their checkpoints, for the investigation interface.")
    if cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_methods=["*"],
                           allow_headers=["*"], expose_headers=["*"])

    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(CaseError)
    async def conflict(_: Request, exc: CaseError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    def case(case_id: str) -> Case:
        return service.get(case_id)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "can_investigate": service.engine is not None, "cases": len(service.cases)}

    # --- cases ----------------------------------------------------------------------

    @app.get("/api/cases")
    def list_cases() -> list[dict]:
        return [views.overview(c) for c in service.list()]

    @app.post("/api/cases", status_code=202)
    def open_case(body: OpenCase, user: User) -> dict:
        return views.overview(service.open(body.claim, by=user, mode=body.mode, poc=body.poc, case_id=body.case_id))

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str) -> dict:
        return views.overview(case(case_id))

    @app.get("/api/approvals")
    def approvals() -> list[dict]:
        """The needs-attention queue: everything waiting for a person, across cases."""
        return [{"case_id": c.id, "case_title": c.claim[:120], **a}
                for c in service.list() for a in views.pending_approvals(c)]

    # --- checkpoints ----------------------------------------------------------------

    @app.post("/api/cases/{case_id}/legal-approval")
    def approve_legal(case_id: str, body: Decision, user: User) -> dict:
        return views.overview(service.approve_legal(case_id, by=user, note=body.note))

    @app.get("/api/cases/{case_id}/plan")
    def get_plan(case_id: str) -> dict:
        return views.plan(case(case_id))

    @app.put("/api/cases/{case_id}/plan")
    def edit_plan(case_id: str, body: PlanEdit, user: User) -> dict:
        return views.plan(service.edit_plan(case_id, body.tasks, by=user))

    @app.post("/api/cases/{case_id}/plan/approve", status_code=202)
    def approve_plan(case_id: str, user: User) -> dict:
        return views.overview(service.approve_plan(case_id, by=user))

    @app.post("/api/cases/{case_id}/pause")
    def pause(case_id: str, user: User) -> dict:
        return views.overview(service.pause(case_id, by=user))

    @app.post("/api/cases/{case_id}/resume")
    def resume(case_id: str, user: User) -> dict:
        return views.overview(service.resume(case_id, by=user))

    @app.post("/api/cases/{case_id}/stop", status_code=202)
    def stop(case_id: str, user: User) -> dict:
        return views.overview(service.stop(case_id, by=user))

    @app.post("/api/cases/{case_id}/suspicions/{suspicion_id}/scope")
    def decide_scope(case_id: str, suspicion_id: str, body: ScopeDecision, user: User) -> dict:
        service.decide_scope(case_id, suspicion_id, body.approve, by=user, note=body.note)
        return views.suspicions(case(case_id))

    @app.post("/api/cases/{case_id}/sign-off")
    def sign_off(case_id: str, body: Decision, user: User) -> dict:
        return views.overview(service.sign_off(case_id, by=user, note=body.note))

    # --- surfaces -------------------------------------------------------------------

    @app.get("/api/cases/{case_id}/claims")
    def claims(case_id: str) -> dict:
        return views.claims(case(case_id))

    @app.get("/api/cases/{case_id}/evidence")
    def evidence(case_id: str) -> dict:
        return views.evidence(case(case_id))

    @app.get("/api/cases/{case_id}/documents")
    def documents(case_id: str) -> dict:
        return views.documents(case(case_id))

    @app.get("/api/cases/{case_id}/documents/{doc_id}")
    def document(case_id: str, doc_id: str) -> dict:
        doc = views.document(case(case_id), doc_id)
        if doc is None:
            raise HTTPException(404, f"no document {doc_id} in case {case_id}")
        return doc

    @app.get("/api/cases/{case_id}/timeline")
    def timeline(case_id: str) -> dict:
        return views.timeline(case(case_id))

    @app.get("/api/cases/{case_id}/suspicions")
    def suspicions(case_id: str) -> dict:
        return views.suspicions(case(case_id))

    @app.get("/api/cases/{case_id}/audit")
    def audit(case_id: str, action: str | None = None, actor: str | None = None) -> dict:
        return views.audit(case(case_id), action, actor)

    @app.get("/api/cases/{case_id}/summary")
    def summary(case_id: str) -> dict:
        return views.summary(case(case_id))

    @app.get("/api/cases/{case_id}/report", response_class=PlainTextResponse)
    def report(case_id: str) -> PlainTextResponse:
        c = case(case_id)
        if c.workspace is None:
            raise CaseError(f"case {case_id} has no case file yet ({c.status.value})")
        result = c.result
        text = build_report(c.workspace, views.current_verdict(c), c.review, poc=c.poc,
                            stop_reason=result.stop_reason if result else None,
                            rounds=result.rounds if result else None)
        return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")

    # --- live events ----------------------------------------------------------------

    @app.get("/api/cases/{case_id}/events")
    def events(case_id: str, after: int = 0) -> list[dict]:
        return [_event(e) for e in case(case_id).events.since(after)]

    @app.get("/api/cases/{case_id}/events/stream")
    def stream(case_id: str, after: int = 0,
               idle: Annotated[float | None, Query(description="close after this many idle seconds")] = None,
               last_event_id: Annotated[str | None, Header()] = None) -> StreamingResponse:
        log = case(case_id).events
        start = int(last_event_id) if last_event_id and last_event_id.isdigit() else after

        def generate() -> Iterator[str]:
            seen = start
            yield "retry: 3000\n\n"
            while True:
                batch = log.wait(seen, timeout=min(idle, heartbeat) if idle is not None else heartbeat)
                if not batch:
                    if idle is not None:
                        return
                    yield ": keep-alive\n\n"
                    continue
                for event in batch:
                    seen = event.seq
                    yield _sse(event)

        return StreamingResponse(generate(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app
