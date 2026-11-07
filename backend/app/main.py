import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth, data, reports, tx
from app.config import get_settings
from app.db import get_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app() -> FastAPI:
    s = get_settings()
    if s.env != "dev" and (s.secret_key.startswith("dev-") or len(s.secret_key) < 32):
        raise RuntimeError("BUDGET_SECRET_KEY must be set to a random value (>=32 chars) outside dev")
    # API docs only in dev: in prod the schema would hand out the whole API surface to anyone
    dev = s.env == "dev"
    app = FastAPI(
        title="Family Budget",
        version="0.1.0",
        docs_url="/api/docs" if dev else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if dev else None,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=s.secret_key,
        session_cookie="budget_session",
        max_age=s.session_max_age,
        same_site="strict",
        https_only=s.cookie_secure,
    )
    for r in (auth.router, data.router, tx.router, reports.router):
        app.include_router(r)

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"ok": True}

    @app.get("/readyz", include_in_schema=False)
    def readyz():
        with get_engine().connect() as c:
            c.execute(text("select 1"))
        return {"ok": True}

    Instrumentator(excluded_handlers=["/healthz", "/readyz", "/metrics"]).instrument(app).expose(
        app, include_in_schema=False
    )

    @app.middleware("http")
    async def internal_only_metrics(request: Request, call_next):
        # /metrics is for in-cluster scraping only. Requests through the ingress (Traefik) always
        # carry X-Forwarded-For, direct pod/service scrapes do not.
        if request.url.path == "/metrics" and "x-forwarded-for" in request.headers:
            return PlainTextResponse("Not Found", status_code=404)
        return await call_next(request)

    # Built SPA (frontend/dist copied into the image as ./static)
    static = Path(s.static_dir).resolve()
    if static.is_dir():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            f = static / path
            return FileResponse(f if path and f.is_file() and static in f.resolve().parents else static / "index.html")

    return app


app = create_app()
