# 开发计划-docker-compose本地部署收敛
创建时间：2026-03-30
当前状态：已完成
执行目标：把当前 Bioon/MySQL 本地 Docker 运行方式收敛为可复用的 `docker compose` 方案。
步骤：[x] 读取现有 compose 与部署文档  [x] 新增本地 compose 覆盖文件  [x] 更新操作文档  [x] 使用 compose 重建本地服务  [x] 验证接口与 MySQL 联通
改动明细：
- 新增 `docker-compose.bioon-local.yml`，把当前 Bioon/MySQL 本地部署收敛为 compose 覆盖方案。
- 更新 `操作方法记录/06-本机MySQL部署示例.md`，改为推荐双 compose 文件启动。
- 在本地 compose 覆盖文件里补充启动时安装 `aiomysql`、`croniter`，兼容旧基础镜像缺少新增依赖的问题。
校验结果：
- 执行 `docker compose -f docker-compose.yml -f docker-compose.bioon-local.yml config`，确认 compose 合成结果包含 `host.docker.internal`、`./runtime:/app/runtime` 和本地覆盖命令。
- 执行 `docker compose -f docker-compose.yml -f docker-compose.bioon-local.yml up -d`，成功拉起本地 compose 容器。
- 执行 `docker compose -f docker-compose.yml -f docker-compose.bioon-local.yml ps`，结果：容器 `38e0ccc9e3df_crawl4ai-bioon` 为 `healthy`。
- 执行 `curl http://localhost:11235/health` 与 `curl http://localhost:11235/custom/sites/bioon/status`，结果：接口正常返回。
- 执行 MySQL 查询 `SELECT id, trigger_type, schedule_id, status FROM crawler_job_log ORDER BY id DESC LIMIT 5;`，结果：最近任务均为 `scheduler / success`。
