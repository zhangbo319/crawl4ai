import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from news_repositories import ArticleRepository, JobLogRepository, SiteRepository


BIOON_HOME_URL = "https://www.bioon.com/"
RULES_FILE_NAME = "bioon_news_rules.json"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name == "crawl4ai":
            return parent
    return Path.cwd()


def _default_base_dir() -> Path:
    value = os.environ.get("BIOON_NEWS_DATA_DIR") or os.environ.get("BIOON_NEWS_BASE_DIR")
    if value:
        return Path(value).expanduser().resolve()
    return _repo_root() / "runtime" / "bioon_news"


def _default_rules_path() -> Path:
    env_value = os.environ.get("BIOON_NEWS_RULES_FILE")
    if env_value:
        return Path(env_value).expanduser().resolve()
    return Path(__file__).resolve().with_name(RULES_FILE_NAME)


def load_bioon_news_rules(path: Optional[Path] = None) -> Dict[str, Any]:
    rules_path = Path(path or _default_rules_path())
    with rules_path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


class BioonNewsRunRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=200)
    target_date: str = ""
    force_refresh: bool = False
    save_raw: bool = False
    archive: bool = True
    trigger_type: str = "manual"
    schedule_id: Optional[int] = None


class BioonNewsStatus(BaseModel):
    success: bool
    last_run_at: str = ""
    last_success_at: str = ""
    latest_file: str = ""
    archive_file: str = ""
    total_seen_urls: int = 0
    last_error: str = ""


def parse_bioon_homepage(
    html: str,
    base_url: str = BIOON_HOME_URL,
    rules: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    active_rules = rules or load_bioon_news_rules()
    homepage_rules = active_rules["homepage"]
    soup = BeautifulSoup(html, "html.parser")
    items: List[Dict[str, Any]] = []
    seen_urls = set()

    for block in soup.select(homepage_rules["item_selector"]):
        title_node = block.select_one(homepage_rules["title_selector"])
        if not title_node:
            continue

        href = (title_node.get("href") or "").strip()
        url = urljoin(base_url, href)
        if not url or "/article/" not in url or url in seen_urls:
            continue

        desc_node = block.select_one(homepage_rules["desc_selector"])
        logo_node = block.select_one(homepage_rules["logo_selector"])
        time_node = block.select_one(homepage_rules["time_selector"])

        seen_urls.add(url)
        items.append(
            {
                "title": " ".join(title_node.get_text(" ", strip=True).split()),
                "url": url,
                "publish_time": " ".join((time_node.get_text(" ", strip=True) if time_node else "").split()),
                "desc_abs": " ".join((desc_node.get_text(" ", strip=True) if desc_node else "").split()),
                "logo": (logo_node.get("src") or "").strip() if logo_node else "",
            }
        )

    return items


def parse_bioon_detail(
    html: str,
    seed: Dict[str, Any],
    rules: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    active_rules = rules or load_bioon_news_rules()
    detail_rules = active_rules["detail"]
    default_rules = active_rules["defaults"]
    soup = BeautifulSoup(html, "html.parser")
    record = dict(seed)

    title_node = soup.select_one(detail_rules["title_selector"])
    page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
    title = " ".join(title_node.get_text(" ", strip=True).split()) if title_node else record.get("title", "")

    source_text = soup.select_one(detail_rules["source_selector"])
    source_line = " ".join(source_text.get_text(" ", strip=True).split()) if source_text else ""
    source_match = re.search(r"来源[:：]\s*(.*?)\s+(20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2})", source_line)
    if source_match:
        resource = source_match.group(1).strip()
        publish_time = source_match.group(2).strip()
    else:
        resource = ""
        publish_time_match = re.search(r"(20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2})", html)
        publish_time = publish_time_match.group(1) if publish_time_match else record.get("publish_time", "")

    desc_node = soup.select_one(detail_rules["summary_selector"])
    meta_desc = soup.select_one(detail_rules["meta_description_selector"])
    desc_abs = ""
    if desc_node:
        desc_abs = " ".join(desc_node.get_text(" ", strip=True).split())
    elif meta_desc and meta_desc.get("content"):
        desc_abs = " ".join(meta_desc["content"].split())
    else:
        desc_abs = record.get("desc_abs", "")

    content_container = soup.select_one(detail_rules["content_container_selector"])
    paragraphs: List[str] = []
    if content_container:
        nodes = list(content_container.select(detail_rules["content_descendant_paragraph_selector"]))
        nodes.extend(content_container.find_all(detail_rules["content_direct_paragraph_tag"], recursive=False))
        for node in nodes:
            classes = node.get("class") or []
            if "source_text" in classes:
                continue
            text = " ".join(node.get_text(" ", strip=True).split())
            if text:
                paragraphs.append(text)

    secondary_cls = record.get("secondary_cls", "")
    if page_title:
        parts = [part.strip() for part in page_title.split(" - ") if part.strip()]
        if len(parts) >= 2:
            secondary_cls = parts[1]

    record.update(
        {
            "title": title,
            "resource": resource,
            "publish_time": publish_time,
            "desc_abs": desc_abs,
            "content": "\n".join(paragraphs).strip(),
            "primary_cls": record.get("primary_cls") or default_rules["primary_class"],
            "secondary_cls": secondary_cls or default_rules["secondary_class_fallback"],
            "tags": record.get("tags", []),
        }
    )
    return record


class BioonNewsService:
    def __init__(
        self,
        base_dir: Optional[Path] = None,
        home_url: str = BIOON_HOME_URL,
        rules_path: Optional[Path] = None,
        site_code: str = "bioon",
        site_repo: Optional[Any] = None,
        article_repo: Optional[Any] = None,
        job_log_repo: Optional[Any] = None,
    ):
        self.base_dir = Path(base_dir or _default_base_dir())
        self.home_url = home_url
        self.rules_path = Path(rules_path) if rules_path else _default_rules_path()
        self.rules = load_bioon_news_rules(self.rules_path)
        self.site_code = site_code
        self.site_repo = site_repo or SiteRepository()
        self.article_repo = article_repo or ArticleRepository()
        self.job_log_repo = job_log_repo or JobLogRepository()
        self.raw_dir = self.base_dir / "raw"
        self.latest_dir = self.base_dir / "latest"
        self.archive_dir = self.base_dir / "archive"
        self.state_dir = self.base_dir / "state"
        for path in (self.raw_dir, self.latest_dir, self.archive_dir, self.state_dir):
            path.mkdir(parents=True, exist_ok=True)

    async def fetch_text(self, url: str) -> str:
        timeout = aiohttp.ClientTimeout(total=self.rules["defaults"]["request_timeout_seconds"])
        headers = {"User-Agent": self.rules["defaults"]["user_agent"]}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                return await response.text()

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as fp:
            return json.load(fp)

    def _write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)

    def _seen_urls_path(self) -> Path:
        return self.state_dir / "seen_urls.json"

    def _run_state_path(self) -> Path:
        return self.state_dir / "run_state.json"

    def _latest_path(self) -> Path:
        return self.latest_dir / "news_latest.json"

    def _fingerprint(self, title: str, publish_time: str, url: str) -> str:
        raw = f"{url}|{title}|{publish_time}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _merge_latest_items(self, target_date: str, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        existing = self._read_json(self._latest_path(), [])
        if isinstance(existing, list):
            for item in existing:
                if item.get("publish_time", "").startswith(target_date) and item.get("url"):
                    merged[item["url"]] = item
        for item in records:
            if item.get("url"):
                merged[item["url"]] = item
        return list(merged.values())

    def _resolve_target_date(self, payload: BioonNewsRunRequest) -> str:
        if payload.target_date:
            return payload.target_date
        return datetime.now().astimezone().strftime("%Y-%m-%d")

    def _save_raw(self, name: str, html: str) -> None:
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)
        (self.raw_dir / safe_name).write_text(html, encoding="utf-8")

    async def _ensure_site_config(self) -> Dict[str, Any]:
        site = await self.site_repo.get_by_code(self.site_code)
        if site:
            if site.get("rule_json"):
                self.rules = site["rule_json"]
            self.home_url = site.get("entry_url") or self.home_url
            return site
        return await self.site_repo.ensure_site(
            site_code=self.site_code,
            site_name="生物谷资讯",
            base_url=BIOON_HOME_URL,
            entry_url=self.home_url,
            rule_json=self.rules,
            default_config_json=self.rules.get("defaults", {}),
            is_enabled=True,
        )

    async def run(self, payload: BioonNewsRunRequest) -> Dict[str, Any]:
        now = _now_iso()
        target_date = self._resolve_target_date(payload)
        site = await self._ensure_site_config()
        site_id = int(site["id"])
        await self.job_log_repo.create_job_log(
            site_id=site_id,
            schedule_id=payload.schedule_id,
            trigger_type=payload.trigger_type,
            started_at=now,
        )

        homepage_html = await self.fetch_text(self.home_url)
        if payload.save_raw:
            self._save_raw("homepage.html", homepage_html)

        homepage_items = [
            item
            for item in parse_bioon_homepage(homepage_html, self.home_url, self.rules)
            if item.get("publish_time", "").startswith(target_date)
        ][: payload.limit]
        existing_urls = set()
        if not payload.force_refresh:
            existing_urls = await self.article_repo.get_existing_urls(
                site_id,
                [item["url"] for item in homepage_items],
            )
        candidates = homepage_items if payload.force_refresh else [item for item in homepage_items if item["url"] not in existing_urls]

        records: List[Dict[str, Any]] = []
        failures: List[Dict[str, str]] = []
        for item in candidates:
            try:
                detail_html = await self.fetch_text(item["url"])
                if payload.save_raw:
                    fingerprint = self._fingerprint(item["title"], item["publish_time"], item["url"])
                    self._save_raw(f"{fingerprint}.html", detail_html)
                record = parse_bioon_detail(detail_html, item, self.rules)
                record["source_site"] = self.rules["defaults"]["source_site"]
                record["crawl_time"] = now
                record["fingerprint"] = self._fingerprint(record["title"], record["publish_time"], record["url"])
                await self.article_repo.upsert_article(site_id, record)
                records.append(record)
            except Exception as exc:  # pragma: no cover - integration only
                failures.append({"url": item["url"], "error": str(exc)})

        latest_file = self._latest_path()
        latest_items = self._merge_latest_items(target_date, records)
        if latest_items:
            self._write_json(latest_file, latest_items)

        archive_file = ""
        if payload.archive and records:
            archive_day = self.archive_dir / datetime.now().strftime("%Y-%m-%d")
            archive_path = archive_day / f"news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            self._write_json(archive_path, records)
            archive_file = str(archive_path)

        seen_urls = sorted(existing_urls.union(record["url"] for record in records))
        self._write_json(self._seen_urls_path(), seen_urls)

        run_state = {
            "success": True,
            "last_run_at": now,
            "last_success_at": now,
            "latest_file": str(latest_file) if latest_file.exists() else "",
            "archive_file": archive_file,
            "total_seen_urls": await self.article_repo.count_articles(site_id),
            "last_error": failures[0]["error"] if failures else "",
            "last_failures": failures,
            "site_code": self.site_code,
        }
        self._write_json(self._run_state_path(), run_state)
        await self.job_log_repo.finish_latest_job_log(
            site_id=site_id,
            finished_at=_now_iso(),
            status="success" if not failures else "partial_success",
            processed_count=len(candidates),
            new_count=len(records),
            failed_count=len(failures),
            error_message=failures[0]["error"] if failures else "",
            result_snapshot_json=run_state,
        )

        return {
            "success": True,
            "message": "抓取完成",
            "target_date": target_date,
            "processed_count": len(candidates),
            "new_count": len(records),
            "failed_count": len(failures),
            "output_file": run_state["latest_file"],
            "archive_file": archive_file,
            "items": latest_items,
        }

    async def status(self) -> BioonNewsStatus:
        state = self._read_json(self._run_state_path(), {})
        site = await self.site_repo.get_by_code(self.site_code)
        if site:
            latest_log = await self.job_log_repo.get_latest_status(int(site["id"]))
            if latest_log:
                state["last_run_at"] = state.get("last_run_at") or str(latest_log.get("started_at") or "")
                state["last_success_at"] = state.get("last_success_at") or str(latest_log.get("finished_at") or "")
                state["last_error"] = state.get("last_error") or (latest_log.get("error_message") or "")
        return BioonNewsStatus(
            success=state.get("success", False),
            last_run_at=state.get("last_run_at", ""),
            last_success_at=state.get("last_success_at", ""),
            latest_file=state.get("latest_file", ""),
            archive_file=state.get("archive_file", ""),
            total_seen_urls=state.get("total_seen_urls", 0),
            last_error=state.get("last_error", ""),
        )

    async def load_latest(self) -> List[Dict[str, Any]]:
        site = await self.site_repo.get_by_code(self.site_code)
        if site:
            return await self.article_repo.list_articles(
                int(site["id"]),
                target_date=datetime.now().astimezone().strftime("%Y-%m-%d"),
                limit=200,
            )
        return self._read_json(self._latest_path(), [])


_service: Optional[BioonNewsService] = None


def get_bioon_news_service() -> BioonNewsService:
    global _service
    if _service is None:
        _service = BioonNewsService()
    return _service


async def _no_auth() -> Dict[str, Any]:
    return {}


def build_router(
    service_factory: Callable[[], BioonNewsService] = get_bioon_news_service,
    token_dep: Optional[Callable[..., Any]] = None,
) -> APIRouter:
    router = APIRouter(prefix="/custom/bioon-news", tags=["bioon-news"])
    security_dep = token_dep or _no_auth

    @router.post("/run")
    async def run_bioon_news(payload: BioonNewsRunRequest, _td: Dict[str, Any] = Depends(security_dep)):
        return await service_factory().run(payload)

    @router.get("/status")
    async def bioon_news_status(_td: Dict[str, Any] = Depends(security_dep)):
        return await service_factory().status()

    @router.get("/latest")
    async def bioon_news_latest(_td: Dict[str, Any] = Depends(security_dep)):
        items = await service_factory().load_latest()
        return {"count": len(items), "items": items}

    return router
