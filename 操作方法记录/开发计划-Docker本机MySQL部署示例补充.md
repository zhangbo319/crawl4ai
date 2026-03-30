# 开发计划-Docker本机MySQL部署示例补充
创建时间：2026-03-30
当前状态：已完成
执行目标：补齐基于宿主机 MySQL 的 `.env`、`docker run` 和 `docker compose` 使用示例，便于直接部署复用。
步骤：[x] 读取现有 Docker 与 MySQL 文档  [x] 补充 `.llm.env.example` 示例  [x] 补充操作文档  [x] 生成本地 `.llm.env` 实际配置  [x] 校验文档内容
改动明细：
- 新增 `操作方法记录/06-本机MySQL部署示例.md`，集中提供 `.llm.env`、`docker run`、`docker compose` 和验证命令。
- 更新 `deploy/docker/.llm.env.example`，补充宿主机 MySQL 场景和调度器环境变量示例。
- 更新 `操作方法记录/01-Docker部署与目录说明.md`，补充容器内误用 `localhost` 的风险提示。
- 更新项目根目录 `.llm.env`，写入当前机器的 MySQL 连接与调度器默认配置。
校验结果：
- 执行 `sed -n '1,240p' deploy/docker/.llm.env.example`，确认示例变量已补充。
- 执行 `sed -n '1,240p' 操作方法记录/06-本机MySQL部署示例.md`，确认部署命令与校验命令已写入。
- 执行 `sed -n '1,240p' .llm.env`，确认当前机器的 `MYSQL_*` 与 `BIOON_NEWS_SCHEDULER_*` 配置已写入。
