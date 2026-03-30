from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable, Optional

from news_mysql import NewsMySQLManager, get_news_mysql_manager


def _parse_json(text: Optional[str], default: Any) -> Any:
    if not text:
        return default
    return json.loads(text)


class SiteRepository:
    def __init__(self, manager: Optional[NewsMySQLManager] = None):
        self.manager = manager or get_news_mysql_manager()

    async def get_by_code(self, site_code: str) -> Optional[dict[str, Any]]:
        row = await self.manager.fetchone(
            """
            SELECT * FROM crawler_site
            WHERE site_code = %s
            """,
            (site_code,),
        )
        if not row:
            return None
        row["rule_json"] = _parse_json(row.get("rule_json"), {})
        row["default_config_json"] = _parse_json(row.get("default_config_json"), {})
        return row

    async def get_by_id(self, site_id: int) -> Optional[dict[str, Any]]:
        row = await self.manager.fetchone(
            """
            SELECT * FROM crawler_site
            WHERE id = %s
            """,
            (site_id,),
        )
        if not row:
            return None
        row["rule_json"] = _parse_json(row.get("rule_json"), {})
        row["default_config_json"] = _parse_json(row.get("default_config_json"), {})
        return row

    async def list_sites(self) -> list[dict[str, Any]]:
        rows = await self.manager.fetchall(
            """
            SELECT * FROM crawler_site
            ORDER BY id ASC
            """
        )
        for row in rows:
            row["rule_json"] = _parse_json(row.get("rule_json"), {})
            row["default_config_json"] = _parse_json(row.get("default_config_json"), {})
        return rows

    async def ensure_site(
        self,
        *,
        site_code: str,
        site_name: str,
        base_url: str,
        entry_url: str,
        rule_json: dict[str, Any],
        default_config_json: dict[str, Any],
        is_enabled: bool = True,
    ) -> dict[str, Any]:
        await self.manager.execute(
            """
            INSERT INTO crawler_site (
                site_code, site_name, base_url, entry_url, rule_json, default_config_json, is_enabled
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                site_name = VALUES(site_name),
                base_url = VALUES(base_url),
                entry_url = VALUES(entry_url),
                rule_json = VALUES(rule_json),
                default_config_json = VALUES(default_config_json),
                is_enabled = VALUES(is_enabled)
            """,
            (
                site_code,
                site_name,
                base_url,
                entry_url,
                json.dumps(rule_json, ensure_ascii=False),
                json.dumps(default_config_json, ensure_ascii=False),
                int(is_enabled),
            ),
        )
        row = await self.get_by_code(site_code)
        if row is None:
            raise RuntimeError(f"站点配置写入失败: {site_code}")
        return row


class ScheduleRepository:
    def __init__(self, manager: Optional[NewsMySQLManager] = None):
        self.manager = manager or get_news_mysql_manager()

    async def create_schedule(
        self,
        *,
        site_id: int,
        cron_expr: str,
        timezone: str,
        is_enabled: bool,
        next_run_at: Optional[str],
    ) -> None:
        await self.manager.execute(
            """
            INSERT INTO crawler_schedule (
                site_id, cron_expr, timezone, is_enabled, next_run_at
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (site_id, cron_expr, timezone, int(is_enabled), next_run_at),
        )

    async def update_schedule(
        self,
        schedule_id: int,
        *,
        cron_expr: str,
        timezone: str,
        is_enabled: bool,
        next_run_at: Optional[str],
    ) -> None:
        await self.manager.execute(
            """
            UPDATE crawler_schedule
            SET cron_expr = %s,
                timezone = %s,
                is_enabled = %s,
                next_run_at = %s
            WHERE id = %s
            """,
            (cron_expr, timezone, int(is_enabled), next_run_at, schedule_id),
        )

    async def list_schedules(self) -> list[dict[str, Any]]:
        return await self.manager.fetchall(
            """
            SELECT * FROM crawler_schedule
            ORDER BY id ASC
            """
        )

    async def get_by_id(self, schedule_id: int) -> Optional[dict[str, Any]]:
        return await self.manager.fetchone(
            """
            SELECT * FROM crawler_schedule
            WHERE id = %s
            """,
            (schedule_id,),
        )

    async def get_due_schedules(self) -> list[dict[str, Any]]:
        return await self.manager.fetchall(
            """
            SELECT * FROM crawler_schedule
            WHERE is_enabled = 1
            ORDER BY id ASC
            """
        )

    async def mark_run_result(
        self,
        schedule_id: int,
        *,
        last_run_at: str,
        next_run_at: Optional[str],
        last_status: str,
        last_error: str,
    ) -> None:
        await self.manager.execute(
            """
            UPDATE crawler_schedule
            SET last_run_at = %s,
                next_run_at = %s,
                last_status = %s,
                last_error = %s
            WHERE id = %s
            """,
            (last_run_at, next_run_at, last_status, last_error, schedule_id),
        )


class ArticleRepository:
    def __init__(self, manager: Optional[NewsMySQLManager] = None):
        self.manager = manager or get_news_mysql_manager()

    async def get_existing_urls(self, site_id: int, urls: Iterable[str]) -> set[str]:
        values = [url for url in urls if url]
        if not values:
            return set()
        placeholders = ", ".join(["%s"] * len(values))
        rows = await self.manager.fetchall(
            f"""
            SELECT url FROM crawler_article
            WHERE site_id = %s AND url IN ({placeholders})
            """,
            tuple([site_id, *values]),
        )
        return {row["url"] for row in rows}

    async def upsert_article(self, site_id: int, article: dict[str, Any]) -> None:
        publish_time = article.get("publish_time") or None
        crawl_time = article.get("crawl_time") or datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        await self.manager.execute(
            """
            INSERT INTO crawler_article (
                site_id, title, url, publish_time, desc_abs, content, logo, resource,
                primary_cls, secondary_cls, tags_json, fingerprint, raw_json, crawl_time
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                title = VALUES(title),
                publish_time = VALUES(publish_time),
                desc_abs = VALUES(desc_abs),
                content = VALUES(content),
                logo = VALUES(logo),
                resource = VALUES(resource),
                primary_cls = VALUES(primary_cls),
                secondary_cls = VALUES(secondary_cls),
                tags_json = VALUES(tags_json),
                fingerprint = VALUES(fingerprint),
                raw_json = VALUES(raw_json),
                crawl_time = VALUES(crawl_time),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                site_id,
                article.get("title", ""),
                article.get("url", ""),
                publish_time,
                article.get("desc_abs", ""),
                article.get("content", ""),
                article.get("logo", ""),
                article.get("resource", ""),
                article.get("primary_cls", ""),
                article.get("secondary_cls", ""),
                json.dumps(article.get("tags", []), ensure_ascii=False),
                article.get("fingerprint", ""),
                json.dumps(article, ensure_ascii=False),
                crawl_time,
            ),
        )

    async def count_articles(self, site_id: int) -> int:
        row = await self.manager.fetchone(
            """
            SELECT COUNT(*) AS total
            FROM crawler_article
            WHERE site_id = %s
            """,
            (site_id,),
        )
        return int(row["total"]) if row else 0

    async def list_articles(
        self,
        site_id: int,
        *,
        target_date: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT title, url, publish_time, desc_abs, content, logo, resource,
                   primary_cls, secondary_cls, tags_json, fingerprint, raw_json, crawl_time
            FROM crawler_article
            WHERE site_id = %s
        """
        params: list[Any] = [site_id]
        if target_date:
            sql += " AND DATE(publish_time) = %s"
            params.append(target_date)
        sql += " ORDER BY publish_time DESC, id DESC LIMIT %s"
        params.append(limit)
        rows = await self.manager.fetchall(sql, tuple(params))
        for row in rows:
            row["tags"] = _parse_json(row.pop("tags_json", "[]"), [])
            raw_json = _parse_json(row.pop("raw_json", "{}"), {})
            if raw_json:
                row.update({k: v for k, v in raw_json.items() if k not in row})
        return rows


class JobLogRepository:
    def __init__(self, manager: Optional[NewsMySQLManager] = None):
        self.manager = manager or get_news_mysql_manager()

    async def create_job_log(
        self,
        *,
        site_id: int,
        schedule_id: Optional[int],
        trigger_type: str,
        started_at: str,
        status: str = "running",
    ) -> None:
        await self.manager.execute(
            """
            INSERT INTO crawler_job_log (
                site_id, schedule_id, trigger_type, started_at, status
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (site_id, schedule_id, trigger_type, started_at, status),
        )

    async def finish_latest_job_log(
        self,
        *,
        site_id: int,
        finished_at: str,
        status: str,
        processed_count: int,
        new_count: int,
        failed_count: int,
        error_message: str,
        result_snapshot_json: dict[str, Any],
    ) -> None:
        await self.manager.execute(
            """
            UPDATE crawler_job_log
            SET finished_at = %s,
                status = %s,
                processed_count = %s,
                new_count = %s,
                failed_count = %s,
                error_message = %s,
                result_snapshot_json = %s
            WHERE site_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                finished_at,
                status,
                processed_count,
                new_count,
                failed_count,
                error_message,
                json.dumps(result_snapshot_json, ensure_ascii=False),
                site_id,
            ),
        )

    async def get_latest_status(self, site_id: int) -> Optional[dict[str, Any]]:
        return await self.manager.fetchone(
            """
            SELECT *
            FROM crawler_job_log
            WHERE site_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (site_id,),
        )

    async def list_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        return await self.manager.fetchall(
            """
            SELECT *
            FROM crawler_job_log
            ORDER BY id DESC
            LIMIT %s
            """,
            (limit,),
        )
