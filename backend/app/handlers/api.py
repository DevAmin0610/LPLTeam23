from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum
from app.aws_runtime import create_aws_service
from app.config import Settings
from app.providers.interfaces import ProviderError
from app.routes.api import router
from app.services.cases import CaseError


def create_aws_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(title="ClearPath")
    app.state.settings = settings
    app.state.service = create_aws_service(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in settings.cors_allowed_origins.split(",")
            if origin.strip()
        ],
        allow_methods=["GET", "POST", "PUT"],
        # The frontend sends the Cognito token as "Authorization: Bearer <JWT>".
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.exception_handler(CaseError)
    async def case_error(request: Request, exc: CaseError):
        return JSONResponse(
            status_code=exc.status,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ProviderError)
    async def provider_error(request: Request, exc: ProviderError):
        return JSONResponse(
            status_code=503,
            content={"detail": "A provider is unavailable."},
        )

    app.include_router(router, prefix="/api")
    return app


handler = Mangum(create_aws_app())
