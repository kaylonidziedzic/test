# CF-Gateway 🛡️🚀

Cloudflare Turnstile 过盾、代理与可视化管理一体化方案。基于 FastAPI + DrissionPage + curl_cffi，提供统一代理、阅读模式与可视化控制台（Vue 单页，SSE 实时）。

> 👉 更多操作手册/FAQ 见 `docs/WIKI.md`

## ✨ 特性
- 🧠 自动过盾：内置浏览器池 + 指纹随机化，`/test`/`/test/batch` 一键验证。
- 🔒 多用户密钥：`data/api_keys.json` / `API_KEYS_JSON` 配置；控制台仅限 `admin`。
- 📊 可视化：监控、实例池、缓存、配置、日志双栏（全局/用户），SSE 优先。
- 🧰 多协议代理：JSON 代理 `/v1/proxy`，原始 `/raw`，阅读 `/reader`。
- 🛠️ 运行时配置：浏览器池/指纹/内存/缓存时效在线调整（重启恢复默认）。

## 🏗️ 结构
```
.
├── main.py                    # FastAPI 入口
├── routers/                   # dashboard / health / proxy / raw / reader
├── services/                  # proxy_service, api_key_store, cache_service
├── core/                      # 浏览器池、过盾 solver
├── schemas/                   # Pydantic 模型
├── utils/                     # 日志、响应构造
├── static/                    # 前端 Vue 单页
├── data/                      # api_keys.json, cache.db 等持久化
├── Dockerfile                 # 生产镜像（含 Chrome）
├── docker-compose*.yml        # 部署与本地开发（override 启用热重载）
└── docs/STRUCTURE.md          # 结构说明
```

## 🚀 快速上手
1. 配置密钥（推荐）  
   `data/api_keys.json`：
   ```json
   [
     {"user": "owner", "key": "请改为强随机", "role": "admin"},
     {"user": "client", "key": "请改为随机", "role": "user"}
   ]
   ```
   或环境变量：`API_KEYS_JSON='[{"user":"owner","key":"xxx","role":"admin"}]'`  
   若 env/file 均为空才回退 `config.py` 的 `API_KEY`。

2. 启动
   ```bash
   docker-compose up -d                # 生产
   # 本地热重载（含前端挂载）：
   docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d
   ```

3. 访问控制台  
   `http://<主机IP>:8000/dashboard`，使用 admin key 登录。

4. 前端开发  
   `static` 已挂载，改动刷新即见；后端 `uvicorn --reload` 自动重载。

## 🔑 鉴权与角色
- Header：`X-API-KEY: <key>`（控制台/代理默认）
- Query：`?key=<key>`（/raw、/reader、SSE 兼容）
- 角色：`admin` 可登录控制台与用户管理；`user` 仅可调用业务 API。

## 🧭 核心接口（摘录）
> 所有返回均为 JSON，除 `/raw`/`/reader` 直接回源内容。

- 健康：`GET /health` → `{status, service}`
- 控制台（需 admin）：
  - `GET /api/dashboard/status` → uptime、version、current_user
  - `GET /api/dashboard/stats` → 请求统计、浏览器池、缓存
  - `GET /api/dashboard/system` → CPU/内存/磁盘
  - `GET /api/dashboard/time-series`
  - `GET /api/dashboard/history?limit=20&user=xx`
  - 日志：`GET /api/dashboard/logs?limit=200&user=xx` → `{all, user}`；SSE `/logs/stream?key=...&user=xx`
  - 配置：`GET/PUT /api/dashboard/config`（运行时）  
  - 缓存：`POST /api/dashboard/cache/clear` `{domain?}`  
  - 浏览器池：`POST /api/dashboard/browser-pool/restart`
  - 过盾：`POST /api/dashboard/test` `{url, mode?, force_refresh?}`；`POST /api/dashboard/test/batch` `{urls[], mode?}`
  - 用户：`GET/POST/DELETE /api/dashboard/users`，`POST /api/dashboard/users/{u}/rotate`

- 代理/阅读：
  - `POST /v1/proxy` (Header Key)  
    体：`{url, method?, headers?, data?, json_body?, data_encoding?}`  
    返回：`{status, url, headers, cookies, encoding, text}`
  - `GET /raw?url=...&key=...` → 原始二进制
  - `GET /reader?url=...&key=...` → 阅读 HTML
  - `POST /reader?url=...&key=...` → form/raw 转发再返回 HTML

更多示例与字段详解见 `docs/WIKI.md`。

## 🛡️ 运行机制
- 浏览器池：最小/最大实例、空闲回收、内存阈值重启；看门狗按 `WATCHDOG_INTERVAL` 轮询。
- 缓存：SQLite (`data/cache.db`)，过期 `COOKIE_EXPIRE_SECONDS`。
- 日志：`logs/server.log`（带 `[user:xxx]`），SSE/轮询二选一。

## 🧰 关键配置（config.py）
- `API_KEYS_JSON` / `API_KEYS_FILE` / `API_KEY`（回退）  
- `PORT`、`HEADLESS`、`BROWSER_POOL_MIN/MAX/IDLE_TIMEOUT`  
- `MEMORY_LIMIT_MB`、`WATCHDOG_INTERVAL`、`FINGERPRINT_ENABLED`

## 📦 部署提示
- 镜像已内置 Chrome；Linux 建议保留 `--no-sandbox`。
- 生产请：移除 compose `version` 警告、持久化 `data/`、调整内存限制 (>=2G)。
- 健康检查：`healthcheck.py` 已集成。

## 🐛 常见问题
- 登录 403：确认使用 admin key；env/file 存在时默认 `API_KEY` 不再生效。
- 日志空白：强刷；检查代理对 SSE 的限制，必要时查看 `logs/server.log`。
- 过盾超时：前端已 60s 超时，仍超时可暂停自动刷新/提升浏览器池规模。
- Chrome 启动失败：核查宿主机权限/内核，必要时复用 `--no-sandbox`。
- 缓存异常：用 `/api/dashboard/cache/clear`；损坏时备份/删除 `data/cache.db`。

## 📚 Wiki
- 详尽接口样例、错误排查、Nginx 反代、SSE 配置等见：`docs/WIKI.md`

## 🤝 贡献
- 保持接口签名与行为不变；中文注释关键逻辑；避免引入长耗时任务。
- 欢迎 Issue/PR，附场景、复现与期望。
