# CF-Gateway Pro

<div align="center">

![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-green.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)
![License](https://img.shields.io/badge/license-MIT-yellow.svg)

**高性能 Cloudflare 绕过网关** | 智能过盾 | 代理服务 | 可视化管理

[快速开始](#-快速开始) · [API 文档](#-api-文档) · [功能特性](#-功能特性) · [Wiki](docs/WIKI.md)

</div>

---

## 功能特性

<table>
<tr>
<td width="50%">

### 核心能力
- **智能过盾** - 自动绕过 Cloudflare Turnstile 验证
- **Cookie 复用** - 高效缓存，减少过盾次数
- **浏览器直读** - 实时渲染确保成功率
- **智能降级** - Cookie 失效自动切换模式

</td>
<td width="50%">

### 高级特性
- **域名智能学习** - 自动识别最佳访问策略
- **Cookie 自动刷新** - 后台提前刷新即将过期凭证
- **代理支持** - IP 池轮换，突破访问限制
- **规则系统** - 可视化配置爬虫规则

</td>
</tr>
</table>

### 管理能力

| 功能 | 说明 |
|------|------|
| **可视化控制台** | Vue 单页应用，SSE 实时数据推送 |
| **多用户权限** | admin/user 角色分离，API Key 管理 |
| **健康监控** | Redis、浏览器池、缓存状态全面监控 |
| **运行时配置** | 在线调整参数，无需重启服务 |

---

## 快速开始

### 1. 配置密钥

创建 `data/api_keys.json`：

```json
[
  {"user": "admin", "key": "your-secure-admin-key-here", "role": "admin"},
  {"user": "client", "key": "your-secure-client-key", "role": "user"}
]
```

### 2. 启动服务

```bash
# 生产环境
docker-compose up -d

# 开发环境（热重载）
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d
```

### 3. 访问服务

| 地址 | 说明 |
|------|------|
| `http://localhost:8000/dashboard` | 管理控制台（需 admin 权限） |
| `http://localhost:8000/docs` | Swagger API 文档 |
| `http://localhost:8000/redoc` | ReDoc API 文档 |
| `http://localhost:8000/health` | 健康检查 |

---

## API 文档

### 代理接口

```bash
# JSON 代理请求
curl -X POST http://localhost:8000/v1/proxy \
  -H "X-API-KEY: your-key" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# 原始内容
curl "http://localhost:8000/raw?url=https://example.com&key=your-key"

# 阅读模式
curl "http://localhost:8000/reader?url=https://example.com&key=your-key"
```

### 规则系统

```bash
# 创建规则
curl -X POST http://localhost:8000/v1/rules \
  -H "X-API-KEY: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "示例规则",
    "target_url": "https://example.com/search?q={keyword}",
    "mode": "cookie",
    "selectors": {"title": "h1", "content": ".article"}
  }'

# 执行规则 (Permlink)
curl "http://localhost:8000/v1/run/rule_id?keyword=test&key=your-key"
```

### 健康检查

```bash
# 基础检查
curl http://localhost:8000/health

# 就绪检查（含组件状态）
curl http://localhost:8000/health/ready

# 存活检查（Kubernetes Liveness）
curl http://localhost:8000/health/live
```

---

## 项目结构

```
cf-gateway/
├── main.py                 # FastAPI 入口，看门狗任务
├── config.py               # 配置管理
│
├── routers/                # API 路由
│   ├── dashboard.py        # 管理面板 API
│   ├── health.py           # 健康检查
│   ├── proxy.py            # JSON 代理
│   ├── raw.py              # 原始内容
│   ├── reader.py           # 阅读模式
│   └── runner.py           # 规则执行
│
├── services/               # 业务服务
│   ├── proxy_service.py    # 代理调度层
│   ├── cache_service.py    # 凭证缓存（SQLite/Redis）
│   ├── domain_intelligence.py  # 域名智能学习
│   ├── rule_service.py     # 规则管理
│   └── api_key_store.py    # 密钥管理
│
├── core/                   # 核心组件
│   ├── browser_pool.py     # 浏览器池
│   ├── solver.py           # 过盾逻辑
│   └── fetchers/           # 请求器（Cookie/Browser）
│
├── static/                 # 前端资源
│   ├── index.html          # Vue 单页应用
│   └── js/                 # JavaScript 模块
│
├── data/                   # 持久化数据
│   ├── api_keys.json       # API 密钥
│   ├── config.json         # 运行时配置
│   └── proxies.txt         # 代理列表
│
└── docker-compose.yml      # Docker 部署配置
```

---

## 配置说明

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | 8000 | 服务端口 |
| `REDIS_URL` | redis://localhost:6379 | Redis 连接 |
| `COOKIE_EXPIRE_SECONDS` | 1800 | Cookie 过期时间（秒） |
| `BROWSER_POOL_MIN` | 1 | 浏览器池最小实例 |
| `BROWSER_POOL_MAX` | 3 | 浏览器池最大实例 |
| `MEMORY_LIMIT_MB` | 1500 | 内存限制（MB） |
| `WATCHDOG_INTERVAL` | 300 | 看门狗检查间隔（秒） |

### 运行时配置

通过 Dashboard 或 API 可在线调整：

```bash
curl -X PUT http://localhost:8000/api/dashboard/config \
  -H "X-API-KEY: admin-key" \
  -H "Content-Type: application/json" \
  -d '{
    "cookie_expire_seconds": 3600,
    "browser_pool_max": 5
  }'
```

---

## 智能特性

### 域名智能学习

系统自动跟踪各域名的访问成功率：

- **Cookie 模式失败率 > 50%** → 自动切换到 Browser 模式
- **统计数据 24 小时过期** → 定期重新评估
- **Dashboard 可视化** → 查看各域名推荐策略

```bash
# 查看域名智能统计
curl http://localhost:8000/api/dashboard/domain-intelligence \
  -H "X-API-KEY: admin-key"
```

### Cookie 自动刷新

后台看门狗自动维护凭证新鲜度：

- 检测即将过期（5分钟内）的凭证
- 自动提前刷新，避免请求失败
- 每轮最多刷新 3 个域名

---

## 部署建议

### 生产环境

```yaml
# docker-compose.yml 建议配置
services:
  cf-gateway:
    deploy:
      resources:
        limits:
          memory: 4G
    environment:
      - BROWSER_POOL_MAX=5
      - MEMORY_LIMIT_MB=3000
```

### Kubernetes

```yaml
# 健康检查配置
livenessProbe:
  httpGet:
    path: /health/live
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 5
```

---

## 常见问题

<details>
<summary><b>登录 Dashboard 返回 403</b></summary>

确认使用 admin 角色的 API Key。当 `data/api_keys.json` 或 `API_KEYS_JSON` 环境变量存在时，`config.py` 中的默认 `API_KEY` 不再生效。

</details>

<details>
<summary><b>过盾超时</b></summary>

1. 增大浏览器池：`BROWSER_POOL_MAX=5`
2. 检查目标站点是否可访问
3. 查看日志：`docker logs cf-gateway`

</details>

<details>
<summary><b>Chrome 启动失败</b></summary>

确保 Docker 容器有足够权限，`--no-sandbox` 参数已默认启用。如使用非 Docker 环境，需手动安装 Chrome。

</details>

<details>
<summary><b>内存占用过高</b></summary>

1. 降低 `BROWSER_POOL_MAX`
2. 调整 `MEMORY_LIMIT_MB` 触发自动重启
3. 减少 `BROWSER_POOL_IDLE_TIMEOUT`

</details>

---

## 更多资源

- **详细文档**: [docs/WIKI.md](docs/WIKI.md)
- **API 文档**: 启动后访问 `/docs` 或 `/redoc`
- **问题反馈**: 提交 Issue 并附带日志和复现步骤

---

<div align="center">

**CF-Gateway Pro** - 让 Cloudflare 不再是障碍

</div>
