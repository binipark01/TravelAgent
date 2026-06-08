from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from travel_agent.app.api.routes_agent import router as agent_router
from travel_agent.app.api.routes_approvals import router as approvals_router
from travel_agent.app.api.routes_health import router as health_router
from travel_agent.app.api.routes_llm import router as llm_router
from travel_agent.app.api.routes_providers import router as providers_router
from travel_agent.app.api.routes_settings import router as settings_router
from travel_agent.app.api.routes_trips import router as trips_router
from travel_agent.app.config import get_settings
from travel_agent.app.db.repositories import NotFoundError
from travel_agent.app.db.session import configure_database, init_db
from travel_agent.app.guardrails.approval_guardrail import GuardrailViolation


def create_app(database_url: str | None = None, initialize_db: bool = True) -> FastAPI:
    lifespan = None
    if not initialize_db:

        @asynccontextmanager
        async def startup_lifespan(_: FastAPI) -> AsyncIterator[None]:
            configure_database(database_url)
            init_db()
            yield

        lifespan = startup_lifespan

    application = FastAPI(title="Travel Agent Backend", version="0.1.0", lifespan=lifespan)
    settings = get_settings()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    application.include_router(llm_router)
    application.include_router(agent_router)
    application.include_router(trips_router)
    application.include_router(approvals_router)
    application.include_router(providers_router)
    application.include_router(settings_router)

    if initialize_db:
        configure_database(database_url)
        init_db()

    @application.exception_handler(NotFoundError)
    async def not_found_handler(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.exception_handler(GuardrailViolation)
    async def guardrail_handler(_: Request, exc: GuardrailViolation) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @application.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
        raise HTTPException(status_code=400, detail=str(exc))

    return application


app = create_app(initialize_db=False)
