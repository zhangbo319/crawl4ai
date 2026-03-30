# Docker 部署与目录说明

## 目标理解
当前方案基于已有 Docker 服务扩展，不新起第二个 Web 服务。生物谷抓取能力直接挂到现有 `11235` 端口的 FastAPI 中。

## 改动范围
- 业务接口模块：`deploy/docker/bioon_news.py`
- 规则文件：`deploy/docker/bioon_news_rules.json`
- MySQL 管理器：`deploy/docker/news_mysql.py`
- 仓储层：`deploy/docker/news_repositories.py`
- 配置管理接口：`deploy/docker/news_admin_router.py`
- 调度服务：`deploy/docker/news_scheduler_service.py`
- 容器内定时脚本：`deploy/docker/bioon_news_scheduler.py`
- 服务挂载：`deploy/docker/server.py`
- 进程管理：`deploy/docker/supervisord.conf`

## 目录说明
- 文档目录：`操作方法记录/`
- 运行数据目录：`runtime/bioon_news/`
- 最近结果：`runtime/bioon_news/latest/news_latest.json`
- 历史归档：`runtime/bioon_news/archive/YYYY-MM-DD/news_*.json`
- 状态文件：`runtime/bioon_news/state/run_state.json`
- 去重索引：`runtime/bioon_news/state/seen_urls.json`
- 可选原始页面：`runtime/bioon_news/raw/`

## Docker 使用建议
如果你希望结果在容器重启后仍保留，建议把 `runtime/` 挂载到宿主机卷。代码默认使用当前工作目录下的 `runtime/bioon_news/`，也可以通过环境变量 `BIOON_NEWS_DATA_DIR` 覆盖；旧变量名 `BIOON_NEWS_BASE_DIR` 也兼容。

## MySQL 环境变量
```bash
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=secret
MYSQL_DATABASE=crawl4ai_news
MYSQL_MINSIZE=1
MYSQL_MAXSIZE=5
```

当前抓取结果、站点配置、调度配置、任务日志都以 MySQL 为主存储。首次运行前需要保证目标数据库已创建，服务会自动执行核心表初始化。

如果 MySQL 安装在宿主机、而抓取服务运行在 Docker 容器内，`MYSQL_HOST` 不应继续写 `localhost`，应改为：

```bash
MYSQL_HOST=host.docker.internal
MYSQL_PORT=3306
MYSQL_USER=zhangbo
MYSQL_PASSWORD=zhangbo
MYSQL_DATABASE=crawl4ai_news
```

原因是容器内的 `localhost` 指向容器自身，不是宿主机。

## 规则文件说明
- 默认规则文件：`deploy/docker/bioon_news_rules.json`
- 可覆盖环境变量：`BIOON_NEWS_RULES_FILE`
- 适合放在规则文件里的内容：
  - 首页和详情页 CSS 选择器
  - 默认主分类、默认栏目回退值
  - 请求超时、`User-Agent`

如果只是在适配生物谷页面结构变化，优先修改规则文件，不要先改 `bioon_news.py`。

## 风险点
- 不挂载卷时，容器重建会丢失抓取结果与去重状态。
- 当前方案依赖服务内 `supervisord` 启动 Gunicorn 与调度脚本，修改容器启动方式时要同步检查。
- 如果数据库在宿主机，而容器内仍配置 `MYSQL_HOST=localhost`，连接一定会失败。

## 验证方式
1. 访问 `GET /health`
2. 访问 `GET /custom/bioon-news/status`
3. 触发一次手动抓取，确认 `runtime/bioon_news/` 自动生成
4. 如修改了规则文件，重启容器后再触发一次抓取，确认新规则已生效
5. 访问 `GET /custom/sites` 与 `GET /custom/schedules`，确认数据库配置接口可用
