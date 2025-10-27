"""Versioned API routing for Heimdex."""

from fastapi import APIRouter

from . import routes_admin, routes_assets, routes_ingest, routes_jobs, routes_system


def get_api_router() -> APIRouter:
    router = APIRouter(prefix="/v1")
    router.include_router(routes_system.router)
    router.include_router(routes_admin.router)
    router.include_router(routes_ingest.router)
    router.include_router(routes_assets.router)
    router.include_router(routes_jobs.router)
    return router


__all__ = ["get_api_router"]

