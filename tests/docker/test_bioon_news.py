import sys
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


DOCKER_DIR = Path(__file__).resolve().parents[2] / "deploy" / "docker"
if str(DOCKER_DIR) not in sys.path:
    sys.path.append(str(DOCKER_DIR))

from bioon_news import (  # type: ignore  # noqa: E402
    BioonNewsRunRequest,
    BioonNewsService,
    BioonNewsStatus,
    _repo_root,
    build_router,
    load_bioon_news_rules,
    parse_bioon_detail,
    parse_bioon_homepage,
)
from bioon_news_scheduler import _enabled, _interval  # type: ignore  # noqa: E402


HOME_HTML = """
<div class="item">
  <div class="item-header">
    <a href="http://news.bioon.com/article/b3a293165950.html" target="_blank">
      <img src="https://img.medsci.cn/bioon-com/20260316/1773651144575_9363901.png" />
    </a>
  </div>
  <div class="item-content">
    <h2>
      <a href="http://news.bioon.com/article/b3a293165950.html" target="_blank">
        给抗癌药装上“GPS导航”和“双重弹头”！
      </a>
    </h2>
    <p class="text-justify">本研究构建了一种DNA四面体纳米载体用于递送伏立诺他。</p>
    <span class="item-meta">
      <span class="item-meta-item">2026-03-30</span>
    </span>
  </div>
</div>
"""

HOME_HTML_WITH_YESTERDAY = """
<div class="item">
  <div class="item-header">
    <a href="http://news.bioon.com/article/today-1.html" target="_blank">
      <img src="https://img.example.com/today-1.png" />
    </a>
  </div>
  <div class="item-content">
    <h2><a href="http://news.bioon.com/article/today-1.html">今天资讯一</a></h2>
    <p class="text-justify">今天摘要一</p>
    <span class="item-meta"><span class="item-meta-item">2026-03-30</span></span>
  </div>
</div>
<div class="item">
  <div class="item-header">
    <a href="http://news.bioon.com/article/today-2.html" target="_blank">
      <img src="https://img.example.com/today-2.png" />
    </a>
  </div>
  <div class="item-content">
    <h2><a href="http://news.bioon.com/article/today-2.html">今天资讯二</a></h2>
    <p class="text-justify">今天摘要二</p>
    <span class="item-meta"><span class="item-meta-item">2026-03-30</span></span>
  </div>
</div>
<div class="item">
  <div class="item-header">
    <a href="http://news.bioon.com/article/yesterday.html" target="_blank">
      <img src="https://img.example.com/yesterday.png" />
    </a>
  </div>
  <div class="item-content">
    <h2><a href="http://news.bioon.com/article/yesterday.html">昨天资讯</a></h2>
    <p class="text-justify">昨天摘要</p>
    <span class="item-meta"><span class="item-meta-item">2026-03-29</span></span>
  </div>
</div>
"""


DETAIL_HTML = """
<html>
  <head>
    <title>给抗癌药装上“GPS导航”和“双重弹头”！ - 纳米医学专区 - 生物谷</title>
    <meta name="description" content="本研究构建了一种DNA四面体纳米载体用于递送伏立诺他。" />
  </head>
  <body>
    <div class="composs-main-content">
      <h1 style="font-size: 26px">给抗癌药装上“GPS导航”和“双重弹头”！</h1>
      <p class="source_text">来源：生物谷原创 2026-03-30 11:13</p>
      <blockquote>本研究构建了一种DNA四面体纳米载体用于递送伏立诺他。</blockquote>
      <div style="color: #303a4e;">
        <p>第一段正文。</p>
        <p>第二段正文。</p>
      </div>
    </div>
  </body>
</html>
"""


def test_parse_bioon_homepage_extracts_latest_items():
    items = parse_bioon_homepage(HOME_HTML, "https://www.bioon.com/")

    assert len(items) == 1
    assert items[0]["title"] == "给抗癌药装上“GPS导航”和“双重弹头”！"
    assert items[0]["url"] == "http://news.bioon.com/article/b3a293165950.html"
    assert items[0]["publish_time"] == "2026-03-30"
    assert items[0]["logo"] == "https://img.medsci.cn/bioon-com/20260316/1773651144575_9363901.png"
    assert items[0]["desc_abs"] == "本研究构建了一种DNA四面体纳米载体用于递送伏立诺他。"


def test_parse_bioon_detail_merges_core_fields():
    record = parse_bioon_detail(
        DETAIL_HTML,
        {
            "url": "http://news.bioon.com/article/b3a293165950.html",
            "publish_time": "2026-03-30",
            "logo": "https://img.medsci.cn/bioon-com/20260316/1773651144575_9363901.png",
        },
    )

    assert record["title"] == "给抗癌药装上“GPS导航”和“双重弹头”！"
    assert record["resource"] == "生物谷原创"
    assert record["publish_time"] == "2026-03-30 11:13"
    assert record["secondary_cls"] == "纳米医学专区"
    assert record["primary_cls"] == "生物谷资讯"
    assert record["desc_abs"] == "本研究构建了一种DNA四面体纳米载体用于递送伏立诺他。"
    assert "第一段正文。" in record["content"]
    assert "第二段正文。" in record["content"]


class DummyService(BioonNewsService):
    def __init__(self):
        pass

    async def run(self, payload: BioonNewsRunRequest):
        return {
            "success": True,
            "message": "ok",
            "processed_count": payload.limit,
            "new_count": 1,
            "output_file": "/tmp/news_latest.json",
        }

    async def status(self):
        return BioonNewsStatus(
            success=True,
            last_run_at="2026-03-30T12:00:00+08:00",
            last_success_at="2026-03-30T12:00:00+08:00",
            latest_file="/tmp/news_latest.json",
            archive_file="/tmp/archive/news_20260330_120000.json",
            total_seen_urls=1,
            last_error="",
        )

    async def load_latest(self):
        return [{"title": "示例资讯", "url": "http://example.com"}]


def test_bioon_news_router_exposes_run_status_and_latest():
    app = FastAPI()
    service = DummyService()
    app.include_router(build_router(lambda: service))
    client = TestClient(app)

    run_response = client.post("/custom/bioon-news/run", json={"limit": 3})
    assert run_response.status_code == 200
    assert run_response.json()["processed_count"] == 3

    status_response = client.get("/custom/bioon-news/status")
    assert status_response.status_code == 200
    assert status_response.json()["latest_file"] == "/tmp/news_latest.json"

    latest_response = client.get("/custom/bioon-news/latest")
    assert latest_response.status_code == 200
    assert latest_response.json()["items"][0]["title"] == "示例资讯"


class FakeFetchService(BioonNewsService):
    def __init__(
        self,
        base_dir: Path,
        rules_path: Path | None = None,
        site_repo=None,
        article_repo=None,
        job_log_repo=None,
    ):
        super().__init__(
            base_dir=base_dir,
            rules_path=rules_path,
            site_repo=site_repo,
            article_repo=article_repo,
            job_log_repo=job_log_repo,
        )

    async def fetch_text(self, url: str) -> str:
        if url == "https://www.bioon.com/":
            return HOME_HTML
        return DETAIL_HTML


class MemorySiteRepository:
    def __init__(self):
        self.site = None

    async def get_by_code(self, site_code: str):
        if self.site and self.site["site_code"] == site_code:
            return self.site
        return None

    async def ensure_site(self, **kwargs):
        self.site = {"id": 1, **kwargs}
        return self.site


class MemoryArticleRepository:
    def __init__(self):
        self.records: dict[tuple[int, str], dict] = {}

    async def get_existing_urls(self, site_id: int, urls):
        return {url for url in urls if (site_id, url) in self.records}

    async def upsert_article(self, site_id: int, article: dict):
        self.records[(site_id, article["url"])] = dict(article)

    async def count_articles(self, site_id: int):
        return len([1 for key in self.records if key[0] == site_id])

    async def list_articles(self, site_id: int, *, target_date=None, limit=100):
        items = [item for (current_site_id, _), item in self.records.items() if current_site_id == site_id]
        if target_date:
            items = [item for item in items if item.get("publish_time", "").startswith(target_date)]
        return items[:limit]


class MemoryJobLogRepository:
    def __init__(self):
        self.logs = []

    async def create_job_log(self, **kwargs):
        self.logs.append(dict(kwargs))

    async def finish_latest_job_log(self, **kwargs):
        if self.logs:
            self.logs[-1].update(kwargs)

    async def get_latest_status(self, site_id: int):
        for item in reversed(self.logs):
            if item.get("site_id") == site_id:
                return item
        return None


def test_bioon_news_service_persists_latest_archive_and_state(tmp_path):
    job_log_repo = MemoryJobLogRepository()
    service = FakeFetchService(
        tmp_path / "runtime" / "bioon_news",
        site_repo=MemorySiteRepository(),
        article_repo=MemoryArticleRepository(),
        job_log_repo=job_log_repo,
    )
    result = __import__("asyncio").run(service.run(BioonNewsRunRequest(limit=5, archive=True)))

    assert result["success"] is True
    assert result["new_count"] == 1
    assert job_log_repo.logs[0]["trigger_type"] == "manual"
    assert job_log_repo.logs[0]["schedule_id"] is None
    assert (service.latest_dir / "news_latest.json").exists()
    assert (service.state_dir / "seen_urls.json").exists()
    assert (service.state_dir / "run_state.json").exists()
    assert any(service.archive_dir.rglob("news_*.json"))


def test_bioon_news_service_records_scheduler_trigger_type(tmp_path):
    job_log_repo = MemoryJobLogRepository()
    service = FakeFetchService(
        tmp_path / "runtime" / "bioon_news",
        site_repo=MemorySiteRepository(),
        article_repo=MemoryArticleRepository(),
        job_log_repo=job_log_repo,
    )

    __import__("asyncio").run(
        service.run(
            BioonNewsRunRequest(
                limit=1,
                archive=False,
                trigger_type="scheduler",
                schedule_id=7,
            )
        )
    )

    assert job_log_repo.logs[0]["trigger_type"] == "scheduler"
    assert job_log_repo.logs[0]["schedule_id"] == 7


def test_bioon_news_service_uses_external_rules_file(tmp_path):
    rules_path = tmp_path / "bioon_news_rules.json"
    rules = load_bioon_news_rules()
    rules["defaults"]["primary_class"] = "自定义主分类"
    rules_path.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")

    service = FakeFetchService(
        tmp_path / "runtime" / "bioon_news",
        rules_path=rules_path,
        site_repo=MemorySiteRepository(),
        article_repo=MemoryArticleRepository(),
        job_log_repo=MemoryJobLogRepository(),
    )
    result = __import__("asyncio").run(
        service.run(BioonNewsRunRequest(limit=5, target_date="2026-03-30", archive=True))
    )

    assert result["items"][0]["primary_cls"] == "自定义主分类"


class TodayOnlyService(BioonNewsService):
    def __init__(self, base_dir: Path):
        super().__init__(
            base_dir=base_dir,
            site_repo=MemorySiteRepository(),
            article_repo=MemoryArticleRepository(),
            job_log_repo=MemoryJobLogRepository(),
        )

    async def fetch_text(self, url: str) -> str:
        if url == "https://www.bioon.com/":
            return HOME_HTML_WITH_YESTERDAY
        return DETAIL_HTML


def test_bioon_news_service_filters_records_by_target_date(tmp_path):
    service = TodayOnlyService(tmp_path / "runtime" / "bioon_news")
    result = __import__("asyncio").run(
        service.run(BioonNewsRunRequest(target_date="2026-03-30", archive=True))
    )

    assert result["processed_count"] == 2
    assert result["new_count"] == 2
    assert all(item["url"] != "http://news.bioon.com/article/yesterday.html" for item in result["items"])


def test_bioon_news_scheduler_defaults_to_hourly_enabled(monkeypatch):
    monkeypatch.delenv("BIOON_NEWS_SCHEDULER_ENABLED", raising=False)
    monkeypatch.delenv("BIOON_NEWS_SCHEDULER_INTERVAL_SECONDS", raising=False)

    assert _enabled() is True
    assert _interval() == 60


def test_repo_root_falls_back_when_module_path_is_shallow(monkeypatch, tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    monkeypatch.setattr("bioon_news.__file__", str(app_dir / "bioon_news.py"))
    monkeypatch.chdir(app_dir)

    assert _repo_root() == app_dir


class RotatingTodayService(BioonNewsService):
    def __init__(self, base_dir: Path):
        super().__init__(
            base_dir=base_dir,
            site_repo=MemorySiteRepository(),
            article_repo=MemoryArticleRepository(),
            job_log_repo=MemoryJobLogRepository(),
        )
        self.home_pages = [
            """
            <div class="item"><div class="item-header"><a href="http://news.bioon.com/article/t1.html"><img src="https://img.example.com/t1.png"/></a></div><div class="item-content"><h2><a href="http://news.bioon.com/article/t1.html">今天资讯一</a></h2><p class="text-justify">摘要一</p><span class="item-meta"><span class="item-meta-item">2026-03-30</span></span></div></div>
            """,
            """
            <div class="item"><div class="item-header"><a href="http://news.bioon.com/article/t1.html"><img src="https://img.example.com/t1.png"/></a></div><div class="item-content"><h2><a href="http://news.bioon.com/article/t1.html">今天资讯一</a></h2><p class="text-justify">摘要一</p><span class="item-meta"><span class="item-meta-item">2026-03-30</span></span></div></div>
            <div class="item"><div class="item-header"><a href="http://news.bioon.com/article/t2.html"><img src="https://img.example.com/t2.png"/></a></div><div class="item-content"><h2><a href="http://news.bioon.com/article/t2.html">今天资讯二</a></h2><p class="text-justify">摘要二</p><span class="item-meta"><span class="item-meta-item">2026-03-30</span></span></div></div>
            """,
        ]
        self.fetch_count = 0

    async def fetch_text(self, url: str) -> str:
        if url == "https://www.bioon.com/":
            value = self.home_pages[min(self.fetch_count, len(self.home_pages) - 1)]
            self.fetch_count += 1
            return value
        return DETAIL_HTML


def test_latest_file_accumulates_today_records_across_hourly_runs(tmp_path):
    service = RotatingTodayService(tmp_path / "runtime" / "bioon_news")
    asyncio = __import__("asyncio")

    asyncio.run(service.run(BioonNewsRunRequest(target_date="2026-03-30")))
    asyncio.run(service.run(BioonNewsRunRequest(target_date="2026-03-30")))

    latest = json.loads((service.latest_dir / "news_latest.json").read_text(encoding="utf-8"))
    assert len(latest) == 2
    assert {item["url"] for item in latest} == {
        "http://news.bioon.com/article/t1.html",
        "http://news.bioon.com/article/t2.html",
    }


def test_bioon_service_persists_articles_to_repository(tmp_path):
    site_repo = MemorySiteRepository()
    article_repo = MemoryArticleRepository()
    job_log_repo = MemoryJobLogRepository()
    service = FakeFetchService(
        tmp_path / "runtime" / "bioon_news",
        site_repo=site_repo,
        article_repo=article_repo,
        job_log_repo=job_log_repo,
    )

    result = __import__("asyncio").run(service.run(BioonNewsRunRequest(limit=2, target_date="2026-03-30")))

    assert result["new_count"] == 1
    assert __import__("asyncio").run(article_repo.count_articles(1)) == 1
    assert job_log_repo.logs[-1]["status"] == "success"
