import asyncio
import os
import sys
from pathlib import Path


DOCKER_DIR = Path(__file__).resolve().parents[2] / "deploy" / "docker"
if str(DOCKER_DIR) not in sys.path:
    sys.path.append(str(DOCKER_DIR))

from news_mysql import NewsMySQLManager, load_news_mysql_settings  # type: ignore  # noqa: E402


def test_mysql_env_defaults(monkeypatch):
    monkeypatch.delenv("MYSQL_HOST", raising=False)
    monkeypatch.delenv("MYSQL_PORT", raising=False)
    monkeypatch.delenv("MYSQL_USER", raising=False)
    monkeypatch.delenv("MYSQL_PASSWORD", raising=False)
    monkeypatch.delenv("MYSQL_DATABASE", raising=False)

    settings = load_news_mysql_settings(os.environ)

    assert settings.host == "localhost"
    assert settings.port == 3306
    assert settings.user == "root"
    assert settings.password == ""
    assert settings.database == "crawl4ai_news"
    assert settings.autocommit is True


def test_mysql_env_overrides(monkeypatch):
    monkeypatch.setenv("MYSQL_HOST", "db.internal")
    monkeypatch.setenv("MYSQL_PORT", "4406")
    monkeypatch.setenv("MYSQL_USER", "crawler")
    monkeypatch.setenv("MYSQL_PASSWORD", "secret")
    monkeypatch.setenv("MYSQL_DATABASE", "news_center")

    settings = load_news_mysql_settings(os.environ)

    assert settings.host == "db.internal"
    assert settings.port == 4406
    assert settings.user == "crawler"
    assert settings.password == "secret"
    assert settings.database == "news_center"


class _FakeCursor:
    def __init__(self, executed: list[str]):
        self.executed = executed

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, sql: str, params=None):
        self.executed.append(sql)

    async def fetchall(self):
        return []


class _FakeConnection:
    def __init__(self, executed: list[str]):
        self.executed = executed
        self.committed = False

    def cursor(self):
        return _FakeCursor(self.executed)

    async def commit(self):
        self.committed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeAcquire:
    def __init__(self, conn: _FakeConnection):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self):
        self.executed: list[str] = []
        self.conn = _FakeConnection(self.executed)

    def acquire(self):
        return _FakeAcquire(self.conn)


def test_news_mysql_manager_creates_tables():
    pool = _FakePool()
    manager = NewsMySQLManager(settings=load_news_mysql_settings({}), pool_factory=lambda *_args, **_kwargs: pool)

    asyncio.run(manager.ensure_schema())

    joined = "\n".join(pool.executed)
    assert "CREATE TABLE IF NOT EXISTS crawler_site" in joined
    assert "CREATE TABLE IF NOT EXISTS crawler_schedule" in joined
    assert "CREATE TABLE IF NOT EXISTS crawler_article" in joined
    assert "CREATE TABLE IF NOT EXISTS crawler_job_log" in joined
    assert pool.conn.committed is True
