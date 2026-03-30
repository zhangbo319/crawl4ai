# 生物谷资讯 MySQL 与配置中心改造设计

## 1. 背景

当前实现已具备以下能力：
- `deploy/docker/bioon_news.py` 支持 Bioon 首页与详情页抓取。
- `deploy/docker/bioon_news_rules.json` 提供单站点规则文件。
- `deploy/docker/bioon_news_scheduler.py` 通过环境变量实现固定间隔调度。
- 结果目前主要落到 `runtime/bioon_news/` 下的 JSON 文件。

这套实现适合单站点验证，但不适合继续扩展到多站点、数据库持久化与动态调度。

## 2. 目标与边界

### 2.1 目标
- 抓取结果改为持久化到 MySQL，数据库地址、账号、密码支持配置。
- 站点规则 JSON、调度 cron 表达式、启停开关改为数据库配置。
- 保持当前 Docker API 触发模式，兼容手动触发与定时触发。
- 以 Bioon 为首个站点完成落地，为后续更多网站复用同一套框架。

### 2.2 非目标
- 首版不做通用低代码爬虫平台。
- 首版不承诺无代码适配任意网站。
- 首版不引入复杂消息队列。

## 3. 总体方案

推荐采用“配置中心 + 执行器 + 调度器 + 结果存储”四层结构。

- 配置中心：MySQL 中维护站点配置与调度配置。
- 执行器：根据 `site_code` 读取站点配置，执行列表抓取、详情抓取、字段映射、去重写库。
- 调度器：周期扫描数据库中的调度任务，按 cron 触发执行器。
- 结果存储：文章结果、任务日志统一入 MySQL；JSON 文件仅保留为调试或临时导出能力。

## 4. 数据模型

### 4.1 `crawler_site`
- `id`
- `site_code`，唯一，例如 `bioon`
- `site_name`
- `base_url`
- `entry_url`
- `rule_json`
- `default_config_json`
- `is_enabled`
- `created_at`
- `updated_at`

用途：保存站点抓取入口、页面规则、默认分类、请求参数等。

### 4.2 `crawler_schedule`
- `id`
- `site_id`
- `cron_expr`
- `timezone`
- `is_enabled`
- `last_run_at`
- `next_run_at`
- `last_status`
- `last_error`
- `created_at`
- `updated_at`

用途：保存数据库驱动的调度配置。

### 4.3 `crawler_article`
- `id`
- `site_id`
- `title`
- `url`
- `publish_time`
- `desc_abs`
- `content`
- `logo`
- `resource`
- `primary_cls`
- `secondary_cls`
- `tags_json`
- `fingerprint`
- `raw_json`
- `crawl_time`
- `updated_at`

约束建议：
- 唯一键：`site_id + url`
- 索引：`publish_time`、`fingerprint`

### 4.4 `crawler_job_log`
- `id`
- `site_id`
- `schedule_id`
- `trigger_type`
- `started_at`
- `finished_at`
- `status`
- `processed_count`
- `new_count`
- `failed_count`
- `error_message`
- `result_snapshot_json`

用途：记录每次手动或定时执行的完整结果。

## 5. API 设计

### 5.1 站点配置
- `POST /custom/sites`
- `GET /custom/sites`
- `GET /custom/sites/{site_code}`
- `PUT /custom/sites/{site_code}`
- `POST /custom/sites/{site_code}/enable`
- `POST /custom/sites/{site_code}/disable`

### 5.2 调度配置
- `POST /custom/schedules`
- `GET /custom/schedules`
- `PUT /custom/schedules/{id}`
- `POST /custom/schedules/{id}/enable`
- `POST /custom/schedules/{id}/disable`

### 5.3 执行与结果
- `POST /custom/sites/{site_code}/run`
- `GET /custom/sites/{site_code}/status`
- `GET /custom/sites/{site_code}/articles`
- `GET /custom/job-logs`
- `GET /custom/job-logs/{id}`

## 6. 调度设计

当前固定间隔调度脚本需要升级为“数据库驱动调度器”。

推荐首版实现：
- 在当前 Docker 服务中保留一个轻量后台调度进程。
- 调度进程固定周期扫描 `crawler_schedule`。
- 对到期且启用的任务进行触发。
- 执行前尝试加锁，避免重复执行。
- 执行后回写 `last_run_at`、`next_run_at`、`last_status`、`last_error`。

cron 规则建议：
- 使用标准 5 段 cron 表达式。
- 默认时区 `Asia/Shanghai`。
- 修改 cron 后立即重算 `next_run_at`。

## 7. 存储职责划分

### 7.1 MySQL
- 站点配置
- 调度配置
- 抓取结果
- 任务日志

### 7.2 Redis
- 运行时分布式锁
- 可选的短期状态缓存

说明：如果当前只跑单实例，可先把锁做成可选能力，但接口上应预留。

## 8. 代码改造方向

建议不要继续以 `bioon_news.py` 为唯一业务入口，而是抽出以下模块：

- `site_repository`
  负责读写站点配置与调度配置。
- `article_repository`
  负责结果入库与去重查询。
- `job_log_repository`
  负责任务日志记录。
- `site_executor`
  负责通用执行流程。
- `bioon_executor`
  作为第一个站点执行器，实现 Bioon 页面规则映射。
- `scheduler_service`
  负责数据库任务扫描与触发。

## 9. 分阶段实施

### 第一期：结果入 MySQL
- 保留当前 Bioon 抓取逻辑。
- 将结果写入 `crawler_article`。
- JSON 文件降级为调试输出。

### 第二期：站点配置入库
- 新建 `crawler_site`。
- 将当前 `bioon_news_rules.json` 和默认配置迁入数据库。
- 按 `site_code` 读取规则执行。

### 第三期：调度配置入库
- 新建 `crawler_schedule`。
- 用 cron 与启停开关替换当前环境变量调度。
- 调度器按数据库任务表执行。

### 第四期：抽象多站点执行器
- Bioon 作为首个 `site_code` 执行器。
- 新站点按相同接口接入。

## 10. 风险点

- 多实例部署时出现重复执行。
- 规则 JSON 入库后缺少结构校验。
- cron 表达式与时区配置错误导致任务不执行。
- 站点差异增大后，单一执行器接口可能需要再次细分。

## 11. 验证标准

设计阶段验收：
- 文档覆盖表结构、API、调度、迁移顺序。
- 能直接指导实现拆分，不依赖口头补充。

实现阶段验收：
- 手动触发可入库文章结果。
- 调度任务可按数据库 cron 触发。
- 改数据库中的规则 JSON 后，重启服务即可生效。
- `crawler_job_log` 能完整反映每次执行结果。

## 12. 决策结论

本次改造可行，推荐按“Bioon 单站点先落地、配置中心先建底座”的方式推进。  
当前最合理的实施范围是前三期，第四期作为后续演进目标进入开发计划。
