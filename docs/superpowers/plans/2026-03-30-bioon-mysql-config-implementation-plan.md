# 生物谷资讯 MySQL 与配置中心改造 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前 Bioon 单站点抓取实现升级为“MySQL 结果持久化 + 数据库存储站点规则与调度配置”的可扩展底座，并保持手动触发与定时触发能力。

**Architecture:** 以 `deploy/docker/` 为主战场，新增 MySQL 存储层、站点配置仓储层、调度仓储层和任务日志层；在不破坏现有 API 骨架的前提下，把 `bioon_news.py` 改造成基于 `site_code` 和数据库配置执行的首个站点执行器。定时逻辑从环境变量驱动迁移到数据库驱动的 cron 调度器，Redis 仅承担分布式锁和运行时协调。

**Tech Stack:** FastAPI、aiohttp、aiomysql、croniter、Redis、pytest

---

## 文件结构

### 预计新增文件
- `deploy/docker/news_mysql.py`
  - MySQL 连接管理、初始化建表、基础执行封装
- `deploy/docker/news_repositories.py`
  - `crawler_site`、`crawler_schedule`、`crawler_article`、`crawler_job_log` 的仓储操作
- `deploy/docker/news_schemas.py`
  - 站点配置、调度配置、文章查询、手动执行的 Pydantic 模型
- `deploy/docker/news_admin_router.py`
  - `/custom/sites`、`/custom/schedules`、`/custom/job-logs` 等接口
- `deploy/docker/news_scheduler_service.py`
  - 数据库驱动的调度扫描、cron 计算、Redis 锁
- `tests/docker/test_news_mysql.py`
  - MySQL 配置、建表、基础仓储测试
- `tests/docker/test_news_admin_api.py`
  - 站点与调度配置 API 测试
- `tests/docker/test_news_scheduler_service.py`
  - cron 计算、到期调度、锁控制测试

### 预计修改文件
- `deploy/docker/bioon_news.py`
  - 从本地 JSON / 文件状态迁移为仓储读写
- `deploy/docker/bioon_news_scheduler.py`
  - 从固定间隔环境变量触发改为数据库驱动调度入口
- `deploy/docker/server.py`
  - 挂载新管理接口，并初始化 MySQL 依赖
- `deploy/docker/supervisord.conf`
  - 调整调度进程启动命令
- `deploy/docker/requirements.txt`
  - 增加 `aiomysql`、`croniter`
- `deploy/docker/.llm.env.example`
  - 增加 MySQL 连接配置示例
- `tests/docker/test_bioon_news.py`
  - 调整现有测试到“数据库持久化 + 数据库配置读取”的行为
- `操作方法记录/*.md`
  - 更新部署、操作、结果说明、排障文档

### 设计约束
- 不改动 `crawl4ai/async_database.py`；该模块仍服务于现有核心 SQLite 缓存，不混入 Bioon 配置中心需求。
- Bioon 首版仍是唯一 `site_code`，但代码接口必须允许第二个站点接入。
- 首版实现优先支持单实例 Docker；Redis 锁为“默认启用、部署可选”的能力。

## Chunk 1: 基础依赖与 MySQL 底座

### Task 1: 引入依赖与环境变量配置

**Files:**
- Modify: `deploy/docker/requirements.txt`
- Modify: `deploy/docker/.llm.env.example`
- Test: `tests/docker/test_news_mysql.py`

- [ ] **Step 1: 写依赖配置测试**

```python
def test_mysql_env_defaults():
    settings = load_news_mysql_settings({})
    assert settings.host == "localhost"
    assert settings.port == 3306
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/docker/test_news_mysql.py::test_mysql_env_defaults -v`
Expected: FAIL with `load_news_mysql_settings` not found

- [ ] **Step 3: 增加依赖与环境变量说明**

```text
aiomysql>=0.2
croniter>=3.0
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=secret
MYSQL_DATABASE=crawl4ai_news
```

- [ ] **Step 4: 运行目标测试确认通过**

Run: `pytest tests/docker/test_news_mysql.py::test_mysql_env_defaults -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add deploy/docker/requirements.txt deploy/docker/.llm.env.example tests/docker/test_news_mysql.py
git commit -m "feat: add mysql config bootstrap"
```

### Task 2: 建立 MySQL 管理器与初始化建表

**Files:**
- Create: `deploy/docker/news_mysql.py`
- Test: `tests/docker/test_news_mysql.py`

- [ ] **Step 1: 写建表行为测试**

```python
async def test_news_mysql_manager_creates_tables():
    manager = NewsMySQLManager(fake_settings)
    await manager.ensure_schema()
    assert "crawler_site" in manager.created_tables
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/docker/test_news_mysql.py::test_news_mysql_manager_creates_tables -v`
Expected: FAIL with `NewsMySQLManager` not found

- [ ] **Step 3: 实现最小 MySQL 管理器**

```python
class NewsMySQLManager:
    async def ensure_schema(self):
        await self.execute("CREATE TABLE IF NOT EXISTS crawler_site (...)")
```

- [ ] **Step 4: 补齐四张核心表 DDL**

Run DDL for:
- `crawler_site`
- `crawler_schedule`
- `crawler_article`
- `crawler_job_log`

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/docker/test_news_mysql.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add deploy/docker/news_mysql.py tests/docker/test_news_mysql.py
git commit -m "feat: add news mysql schema manager"
```

## Chunk 2: 结果入库与 Bioon 执行器改造

### Task 3: 建立文章与任务日志仓储

**Files:**
- Create: `deploy/docker/news_repositories.py`
- Test: `tests/docker/test_news_mysql.py`

- [ ] **Step 1: 写文章去重写入测试**

```python
async def test_article_repository_upserts_by_site_and_url():
    repo = ArticleRepository(manager)
    await repo.upsert_article(site_id=1, article={"url": "http://x"})
    await repo.upsert_article(site_id=1, article={"url": "http://x"})
    assert await repo.count_articles(site_id=1) == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/docker/test_news_mysql.py::test_article_repository_upserts_by_site_and_url -v`
Expected: FAIL with `ArticleRepository` not found

- [ ] **Step 3: 实现最小仓储层**

```python
class ArticleRepository:
    async def upsert_article(self, site_id: int, article: dict) -> int:
        ...
```

- [ ] **Step 4: 增加任务日志写入与查询**

```python
class JobLogRepository:
    async def create_job_log(...): ...
    async def finish_job_log(...): ...
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/docker/test_news_mysql.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add deploy/docker/news_repositories.py tests/docker/test_news_mysql.py
git commit -m "feat: add article and job log repositories"
```

### Task 4: 把 Bioon 抓取结果从 JSON 主存储迁到 MySQL

**Files:**
- Modify: `deploy/docker/bioon_news.py`
- Modify: `tests/docker/test_bioon_news.py`
- Test: `tests/docker/test_bioon_news.py`

- [ ] **Step 1: 写“抓取后入库”失败测试**

```python
async def test_bioon_service_persists_articles_to_mysql():
    result = await service.run(BioonNewsRunRequest(limit=2))
    assert result["new_count"] == 2
    assert await article_repo.count_articles(site_id=1) == 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/docker/test_bioon_news.py::test_bioon_service_persists_articles_to_mysql -v`
Expected: FAIL because service still only writes files

- [ ] **Step 3: 改造 `BioonNewsService` 依赖注入**

```python
class BioonNewsService:
    def __init__(self, site_repo, article_repo, job_log_repo, ...):
        ...
```

- [ ] **Step 4: 仅把 JSON 结果降级为调试输出**

Keep optional:
- `latest/news_latest.json`
- `archive/*.json`

But primary success condition must come from MySQL.

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/docker/test_bioon_news.py -q`
Expected: PASS with updated persistence assertions

- [ ] **Step 6: 提交**

```bash
git add deploy/docker/bioon_news.py tests/docker/test_bioon_news.py
git commit -m "feat: persist bioon articles to mysql"
```

## Chunk 3: 站点配置中心

### Task 5: 建立站点配置与调度配置 schema / repository

**Files:**
- Create: `deploy/docker/news_schemas.py`
- Modify: `deploy/docker/news_repositories.py`
- Test: `tests/docker/test_news_admin_api.py`

- [ ] **Step 1: 写站点配置 CRUD 测试**

```python
def test_create_site_config_returns_site_code():
    payload = {"site_code": "bioon", "entry_url": "https://www.bioon.com/"}
    response = client.post("/custom/sites", json=payload)
    assert response.status_code == 200
    assert response.json()["site_code"] == "bioon"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/docker/test_news_admin_api.py::test_create_site_config_returns_site_code -v`
Expected: FAIL because route does not exist

- [ ] **Step 3: 实现配置 Schema 与仓储**

```python
class SiteConfigPayload(BaseModel):
    site_code: str
    entry_url: str
    rule_json: dict
```

- [ ] **Step 4: 运行相关测试确认通过**

Run: `pytest tests/docker/test_news_admin_api.py -q`
Expected: PASS for repository-backed CRUD

- [ ] **Step 5: 提交**

```bash
git add deploy/docker/news_schemas.py deploy/docker/news_repositories.py tests/docker/test_news_admin_api.py
git commit -m "feat: add site and schedule configuration schemas"
```

### Task 6: 挂载配置管理 API

**Files:**
- Create: `deploy/docker/news_admin_router.py`
- Modify: `deploy/docker/server.py`
- Test: `tests/docker/test_news_admin_api.py`

- [ ] **Step 1: 写 API 路由失败测试**

```python
def test_get_sites_returns_seeded_bioon():
    response = client.get("/custom/sites")
    assert response.status_code == 200
    assert response.json()["items"][0]["site_code"] == "bioon"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/docker/test_news_admin_api.py::test_get_sites_returns_seeded_bioon -v`
Expected: FAIL because router not mounted

- [ ] **Step 3: 实现 `/custom/sites`、`/custom/schedules`、`/custom/job-logs`**

```python
router = APIRouter(prefix="/custom", tags=["news-admin"])
```

- [ ] **Step 4: 在 `server.py` 中挂载新路由并初始化 MySQL 依赖**

Run: `pytest tests/docker/test_news_admin_api.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add deploy/docker/news_admin_router.py deploy/docker/server.py tests/docker/test_news_admin_api.py
git commit -m "feat: add news admin api"
```

## Chunk 4: 数据库驱动调度

### Task 7: 用 cron 表达式替换固定间隔环境变量

**Files:**
- Create: `deploy/docker/news_scheduler_service.py`
- Modify: `deploy/docker/bioon_news_scheduler.py`
- Modify: `tests/docker/test_bioon_news.py`
- Create: `tests/docker/test_news_scheduler_service.py`

- [ ] **Step 1: 写 cron 调度失败测试**

```python
def test_scheduler_picks_due_schedule_and_computes_next_run():
    next_run = compute_next_run("0 * * * *", "Asia/Shanghai", now)
    assert next_run > now
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/docker/test_news_scheduler_service.py::test_scheduler_picks_due_schedule_and_computes_next_run -v`
Expected: FAIL with `compute_next_run` not found

- [ ] **Step 3: 实现 `croniter` 驱动的调度服务**

```python
def compute_next_run(cron_expr: str, timezone: str, now: datetime) -> datetime:
    return croniter(cron_expr, now).get_next(datetime)
```

- [ ] **Step 4: 改造调度入口**

Replace old payload source:
- remove fixed `BIOON_NEWS_SCHEDULER_LIMIT`
- scan `crawler_schedule`
- lock by `news:schedule:{schedule_id}`

- [ ] **Step 5: 运行调度测试**

Run: `pytest tests/docker/test_news_scheduler_service.py tests/docker/test_bioon_news.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add deploy/docker/news_scheduler_service.py deploy/docker/bioon_news_scheduler.py tests/docker/test_news_scheduler_service.py tests/docker/test_bioon_news.py
git commit -m "feat: add database driven scheduler"
```

### Task 8: 调整 `supervisord` 与部署文档

**Files:**
- Modify: `deploy/docker/supervisord.conf`
- Modify: `操作方法记录/01-Docker部署与目录说明.md`
- Modify: `操作方法记录/02-手动触发操作.md`
- Modify: `操作方法记录/03-容器内定时任务操作.md`
- Modify: `操作方法记录/04-结果文件说明.md`
- Modify: `操作方法记录/05-常见问题与排障.md`

- [ ] **Step 1: 更新启动命令与环境依赖说明**

```ini
[program:news_scheduler]
command=/usr/local/bin/python /app/bioon_news_scheduler.py
```

- [ ] **Step 2: 补充 MySQL 初始化与配置管理操作文档**

Document:
- 建库建表
- 首次插入 `crawler_site`
- 首次插入 `crawler_schedule`
- 手动触发与状态查询

- [ ] **Step 3: 运行最小回归**

Run:
- `pytest tests/docker/test_news_admin_api.py tests/docker/test_news_scheduler_service.py tests/docker/test_bioon_news.py -q`
- `python -m py_compile deploy/docker/*.py tests/docker/test_news_*.py`

Expected: PASS / exit 0

- [ ] **Step 4: 提交**

```bash
git add deploy/docker/supervisord.conf 操作方法记录/*.md
git commit -m "docs: update mysql and scheduler operations"
```

## Chunk 5: 端到端验收

### Task 9: 真实容器端到端验证

**Files:**
- Modify: `操作方法记录/开发计划-生物谷资讯MySQL与配置中心改造实现.md`

- [ ] **Step 1: 准备环境**

Required env:
- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE`
- `REDIS_HOST`

- [ ] **Step 2: 启动容器并检查健康**

Run:
```bash
docker restart crawl4ai-bioon
curl http://localhost:11235/health
```

Expected: `{"status":"ok",...}`

- [ ] **Step 3: 插入 Bioon 站点与调度配置**

Run:
```bash
curl -X POST http://localhost:11235/custom/sites ...
curl -X POST http://localhost:11235/custom/schedules ...
```

- [ ] **Step 4: 手动执行一次站点抓取**

Run:
```bash
curl -X POST http://localhost:11235/custom/sites/bioon/run
```

Expected:
- `new_count > 0`
- MySQL `crawler_article` 中有数据
- `crawler_job_log` 中有记录

- [ ] **Step 5: 检查调度器执行**

Run:
```bash
docker logs --tail 100 crawl4ai-bioon
curl http://localhost:11235/custom/job-logs
```

Expected:
- 日志中出现调度成功记录
- 最新 `job_log` 状态为成功

- [ ] **Step 6: 回填开发计划**

记录：
- 实际变更文件
- 测试命令与结果
- 未覆盖风险

## 执行顺序建议

必须按以下顺序推进：
1. Chunk 1
2. Chunk 2
3. Chunk 3
4. Chunk 4
5. Chunk 5

不要跳过测试先写实现；不要先做调度再做结果入库。

## 风险控制

- 若 MySQL 初始化失败，先阻止服务进入“看似可用但实际不可写”的状态。
- 若 Redis 不可用，首版允许退化为单实例无锁执行，但必须记录 warning。
- 若站点配置缺失或规则 JSON 非法，`/custom/sites/{site_code}/run` 必须返回明确错误，不允许静默失败。
- 若 cron 非法，创建或更新调度配置时直接拒绝写入。

## 完成定义

满足以下条件才算本计划完成：
- Bioon 手动抓取结果以 MySQL 为主存储。
- 站点规则和调度配置来自 MySQL，而不是本地 JSON / 环境变量。
- 调度器按数据库 cron 执行。
- 管理 API 可增删改查站点和调度。
- 文档、测试、容器启动方式同步更新。

Plan complete and saved to `docs/superpowers/plans/2026-03-30-bioon-mysql-config-implementation-plan.md`. Ready to execute?
