import sys
from datetime import datetime
from pathlib import Path


DOCKER_DIR = Path(__file__).resolve().parents[2] / "deploy" / "docker"
if str(DOCKER_DIR) not in sys.path:
    sys.path.append(str(DOCKER_DIR))

from news_scheduler_service import NewsSchedulerService, compute_next_run  # type: ignore  # noqa: E402


def test_compute_next_run_from_cron():
    now = datetime.fromisoformat("2026-03-30T10:15:00+08:00")
    next_run = compute_next_run("0 * * * *", "Asia/Shanghai", now)

    assert next_run.isoformat().startswith("2026-03-30T11:00:00")


class MemoryScheduleRepository:
    def __init__(self):
        self.items = [
            {
                "id": 1,
                "site_id": 1,
                "cron_expr": "0 * * * *",
                "timezone": "Asia/Shanghai",
                "is_enabled": 1,
                "next_run_at": "2026-03-30 10:00:00",
            }
        ]
        self.marked = []

    async def get_due_schedules(self):
        return self.items

    async def mark_run_result(self, schedule_id, **kwargs):
        self.marked.append((schedule_id, kwargs))


class MemorySiteRepository:
    async def get_by_id(self, site_id):
        return {"id": site_id, "site_code": "bioon"}


async def _fake_runner(site_code: str, schedule_id: int, trigger_type: str):
    return {
        "success": True,
        "site_code": site_code,
        "schedule_id": schedule_id,
        "trigger_type": trigger_type,
    }


def test_scheduler_runs_due_schedule_and_marks_result():
    schedule_repo = MemoryScheduleRepository()
    service = NewsSchedulerService(
        schedule_repo=schedule_repo,
        site_repo=MemorySiteRepository(),
        trigger_runner=_fake_runner,
    )

    results = __import__("asyncio").run(
        service.run_due_schedules(datetime.fromisoformat("2026-03-30T10:15:00+08:00"))
    )

    assert results[0]["site_code"] == "bioon"
    assert results[0]["result"]["schedule_id"] == 1
    assert results[0]["result"]["trigger_type"] == "scheduler"
    assert schedule_repo.marked[0][0] == 1
    assert schedule_repo.marked[0][1]["last_status"] == "success"
    assert schedule_repo.marked[0][1]["next_run_at"] == "2026-03-30 11:00:00"
