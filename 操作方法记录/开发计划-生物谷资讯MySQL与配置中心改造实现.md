# 开发计划-生物谷资讯MySQL与配置中心改造实现
创建时间：2026-03-30
当前状态：已完成
执行目标：按已确认的实施计划完成 MySQL 持久化、数据库配置中心与数据库驱动调度的代码改造。
步骤：[x] 读取设计与实施计划  [x] 完成 MySQL 配置与建表  [x] 完成结果入库与日志记录  [x] 完成站点配置与调度 API  [x] 完成数据库驱动调度  [x] 更新文档与代码级验证  [x] 真实 MySQL 联调验证
改动明细：
- 新增 `deploy/docker/news_mysql.py`，实现 MySQL 配置解析、连接池和核心表初始化。
- 新增 `deploy/docker/news_repositories.py`，封装站点、调度、文章、任务日志仓储。
- 新增 `deploy/docker/news_schemas.py`、`deploy/docker/news_admin_router.py`、`deploy/docker/news_scheduler_service.py`，实现数据库配置接口与 cron 调度服务。
- 修改 `deploy/docker/bioon_news.py`，使 Bioon 抓取结果以仓储入库为主，本地 JSON 仅保留为调试输出。
- 修改 `deploy/docker/bioon_news_scheduler.py`、`deploy/docker/server.py`，接入数据库驱动调度与管理接口。
- 修改 `deploy/docker/bioon_news.py`、`deploy/docker/news_schemas.py`、`deploy/docker/news_scheduler_service.py`，补齐 `trigger_type` 与 `schedule_id` 透传，修正调度触发日志被误记为 `manual` 的问题。
- 新增 `tests/docker/test_news_mysql.py`、`tests/docker/test_news_admin_api.py`、`tests/docker/test_news_scheduler_service.py`，并扩展 `tests/docker/test_bioon_news.py`。
- 更新 `操作方法记录/00-05`，同步 MySQL 主存储和数据库配置中心的使用方式。
校验结果：
- 执行 `/Users/zhangbo/work/INKE/study/crawl4ai/.venv/bin/python -m pytest tests/docker/test_news_mysql.py tests/docker/test_bioon_news.py tests/docker/test_news_admin_api.py tests/docker/test_news_scheduler_service.py -q`，结果：`17 passed in 0.33s`。
- 执行 `/Users/zhangbo/work/INKE/study/crawl4ai/.venv/bin/python -m py_compile deploy/docker/news_mysql.py deploy/docker/news_repositories.py deploy/docker/news_schemas.py deploy/docker/news_scheduler_service.py deploy/docker/news_admin_router.py deploy/docker/bioon_news.py deploy/docker/bioon_news_scheduler.py deploy/docker/server.py tests/docker/test_news_mysql.py tests/docker/test_bioon_news.py tests/docker/test_news_admin_api.py tests/docker/test_news_scheduler_service.py`，结果：通过。
- 使用本机 MySQL `127.0.0.1:3306 / zhangbo / zhangbo` 真实联调，确认 `crawl4ai_news` 库已建表，`crawler_site=1`、`crawler_article=16`、`crawler_schedule=1`、`crawler_job_log` 持续写入。
- 重启 `crawl4ai-bioon` 容器后，执行 `GET /health`、`GET /custom/sites`、`GET /custom/sites/bioon/status`、`POST /custom/sites/bioon/run` 均成功。
- 人工将 `crawler_schedule.next_run_at` 调整为到期后，容器日志出现 `[bioon-news-scheduler] trigger success`，数据库最新任务日志为 `trigger_type=scheduler`、`schedule_id=1`，确认调度链路与日志语义均正确。
