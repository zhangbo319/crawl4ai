# 本机 MySQL 部署示例

## 目标理解
当 Crawl4AI 跑在 Docker 容器里、MySQL 安装在宿主机时，需要把数据库连接明确配置到宿主机地址，而不是容器内的 `localhost`。

## 推荐 `.llm.env`
在项目根目录创建 `.llm.env`，至少加入下面这些配置：

```bash
MYSQL_HOST=host.docker.internal
MYSQL_PORT=3306
MYSQL_USER=zhangbo
MYSQL_PASSWORD=zhangbo
MYSQL_DATABASE=crawl4ai_news
MYSQL_MINSIZE=1
MYSQL_MAXSIZE=5

BIOON_NEWS_SCHEDULER_ENABLED=true
BIOON_NEWS_SCHEDULER_INTERVAL_SECONDS=60
```

如果你后续改为“手动触发为主，关闭容器内自动兜底”，把 `BIOON_NEWS_SCHEDULER_ENABLED=false` 即可。

## `docker run` 示例
```bash
docker run -d \
  --name crawl4ai-bioon \
  -p 11235:11235 \
  --add-host=host.docker.internal:host-gateway \
  --env-file .llm.env \
  -v "$(pwd)/deploy/docker:/app" \
  -v "$(pwd)/runtime:/app/runtime" \
  crawl4ai-local:af648e1
```

说明：
- `--add-host=host.docker.internal:host-gateway` 用于让容器访问宿主机 MySQL
- `deploy/docker` 挂载后，直接使用当前仓库里的定制代码
- `runtime` 挂载后，抓取结果和状态文件会保留在宿主机

## `docker compose` 示例
如果你使用项目自带的 `docker-compose.yml`，推荐命令：

```bash
docker compose up -d --build
```

前提：
- 项目根目录已有 `.llm.env`
- `.llm.env` 里已经写入上面的 MySQL 配置

如果你的 Docker 环境无法自动解析 `host.docker.internal`，先确认宿主机支持 `host-gateway`；不支持时，改成宿主机实际局域网 IP。

## 启动后验证
```bash
curl http://localhost:11235/health
curl http://localhost:11235/custom/sites
curl http://localhost:11235/custom/sites/bioon/status
mysql -h127.0.0.1 -P3306 -uzhangbo -pzhangbo -D crawl4ai_news -e "SHOW TABLES;"
mysql -h127.0.0.1 -P3306 -uzhangbo -pzhangbo -D crawl4ai_news -e "SELECT id, trigger_type, schedule_id, status FROM crawler_job_log ORDER BY id DESC LIMIT 5;"
```

## 常见问题
- 容器里配 `MYSQL_HOST=localhost` 连不上宿主机 MySQL：改为 `host.docker.internal`
- 能手动抓取但看不到定时日志：检查 `BIOON_NEWS_SCHEDULER_ENABLED`，并查看 `docker logs crawl4ai-bioon`
- 表没自动创建：确认 MySQL 用户对 `crawl4ai_news` 有建表权限
