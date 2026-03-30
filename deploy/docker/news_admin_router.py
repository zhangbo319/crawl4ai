from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from bioon_news import BioonNewsRunRequest, BioonNewsService
from news_repositories import JobLogRepository, ScheduleRepository, SiteRepository
from news_schemas import (
    JobLogsResponse,
    SchedulePayload,
    ScheduleUpdatePayload,
    SchedulesResponse,
    SiteConfigPayload,
    SiteRunPayload,
    SitesResponse,
)
from news_scheduler_service import compute_next_run


async def _no_auth() -> Dict[str, Any]:
    return {}


def _default_service_factory(site_code: str) -> BioonNewsService:
    return BioonNewsService(site_code=site_code)


def build_news_admin_router(
    *,
    site_repo_factory: Callable[[], Any] = SiteRepository,
    schedule_repo_factory: Callable[[], Any] = ScheduleRepository,
    job_log_repo_factory: Callable[[], Any] = JobLogRepository,
    service_factory: Callable[[str], Any] = _default_service_factory,
    token_dep: Optional[Callable[..., Any]] = None,
) -> APIRouter:
    router = APIRouter(prefix="/custom", tags=["news-admin"])
    security_dep = token_dep or _no_auth

    @router.post("/sites")
    async def create_site(payload: SiteConfigPayload, _td: Dict[str, Any] = Depends(security_dep)):
        site_repo = site_repo_factory()
        return await site_repo.ensure_site(**payload.model_dump())

    @router.get("/sites", response_model=SitesResponse)
    async def list_sites(_td: Dict[str, Any] = Depends(security_dep)):
        items = await site_repo_factory().list_sites()
        return {"items": items}

    @router.get("/sites/{site_code}")
    async def get_site(site_code: str, _td: Dict[str, Any] = Depends(security_dep)):
        site = await site_repo_factory().get_by_code(site_code)
        if not site:
            raise HTTPException(status_code=404, detail="site not found")
        return site

    @router.put("/sites/{site_code}")
    async def update_site(site_code: str, payload: SiteConfigPayload, _td: Dict[str, Any] = Depends(security_dep)):
        if payload.site_code != site_code:
            raise HTTPException(status_code=400, detail="site_code mismatch")
        return await site_repo_factory().ensure_site(**payload.model_dump())

    @router.post("/schedules")
    async def create_schedule(payload: SchedulePayload, _td: Dict[str, Any] = Depends(security_dep)):
        next_run = compute_next_run(payload.cron_expr, payload.timezone, datetime.now().astimezone())
        schedule_repo = schedule_repo_factory()
        await schedule_repo.create_schedule(
            site_id=payload.site_id,
            cron_expr=payload.cron_expr,
            timezone=payload.timezone,
            is_enabled=payload.is_enabled,
            next_run_at=next_run.strftime("%Y-%m-%d %H:%M:%S"),
        )
        return {"success": True, "next_run_at": next_run.strftime("%Y-%m-%d %H:%M:%S")}

    @router.get("/schedules", response_model=SchedulesResponse)
    async def list_schedules(_td: Dict[str, Any] = Depends(security_dep)):
        items = await schedule_repo_factory().list_schedules()
        return {"items": items}

    @router.put("/schedules/{schedule_id}")
    async def update_schedule(schedule_id: int, payload: ScheduleUpdatePayload, _td: Dict[str, Any] = Depends(security_dep)):
        next_run = compute_next_run(payload.cron_expr, payload.timezone, datetime.now().astimezone())
        await schedule_repo_factory().update_schedule(
            schedule_id,
            cron_expr=payload.cron_expr,
            timezone=payload.timezone,
            is_enabled=payload.is_enabled,
            next_run_at=next_run.strftime("%Y-%m-%d %H:%M:%S"),
        )
        return {"success": True, "next_run_at": next_run.strftime("%Y-%m-%d %H:%M:%S")}

    @router.get("/job-logs", response_model=JobLogsResponse)
    async def list_job_logs(_td: Dict[str, Any] = Depends(security_dep)):
        items = await job_log_repo_factory().list_logs()
        return {"items": items}

    @router.post("/sites/{site_code}/run")
    async def run_site(site_code: str, payload: SiteRunPayload, _td: Dict[str, Any] = Depends(security_dep)):
        request = BioonNewsRunRequest(**payload.model_dump())
        return await service_factory(site_code).run(request)

    @router.get("/sites/{site_code}/status")
    async def site_status(site_code: str, _td: Dict[str, Any] = Depends(security_dep)):
        return await service_factory(site_code).status()

    @router.get("/sites/{site_code}/articles")
    async def site_articles(site_code: str, _td: Dict[str, Any] = Depends(security_dep)):
        items = await service_factory(site_code).load_latest()
        return {"count": len(items), "items": items}

    return router
