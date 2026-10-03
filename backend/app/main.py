from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import Settings
from app.providers.interfaces import Providers, ProviderError
from app.providers.local.extraction import LocalPDFExtractor
from app.providers.local.jobs import LocalJobDispatcher
from app.providers.local.privacy import LocalPrivacyFilter, TemplateExplanations
from app.providers.local.storage import (
    LocalDocumentStorage,
    SQLiteCaseStorage,
    SQLiteMemoryStore,
)
from app.routes.api import router
from app.services.cases import CaseError, CaseService


def _local_lessons(settings: Settings):
    """Opt-in only: with AGENTCORE_MEMORY_ID set, lessons use real AgentCore Memory
    (AWS credentials required). Blank keeps demo mode free of AWS calls."""
    if not settings.agentcore_memory_id:
        return None
    from app.providers.aws.agentcore import AgentCoreLessons

    return AgentCoreLessons(settings)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.validate_mode()
    if settings.app_mode != "demo":
        # This server only wires local providers; labeling them "AWS" would be a
        # silent demo fallback. AWS mode runs through app.handlers.api in Lambda.
        raise ValueError(
            "The local server runs APP_MODE=demo only. AWS mode runs in Lambda "
            "(app.handlers.api); no demo fallback is permitted."
        )

    @asynccontextmanager
    async def lifespan(app):
        cases = SQLiteCaseStorage(settings.local_data_dir)
        cases.interrupt_pending()
        providers = Providers(
            extraction=LocalPDFExtractor(),
            privacy=LocalPrivacyFilter(),
            explanations=TemplateExplanations(),
            documents=LocalDocumentStorage(settings.local_data_dir / "uploads"),
            cases=cases,
            memory=SQLiteMemoryStore(settings.local_data_dir),
            lessons=_local_lessons(settings),
        )
        service = CaseService(providers)
        providers.dispatcher = LocalJobDispatcher(service.process)
        app.state.service = service
        yield
        providers.dispatcher.close()

    app = FastAPI(title="ClearPath — synthetic local starter", lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()
        ],
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(CaseError)
    async def case_error(request: Request, exc: CaseError):
        return JSONResponse(status_code=exc.status, content={"detail": str(exc)})

    @app.exception_handler(ProviderError)
    async def provider_error(request: Request, exc: ProviderError):
        return JSONResponse(
            status_code=503,
            content={"detail": "A provider is unavailable. No demo fallback was used."},
        )

    app.include_router(router, prefix="/api")
    return app


app = create_app()
