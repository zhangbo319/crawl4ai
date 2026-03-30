from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

import httpx

from news_repositories import ScheduleRepository, SiteRepository


def compute_next_run(cron_expr: str, timezone: str, now: datetime) -> datetime:
    from croniter import croniter
    from zoneinfo import ZoneInfo

    localized = now.astimezone(ZoneInfo(timezone))
    return croniter(cron_expr, localized).get_next(datetime)


class NewsSchedulerService:
    def __init__(
        self,
        schedule_repo: Optional[Any] = None,
        site_repo: Optional[Any] = None,
        trigger_runner: Optional[Callable[[str, int, str], Awaitable[dict[str, Any]]]] = None,
    ):
        self.schedule_repo = schedule_repo or ScheduleRepository()
        self.site_repo = site_repo or SiteRepository()
        self.trigger_runner = trigger_runner or self._trigger_via_http

    async def _trigger_via_http(self, site_code: str, schedule_id: int, trigger_type: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"http://127.0.0.1:11235/custom/sites/{site_code}/run",
                json={
                    "limit": 100,
                    "force_refresh": False,
                    "save_raw": False,
                    "archive": True,
                    "trigger_type": trigger_type,
                    "schedule_id": schedule_id,
                },
            )
            response.raise_for_status()
            return response.json()

    def _is_due(self, item: dict[str, Any], current_time: datetime) -> bool:
        from zoneinfo import ZoneInfo

        timezone = item.get("timezone") or "Asia/Shanghai"
        localized_now = current_time.astimezone(ZoneInfo(timezone))
        next_run_value = item.get("next_run_at")
        if not next_run_value:
            return True
        if isinstance(next_run_value, str):
            next_run = datetime.fromisoformat(next_run_value.replace(" ", "T"))
        else:
            next_run = next_run_value
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=ZoneInfo(timezone))
        return next_run <= localized_now

    async def run_due_schedules(self, now: Optional[datetime] = None) -> list[dict[str, Any]]:
        current_time = (now or datetime.now().astimezone())
        all_items = await self.schedule_repo.get_due_schedules()
        due_items = [item for item in all_items if self._is_due(item, current_time)]
        results: list[dict[str, Any]] = []
        for item in due_items:
            site = await self.site_repo.get_by_id(int(item["site_id"]))
            if not site:
                continue
            try:
                trigger_result = await self.trigger_runner(site["site_code"], int(item["id"]), "scheduler")
                timezone = item.get("timezone") or "Asia/Shanghai"
                localized_now = current_time.astimezone(__import__("zoneinfo").ZoneInfo(timezone))
                next_run = compute_next_run(item["cron_expr"], timezone, localized_now)
                await self.schedule_repo.mark_run_result(
                    int(item["id"]),
                    last_run_at=localized_now.strftime("%Y-%m-%d %H:%M:%S"),
                    next_run_at=next_run.strftime("%Y-%m-%d %H:%M:%S"),
                    last_status="success",
                    last_error="",
                )
                results.append({"schedule_id": item["id"], "site_code": site["site_code"], "result": trigger_result})
            except Exception as exc:  # pragma: no cover - integration only
                timezone = item.get("timezone") or "Asia/Shanghai"
                localized_now = current_time.astimezone(__import__("zoneinfo").ZoneInfo(timezone))
                await self.schedule_repo.mark_run_result(
                    int(item["id"]),
                    last_run_at=localized_now.strftime("%Y-%m-%d %H:%M:%S"),
                    next_run_at=None,
                    last_status="failed",
                    last_error=str(exc),
                )
                results.append({"schedule_id": item["id"], "site_code": site["site_code"], "error": str(exc)})
        return results
