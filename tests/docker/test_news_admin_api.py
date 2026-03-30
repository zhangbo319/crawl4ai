import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


DOCKER_DIR = Path(__file__).resolve().parents[2] / "deploy" / "docker"
if str(DOCKER_DIR) not in sys.path:
    sys.path.append(str(DOCKER_DIR))

from news_admin_router import build_news_admin_router  # type: ignore  # noqa: E402


class MemorySiteRepository:
    def __init__(self):
        self.items = {}
        self.next_id = 1

    async def ensure_site(self, **kwargs):
        current = self.items.get(kwargs["site_code"]) or {"id": self.next_id}
        current.update(kwargs)
        self.items[kwargs["site_code"]] = current
        if current["id"] == self.next_id:
            self.next_id += 1
        return current

    async def list_sites(self):
        return list(self.items.values())

    async def get_by_code(self, site_code):
        return self.items.get(site_code)

    async def get_by_id(self, site_id):
        for item in self.items.values():
            if item["id"] == site_id:
                return item
        return None


class MemoryScheduleRepository:
    def __init__(self):
        self.items = []

    async def create_schedule(self, **kwargs):
        self.items.append({"id": len(self.items) + 1, **kwargs})

    async def list_schedules(self):
        return self.items

    async def update_schedule(self, schedule_id, **kwargs):
        for item in self.items:
            if item["id"] == schedule_id:
                item.update(kwargs)


class MemoryJobLogRepository:
    async def list_logs(self):
        return [{"id": 1, "status": "success"}]


class MemoryRunService:
    async def run(self, payload):
        return {
            "success": True,
            "processed_count": payload.limit,
            "trigger_type": payload.trigger_type,
            "schedule_id": payload.schedule_id,
        }

    async def status(self):
        return {"success": True}

    async def load_latest(self):
        return [{"title": "示例", "url": "http://example.com"}]


def test_news_admin_router_supports_site_schedule_and_logs():
    site_repo = MemorySiteRepository()
    schedule_repo = MemoryScheduleRepository()
    job_log_repo = MemoryJobLogRepository()

    app = FastAPI()
    app.include_router(
        build_news_admin_router(
            site_repo_factory=lambda: site_repo,
            schedule_repo_factory=lambda: schedule_repo,
            job_log_repo_factory=lambda: job_log_repo,
            service_factory=lambda _site_code: MemoryRunService(),
        )
    )
    client = TestClient(app)

    create_site = client.post(
        "/custom/sites",
        json={
            "site_code": "bioon",
            "site_name": "生物谷资讯",
            "base_url": "https://www.bioon.com/",
            "entry_url": "https://www.bioon.com/",
            "rule_json": {"homepage": {}, "detail": {}, "defaults": {}},
            "default_config_json": {},
            "is_enabled": True,
        },
    )
    assert create_site.status_code == 200
    assert create_site.json()["site_code"] == "bioon"

    list_sites = client.get("/custom/sites")
    assert list_sites.status_code == 200
    assert list_sites.json()["items"][0]["site_code"] == "bioon"

    create_schedule = client.post(
        "/custom/schedules",
        json={"site_id": 1, "cron_expr": "0 * * * *", "timezone": "Asia/Shanghai", "is_enabled": True},
    )
    assert create_schedule.status_code == 200
    assert create_schedule.json()["success"] is True

    list_schedules = client.get("/custom/schedules")
    assert list_schedules.status_code == 200
    assert list_schedules.json()["items"][0]["site_id"] == 1

    list_logs = client.get("/custom/job-logs")
    assert list_logs.status_code == 200
    assert list_logs.json()["items"][0]["status"] == "success"

    run_site = client.post("/custom/sites/bioon/run", json={"limit": 3})
    assert run_site.status_code == 200
    assert run_site.json()["processed_count"] == 3
    assert run_site.json()["trigger_type"] == "manual"

    scheduler_run = client.post(
        "/custom/sites/bioon/run",
        json={"limit": 1, "trigger_type": "scheduler", "schedule_id": 99},
    )
    assert scheduler_run.status_code == 200
    assert scheduler_run.json()["trigger_type"] == "scheduler"
    assert scheduler_run.json()["schedule_id"] == 99
