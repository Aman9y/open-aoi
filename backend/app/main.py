"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import (
    routes_camera,
    routes_history,
    routes_inspection,
    routes_reference,
    routes_station,
)
from .api.deps import inspection_repo, reference_repo
from .sources.camera_hub import get_hub
from .config import get_settings
from .logging_config import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    cfg = get_settings()
    cfg.ensure_dirs()
    inspection_repo()  # init DB
    refs = reference_repo().list()
    log.info("AOI backend ready — %d reference(s), active=%s",
             len(refs), next((r.id for r in refs if r.active), None))
    yield
    get_hub().release_all()


def create_app() -> FastAPI:
    cfg = get_settings()
    app = FastAPI(
        title="AI Visual Quality Inspection",
        version="0.1.0",
        description="Simplified, explainable AOI station (prototype).",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(routes_inspection.router)
    app.include_router(routes_reference.router)
    app.include_router(routes_history.router)
    app.include_router(routes_camera.router)
    app.include_router(routes_station.router)

    # Static media: annotated images, reference images.
    app.mount("/media/outputs", StaticFiles(directory=cfg.outputs_dir), name="outputs")
    app.mount("/media/references", StaticFiles(directory=cfg.references_dir), name="references")

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        from .models import MODEL_NOT_CONFIGURED, build_component_detector

        det = build_component_detector(cfg)
        return {
            "status": "ok",
            "yolo": MODEL_NOT_CONFIGURED if det.status == MODEL_NOT_CONFIGURED else "READY",
            "yolo_model_path": str(cfg.yolo_model_path) if cfg.yolo_model_path else None,
        }

    return app


app = create_app()
