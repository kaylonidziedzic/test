# CF-Gateway Wiki 📚

全面说明部署、配置、接口、常见报错、排障与最佳实践。

## 目录
- [部署与环境](#部署与环境)
- [密钥与角色](#密钥与角色)
- [运行模式](#运行模式)
- [接口详解](#接口详解)
- [前端控制台](#前端控制台)
- [日志与监控](#日志与监控)
- [浏览器池与过盾](#浏览器池与过盾)
- [常见报错与排障](#常见报错与排障)
- [安全建议](#安全建议)

## 部署与环境
- 依赖：Python 3.9、Chrome（镜像内置 google-chrome-stable）、Docker+Compose（推荐）。
- 快速启动：
  ```bash
  # 生产
  docker-compose up -d
  # 开发（含静态挂载+热重载）
  docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d
  ```
- 持久化：`data/`（密钥、缓存 DB），`logs/`（日志）。
- 健康检查：`GET /health` 或 Docker healthcheck。

## 密钥与角色
- 优先级：`API_KEYS_JSON`（env） > `data/api_keys.json`（文件） > `API_KEY`（回退）。
- 文件示例：
  ```json
  [
    {"user": "owner", "key": "strong-admin", "role": "admin"},
    {"user": "client", "key": "client-key", "role": "user"}
  ]
  ```
- 角色：`admin` 可登录控制台/管理用户；`user` 仅可调用代理/测试，不能登录控制台。
- 鉴权：Header `X-API-KEY`（默认），或 Query `?key=`（/raw、/reader、SSE）。

## 运行模式
- 生产：`docker-compose.yml`（入口 `python main.py`）。
- 开发：`docker-compose.override.yml`（`uvicorn --reload`，挂载 `./static`）。
- 端口：默认 8000，配置于 `config.py:PORT` 或环境变量。

## 接口详解
### 健康
- `GET /health` → `{"status":"healthy","service":"CF-Gateway-Pro"}`

### 控制台（需 admin）
- `GET /api/dashboard/status` → uptime、version、current_user
- `GET /api/dashboard/stats` → 浏览器池、缓存、请求统计
- `GET /api/dashboard/system` → CPU/内存/磁盘
- `GET /api/dashboard/time-series` → 成功率/耗时趋势
- `GET /api/dashboard/history?limit=20&user=xx` → 请求历史
- 日志：
  - `GET /api/dashboard/logs?limit=200&user=xx` → `{all:[...], user:[...]}`
  - `GET /api/dashboard/logs/stream?key=...&user=xx` → SSE 增量日志
- 配置：
  - `GET /api/dashboard/config`
  - `PUT /api/dashboard/config`（运行时生效，重启恢复）
- 缓存：
  - `POST /api/dashboard/cache/clear` `{domain?}` → 清理指定/全部
- 浏览器池：
  - `POST /api/dashboard/browser-pool/restart` → 重启池
- 过盾：
  - `POST /api/dashboard/test` `{url, mode?, force_refresh?}` → 单次结果（cookies、ua、duration）
  - `POST /api/dashboard/test/batch` `{urls[], mode?}` → 批量结果
- 用户/密钥（仅 admin）：
  - `GET /api/dashboard/users`
  - `POST /api/dashboard/users` `{user, role}` → 自动生成 key
  - `DELETE /api/dashboard/users/{username}`
  - `POST /api/dashboard/users/{username}/rotate`

### 代理/阅读（user/admin 均可）
- `POST /v1/proxy`
  - 体：`{url, method?, headers?, data?, json_body?, data_encoding?}`
  - 回：`{status, url, headers, cookies, encoding, text}`
- `GET /raw?url=...&key=...` → 原始二进制（保持 content-type/status）
- `GET /reader?url=...&key=...` → 阅读 HTML
- `POST /reader?url=...&key=...` → 根据 content-type 处理 form/raw，返回 HTML

## 前端控制台
- 地址：`http://<IP>:8000/dashboard`，仅 admin 可登录。
- 功能：总览、日志（全局/用户双栏）、实例池、缓存、配置、操作（测试/批量）、用户/密钥管理。
- 数据刷新：SSE 优先，断线回退轮询；可手动暂停自动刷新。
- 日志过滤：顶部用户筛选 + 级别筛选；右栏仅显示选定用户日志。

## 日志与监控
- 文件：`logs/server.log`，格式含 `[user:xxx]`。
- 后端：SSE `/logs/stream` 实时推送；轮询 `/logs` 回传 `{all,user}`。
- 看门狗：`WATCHDOG_INTERVAL`，输出浏览器池状态与内存。

## 浏览器池与过盾
- 配置：`BROWSER_POOL_MIN/MAX/IDLE_TIMEOUT`，`MEMORY_LIMIT_MB` 超限自动重启。
- 指纹：`FINGERPRINT_ENABLED` 控制 Canvas/WebGL/Audio 随机化。
- 过盾函数：`core.solver.solve_turnstile`，`/test`/`/test/batch` 调用。
- 典型耗时：已将前端超时放宽至 60s，批量测试分片执行（每批 3 个）。

## 常见报错与排障
- 403 / 登录失败：使用 admin key；env/file 存在时 `API_KEY` 回退失效。
- 日志空白/卡死：强刷；检查 SSE 被反代阻断时回退轮询；直接查看 `logs/server.log`。
- 过盾超时：暂停自动刷新或增大浏览器池；确认目标站点可访问。
- Chrome 启动失败：检查宿主机权限/内核；`--no-sandbox` 已默认启用。
- 缓存异常：`POST /api/dashboard/cache/clear`；必要时备份/删除 `data/cache.db`。
- 默认 key 仍可登录：确认未在环境里保留旧 `API_KEY`；`get_all_entries()` 已优先 env/file。

## 安全建议
- 强随机密钥，定期轮换；限制 admin key 暴露范围（降低泄露后横向风险）。
- 生产前删除 compose `version` 警告、加防火墙与反代限速（防扫描、防爆破）。
- 挂载独立卷存放 `data/`，定期备份密钥与缓存（防止容器重建或磁盘损坏导致数据丢失）。

## 建议与不建议
### 建议
- 使用 `API_KEYS_JSON` 或 `data/api_keys.json` 管理多密钥（原因：支持多用户隔离与角色控制，便于轮换）。
- 生产关闭默认 `API_KEY`（原因：默认值弱且容易被误用，存在安全隐患）。
- 开启 SSE（默认）并保留轮询回退（原因：降低请求频次，提升实时性，同时兼容代理阻断场景）。
- 运行时调整配置但持久化前记录原始值（原因：运行时修改重启会恢复，记录可避免配置漂移）。
- 过盾批量测试时分片（已实现）并监控耗时（原因：减少单次超长阻塞，便于定位慢目标）。
- 定期清理/压缩日志（原因：长期运行日志体积膨胀，影响磁盘与检索性能）。

### 不建议
- 在生产中直接使用 `HEADLESS=True` 且禁用指纹随机化（原因：更易被目标站点识别为自动化流量）。
- 将 `static/index.html` 打包进后端镜像后再频繁改动镜像（原因：前端与后端耦合，修改成本高；开发可用挂载方式即时生效）。
- 在高并发场景将浏览器池设过大且无资源限制（原因：Chrome 进程占用高，易触发 OOM 或宿主机卡死）。
- 手动修改 `data/cache.db`（原因：容易破坏 SQLite 索引/数据，建议通过 API 清理或备份后重建）。
