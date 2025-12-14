# CF-Gateway Wiki

> 完整的部署指南、API 参考、配置说明与最佳实践

---

## 目录

- [快速入门](#快速入门)
- [部署指南](#部署指南)
- [API 参考](#api-参考)
- [功能详解](#功能详解)
- [配置参考](#配置参考)
- [故障排查](#故障排查)
- [最佳实践](#最佳实践)

---

## 快速入门

### 系统要求

| 组件 | 最低要求 | 推荐配置 |
|------|----------|----------|
| CPU | 2 核 | 4 核 |
| 内存 | 2 GB | 4 GB |
| Docker | 20.10+ | 最新版 |
| Docker Compose | 2.0+ | 最新版 |

### 30 秒启动

```bash
# 1. 克隆项目
git clone https://github.com/your-repo/cf-gateway.git
cd cf-gateway

# 2. 配置密钥
cat > data/api_keys.json << 'EOF'
[
  {"user": "admin", "key": "change-this-to-secure-key", "role": "admin"}
]
EOF

# 3. 启动
docker-compose up -d

# 4. 验证
curl http://localhost:8000/health
```

---

## 部署指南

### Docker Compose（推荐）

#### 生产环境

```yaml
# docker-compose.yml
version: '3.8'
services:
  cf-gateway:
    image: cf-gateway:latest
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - REDIS_URL=redis://redis:6379
      - BROWSER_POOL_MAX=5
      - MEMORY_LIMIT_MB=3000
    depends_on:
      - redis
    deploy:
      resources:
        limits:
          memory: 4G

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

#### 开发环境

```bash
# 启用热重载和静态文件挂载
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cf-gateway
spec:
  replicas: 1
  selector:
    matchLabels:
      app: cf-gateway
  template:
    metadata:
      labels:
        app: cf-gateway
    spec:
      containers:
      - name: cf-gateway
        image: cf-gateway:latest
        ports:
        - containerPort: 8000
        env:
        - name: REDIS_URL
          value: "redis://redis-service:6379"
        resources:
          limits:
            memory: "4Gi"
            cpu: "2"
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

### Nginx 反向代理

```nginx
upstream cf_gateway {
    server 127.0.0.1:8000;
}

server {
    listen 443 ssl http2;
    server_name gateway.example.com;

    # SSL 配置
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    # SSE 支持（重要！）
    proxy_buffering off;
    proxy_cache off;

    location / {
        proxy_pass http://cf_gateway;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 连接保持
        proxy_set_header Connection '';
        proxy_read_timeout 86400s;
    }
}
```

---

## API 参考

### 认证方式

所有 API（除健康检查外）需要认证：

```bash
# 方式 1: Header（推荐）
curl -H "X-API-KEY: your-key" http://localhost:8000/v1/proxy

# 方式 2: Query 参数
curl "http://localhost:8000/raw?url=https://example.com&key=your-key"
```

### 健康检查

#### `GET /health`

基础健康检查，无需认证。

**响应示例：**
```json
{
  "status": "healthy",
  "service": "CF-Gateway-Pro"
}
```

#### `GET /health/ready`

就绪检查，返回所有组件状态。

**响应示例：**
```json
{
  "status": "healthy",
  "service": "CF-Gateway-Pro",
  "uptime_seconds": 3600,
  "components": {
    "redis": {"status": "healthy", "url": "redis://redis:6379"},
    "browser_pool": {"status": "healthy", "total": 3, "available": 2, "in_use": 1},
    "cache": {"status": "healthy", "type": "redis", "entries": 15}
  }
}
```

#### `GET /health/live`

轻量存活检查，用于 Kubernetes Liveness Probe。

**响应示例：**
```json
{"status": "alive"}
```

### 代理接口

#### `POST /v1/proxy`

JSON 格式代理请求，返回结构化响应。

**请求体：**
```json
{
  "url": "https://example.com/page",
  "method": "GET",
  "headers": {"User-Agent": "Custom UA"},
  "data": null,
  "json_body": null,
  "data_encoding": null
}
```

**响应示例：**
```json
{
  "status": 200,
  "url": "https://example.com/page",
  "headers": {"content-type": "text/html"},
  "cookies": {"session": "abc123"},
  "encoding": "utf-8",
  "text": "<!DOCTYPE html>..."
}
```

#### `GET /raw`

返回目标站点原始响应内容。

**参数：**
| 参数 | 必填 | 说明 |
|------|------|------|
| `url` | 是 | 目标 URL |
| `key` | 是 | API Key |

**示例：**
```bash
curl "http://localhost:8000/raw?url=https://example.com&key=your-key"
```

#### `GET /reader`

阅读模式，返回处理后的 HTML 内容。

**参数：**
| 参数 | 必填 | 说明 |
|------|------|------|
| `url` | 是 | 目标 URL |
| `key` | 是 | API Key |

### 规则系统

#### `POST /v1/rules`

创建爬虫规则。

**请求体：**
```json
{
  "name": "搜索规则",
  "target_url": "https://example.com/search?q={keyword}",
  "method": "GET",
  "mode": "cookie",
  "api_type": "proxy",
  "selectors": {
    "title": "h1.title",
    "content": "div.content",
    "items": "ul.list li"
  },
  "headers": {},
  "is_public": false,
  "cache_ttl": 300,
  "proxy_mode": "none"
}
```

**响应示例：**
```json
{
  "id": "abc12345",
  "permlink": "/v1/run/abc12345",
  "message": "规则创建成功"
}
```

#### `GET /v1/rules`

获取规则列表。

#### `PUT /v1/rules/{rule_id}`

更新规则。

#### `DELETE /v1/rules/{rule_id}`

删除规则。

#### `GET /v1/run/{rule_id}`

执行规则（Permlink）。

**参数：**
| 参数 | 必填 | 说明 |
|------|------|------|
| `test` | 否 | `true` 返回 JSON 摘要 |
| `refresh` | 否 | `true` 忽略缓存 |
| `{param}` | 否 | 替换规则中的 `{param}` 占位符 |

**示例：**
```bash
# 替换 {keyword} 占位符
curl "http://localhost:8000/v1/run/abc12345?keyword=测试&key=your-key"
```

### Dashboard API

> 需要 admin 角色

#### 状态监控

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/dashboard/status` | GET | 服务状态（uptime、version） |
| `/api/dashboard/stats` | GET | 综合统计（浏览器池、缓存、请求） |
| `/api/dashboard/system` | GET | 系统信息（CPU、内存、磁盘） |
| `/api/dashboard/time-series` | GET | 时间序列数据 |
| `/api/dashboard/history` | GET | 请求历史 |

#### 配置管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/dashboard/config` | GET | 获取配置 |
| `/api/dashboard/config` | PUT | 更新配置（运行时生效） |

#### 缓存管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/dashboard/cache` | GET | 缓存状态 |
| `/api/dashboard/cache/clear` | POST | 清除缓存 |

#### 浏览器池

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/dashboard/browser-pool` | GET | 浏览器池状态 |
| `/api/dashboard/browser-pool/restart` | POST | 重启浏览器池 |

#### 域名智能

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/dashboard/domain-intelligence` | GET | 域名统计 |
| `/api/dashboard/domain-intelligence/reset` | POST | 重置统计 |

#### 代理管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/dashboard/proxies` | GET | 代理列表 |
| `/api/dashboard/proxies` | POST | 添加代理 |
| `/api/dashboard/proxies` | DELETE | 删除代理 |
| `/api/dashboard/proxies/reload` | POST | 从文件重载 |

#### 用户管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/dashboard/users` | GET | 用户列表 |
| `/api/dashboard/users` | POST | 创建用户 |
| `/api/dashboard/users/{username}` | DELETE | 删除用户 |
| `/api/dashboard/users/{username}/rotate` | POST | 重置密钥 |

#### 测试接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/dashboard/test` | POST | 单次测试 |
| `/api/dashboard/test/batch` | POST | 批量测试 |

---

## 功能详解

### 访问模式

#### Cookie 模式（默认）

```
用户请求 → 检查缓存 → 有效Cookie → curl_cffi发送请求 → 返回结果
                    ↓ 无效
               启动浏览器 → 过盾 → 提取Cookie → 缓存 → 请求
```

**优点：** 高效，响应快（毫秒级）
**缺点：** 部分站点可能检测 TLS 指纹

#### Browser 模式

```
用户请求 → 浏览器直接访问 → 等待渲染 → 返回结果
```

**优点：** 成功率高，完全模拟浏览器
**缺点：** 响应慢（秒级）

### 智能降级

系统自动处理 Cookie 失效：

1. Cookie 请求返回 403/503/429 → 自动降级到 Browser
2. 检测到 Cloudflare 挑战页面 → 自动降级
3. 请求异常 → 自动降级

### 域名智能学习

系统自动学习每个域名的最佳访问策略：

```python
# 判断逻辑
if cookie_failure_rate > 50% and sample_count >= 5:
    推荐使用 browser 模式
else:
    使用 cookie 模式
```

**查看统计：**
```bash
curl http://localhost:8000/api/dashboard/domain-intelligence \
  -H "X-API-KEY: admin-key"
```

**响应示例：**
```json
{
  "domains": [
    {
      "domain": "example.com",
      "cookie_success": 10,
      "cookie_failure": 8,
      "cookie_failure_rate": 0.444,
      "browser_success": 5,
      "browser_failure": 0,
      "recommended_mode": "browser"
    }
  ],
  "total_domains": 1,
  "browser_recommended": 1
}
```

### Cookie 自动刷新

后台看门狗每隔 `WATCHDOG_INTERVAL` 秒执行：

1. 检测即将过期（5分钟内）的凭证
2. 自动启动浏览器刷新
3. 每轮最多刷新 3 个域名

### 规则系统

#### 规则配置

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 规则名称 |
| `target_url` | string | 目标 URL，支持 `{param}` 占位符 |
| `method` | string | HTTP 方法 |
| `mode` | string | `cookie` / `browser` |
| `api_type` | string | `proxy` / `raw` / `reader` |
| `selectors` | object | CSS 选择器映射 |
| `headers` | object | 自定义请求头 |
| `body` | string | POST 请求体 |
| `body_type` | string | `none` / `json` / `form` |
| `is_public` | boolean | 是否公开访问 |
| `cache_ttl` | integer | 缓存时间（秒） |
| `proxy_mode` | string | `none` / `pool` / `fixed` |
| `proxy` | string | 固定代理地址 |
| `wait_for` | string | 等待元素（Browser 模式） |

#### 占位符替换

```bash
# 规则定义
{
  "target_url": "https://example.com/search?q={keyword}&page={page}",
  "body": "query={keyword}"
}

# 执行时替换
GET /v1/run/rule_id?keyword=测试&page=1
```

---

## 配置参考

### 完整配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `PORT` | 8000 | 服务端口 |
| `API_KEY` | change_me_please | 默认 API Key（不推荐使用） |
| `API_KEYS_JSON` | - | 多用户配置（JSON 字符串） |
| `API_KEYS_FILE` | data/api_keys.json | 多用户配置文件 |
| `REDIS_URL` | redis://localhost:6379 | Redis 连接地址 |
| `COOKIE_EXPIRE_SECONDS` | 1800 | Cookie 过期时间（秒） |
| `CACHE_DB_PATH` | data/cache.db | SQLite 缓存路径 |
| `BROWSER_POOL_MIN` | 1 | 浏览器池最小实例 |
| `BROWSER_POOL_MAX` | 3 | 浏览器池最大实例 |
| `BROWSER_POOL_IDLE_TIMEOUT` | 300 | 空闲回收时间（秒） |
| `MEMORY_LIMIT_MB` | 1500 | 内存限制（MB） |
| `WATCHDOG_INTERVAL` | 300 | 看门狗间隔（秒） |
| `FINGERPRINT_ENABLED` | true | 指纹随机化 |
| `HEADLESS` | false | 无头模式 |
| `PROXIES_FILE` | data/proxies.txt | 代理列表文件 |

### 密钥配置优先级

```
API_KEYS_JSON (环境变量) > API_KEYS_FILE (文件) > API_KEY (默认)
```

### 代理配置

**文件格式** (`data/proxies.txt`)：
```
http://user:pass@proxy1.example.com:8080
socks5://proxy2.example.com:1080
http://proxy3.example.com:3128
```

**规则中使用：**
```json
{
  "proxy_mode": "pool",    // 从代理池轮换
  "proxy_mode": "fixed",   // 使用固定代理
  "proxy": "http://..."    // 固定代理地址
}
```

---

## 故障排查

### 常见错误

#### 登录 403

**原因：** 使用了非 admin 角色的 Key，或 Key 无效

**解决：**
```bash
# 检查 api_keys.json
cat data/api_keys.json

# 确认使用 admin 角色的 key
curl http://localhost:8000/api/dashboard/status \
  -H "X-API-KEY: your-admin-key"
```

#### 过盾超时

**原因：** 浏览器资源不足或目标站点响应慢

**解决：**
```bash
# 增大浏览器池
export BROWSER_POOL_MAX=5

# 检查日志
docker logs cf-gateway --tail 100

# 手动测试目标站点
curl -I https://target-site.com
```

#### Chrome 启动失败

**原因：** 权限不足或缺少依赖

**解决：**
```bash
# 检查容器日志
docker logs cf-gateway | grep -i chrome

# 确认 --no-sandbox 已启用（默认启用）
# 如果使用非 Docker 环境，安装 Chrome：
# apt-get install google-chrome-stable
```

#### SSE 连接断开

**原因：** 反向代理配置问题

**解决：**
```nginx
# Nginx 配置
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 86400s;
proxy_set_header Connection '';
```

#### 内存占用过高

**解决：**
```bash
# 降低浏览器池大小
export BROWSER_POOL_MAX=2

# 降低内存限制（触发自动重启）
export MEMORY_LIMIT_MB=1000

# 缩短空闲超时
export BROWSER_POOL_IDLE_TIMEOUT=60
```

### 日志分析

```bash
# 查看实时日志
docker logs -f cf-gateway

# 搜索错误
docker logs cf-gateway 2>&1 | grep -i error

# 查看特定用户日志
docker logs cf-gateway 2>&1 | grep "\[user:alice\]"
```

---

## 最佳实践

### 安全建议

- **强密钥**：使用 32 位以上随机字符串
- **定期轮换**：通过 Dashboard 定期重置密钥
- **角色分离**：admin 仅用于管理，业务使用 user 角色
- **网络隔离**：内网部署，通过反代暴露

### 性能优化

- **浏览器池**：根据内存调整，建议每 GB 内存 1-2 个实例
- **Cookie 缓存**：适当延长 `COOKIE_EXPIRE_SECONDS`
- **代理轮换**：使用 `proxy_mode: pool` 分散请求

### 监控建议

```bash
# Prometheus 指标（待实现）
# 目前可通过 /health/ready 监控组件状态

# 定时健康检查
*/5 * * * * curl -s http://localhost:8000/health/ready | jq .status
```

### 备份策略

```bash
# 备份数据目录
tar -czvf cf-gateway-backup-$(date +%Y%m%d).tar.gz data/

# 恢复
tar -xzvf cf-gateway-backup-20240101.tar.gz
```

---

## 更新日志

### v2.0.0

- 新增 Cookie 自动刷新机制
- 新增域名智能学习
- 增强健康检查端点（/health/ready, /health/live）
- OpenAPI 文档增强
- 修复前端-后端适配问题
- 修复代理模式跳过 CookieFetcher 的 Bug

### v1.x

- 初始版本
- Cookie 复用模式
- 浏览器直读模式
- 规则系统
- Dashboard 控制台
