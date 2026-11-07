import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
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
    app = FastAPI(title="Family Budget", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
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
