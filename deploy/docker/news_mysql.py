from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class NewsMySQLSettings:
    host: str
    port: int
    user: str
    password: str
    database: str
    minsize: int = 1
    maxsize: int = 5
    charset: str = "utf8mb4"
    autocommit: bool = True


def load_news_mysql_settings(source: Optional[Mapping[str, str]] = None) -> NewsMySQLSettings:
    env = source or os.environ
    return NewsMySQLSettings(
        host=env.get("MYSQL_HOST", "localhost"),
        port=int(env.get("MYSQL_PORT", "3306")),
        user=env.get("MYSQL_USER", "root"),
        password=env.get("MYSQL_PASSWORD", ""),
        database=env.get("MYSQL_DATABASE", "crawl4ai_news"),
        minsize=int(env.get("MYSQL_MINSIZE", "1")),
        maxsize=int(env.get("MYSQL_MAXSIZE", "5")),
        charset=env.get("MYSQL_CHARSET", "utf8mb4"),
        autocommit=env.get("MYSQL_AUTOCOMMIT", "true").lower() == "true",
    )


class NewsMySQLManager:
    def __init__(self, settings: Optional[NewsMySQLSettings] = None, pool_factory=None):
        self.settings = settings or load_news_mysql_settings()
        self.pool_factory = pool_factory
        self._pool = None
        self._schema_ready = False

    async def _create_pool(self):
        if self.pool_factory is not None:
            return self.pool_factory(self.settings)

        try:
            import aiomysql
        except ModuleNotFoundError as exc:  # pragma: no cover - exercised in runtime only
            raise RuntimeError("缺少 aiomysql 依赖，无法连接 MySQL") from exc

        return await aiomysql.create_pool(
            host=self.settings.host,
            port=self.settings.port,
            user=self.settings.user,
            password=self.settings.password,
            db=self.settings.database,
            minsize=self.settings.minsize,
            maxsize=self.settings.maxsize,
            charset=self.settings.charset,
            autocommit=self.settings.autocommit,
        )

    async def get_pool(self):
        if self._pool is None:
            self._pool = await self._create_pool()
        return self._pool

    async def close(self) -> None:
        if self._pool is None:
            return
        close = getattr(self._pool, "close", None)
        wait_closed = getattr(self._pool, "wait_closed", None)
        if callable(close):
            close()
        if callable(wait_closed):
            await wait_closed()
        self._pool = None

    def _schema_statements(self) -> list[str]:
        return [
            """
            CREATE TABLE IF NOT EXISTS crawler_site (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                site_code VARCHAR(100) NOT NULL UNIQUE,
                site_name VARCHAR(255) NOT NULL,
                base_url VARCHAR(1024) NOT NULL,
                entry_url VARCHAR(1024) NOT NULL,
                rule_json LONGTEXT NOT NULL,
                default_config_json LONGTEXT NULL,
                is_enabled TINYINT(1) NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS crawler_schedule (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                site_id BIGINT NOT NULL,
                cron_expr VARCHAR(100) NOT NULL,
                timezone VARCHAR(100) NOT NULL DEFAULT 'Asia/Shanghai',
                is_enabled TINYINT(1) NOT NULL DEFAULT 1,
                last_run_at DATETIME NULL,
                next_run_at DATETIME NULL,
                last_status VARCHAR(50) NOT NULL DEFAULT '',
                last_error TEXT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_schedule_due (is_enabled, next_run_at),
                CONSTRAINT fk_schedule_site FOREIGN KEY (site_id) REFERENCES crawler_site(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS crawler_article (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                site_id BIGINT NOT NULL,
                title VARCHAR(1024) NOT NULL,
                url VARCHAR(2048) NOT NULL,
                publish_time DATETIME NULL,
                desc_abs LONGTEXT NULL,
                content LONGTEXT NULL,
                logo VARCHAR(2048) NULL,
                resource VARCHAR(255) NULL,
                primary_cls VARCHAR(255) NULL,
                secondary_cls VARCHAR(255) NULL,
                tags_json LONGTEXT NULL,
                fingerprint VARCHAR(64) NOT NULL,
                raw_json LONGTEXT NULL,
                crawl_time DATETIME NOT NULL,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uk_site_url (site_id, url(512)),
                INDEX idx_article_publish_time (publish_time),
                INDEX idx_article_fingerprint (fingerprint),
                CONSTRAINT fk_article_site FOREIGN KEY (site_id) REFERENCES crawler_site(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS crawler_job_log (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                site_id BIGINT NOT NULL,
                schedule_id BIGINT NULL,
                trigger_type VARCHAR(50) NOT NULL,
                started_at DATETIME NOT NULL,
                finished_at DATETIME NULL,
                status VARCHAR(50) NOT NULL,
                processed_count INT NOT NULL DEFAULT 0,
                new_count INT NOT NULL DEFAULT 0,
                failed_count INT NOT NULL DEFAULT 0,
                error_message TEXT NULL,
                result_snapshot_json LONGTEXT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_job_log_site_started (site_id, started_at),
                CONSTRAINT fk_job_log_site FOREIGN KEY (site_id) REFERENCES crawler_site(id)
            )
            """,
        ]

    async def ensure_schema(self) -> None:
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                for statement in self._schema_statements():
                    await cursor.execute(statement)
            commit = getattr(conn, "commit", None)
            if callable(commit):
                await commit()
        self._schema_ready = True

    async def ensure_ready(self) -> None:
        if not self._schema_ready:
            await self.ensure_schema()

    async def execute(self, sql: str, params: Optional[tuple[Any, ...]] = None) -> None:
        await self.ensure_ready()
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(sql, params)
            commit = getattr(conn, "commit", None)
            if callable(commit):
                await commit()

    async def fetchall(self, sql: str, params: Optional[tuple[Any, ...]] = None) -> list[dict[str, Any]]:
        await self.ensure_ready()
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(sql, params)
                rows = await cursor.fetchall()
                if hasattr(cursor, "description") and cursor.description:
                    columns = [item[0] for item in cursor.description]
                    return [dict(zip(columns, row)) for row in rows]
                return rows

    async def fetchone(self, sql: str, params: Optional[tuple[Any, ...]] = None) -> Optional[dict[str, Any]]:
        rows = await self.fetchall(sql, params)
        return rows[0] if rows else None


_mysql_manager: Optional[NewsMySQLManager] = None


def get_news_mysql_manager() -> NewsMySQLManager:
    global _mysql_manager
    if _mysql_manager is None:
        _mysql_manager = NewsMySQLManager()
    return _mysql_manager
