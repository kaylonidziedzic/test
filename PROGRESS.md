# Progress Log

## 2024-12-13 已修复的问题

### 1. 前端 SyntaxError (已修复)
- **问题**: `index.html:296-297` 中 `split(' ')` 字符串被换行，导致 Vue 模板编译错误
- **修复**: 将换行的字符串改为单行

### 2. 添加规则 500 错误 (已修复)
- **问题**: `routers/runner.py` 中 `from services.api_key_store import api_key_store` 导入错误
- **修复**: 改为 `from services.api_key_store import find_user_by_key`

### 3. SSE applySnapshot 错误 (已修复)
- **问题**: `app.js:280` 中 spread 语法遇到非数组类型报错
- **修复**: 使用 `Array.isArray()` 检查后再 spread

### 4. 规则测试显示失败 (已修复)
- **问题**: `reader` 类型规则返回 HTML，前端调用 `res.json()` 解析失败
- **修复**: 前端根据 `Content-Type` 判断响应类型，HTML 响应显示内容长度和预览

### 5. Cookie 复用自动降级 (已修复)
- **问题**: 显式指定 `fetcher=cookie` 时 `use_fallback=False`，被拦截不会降级
- **修复**: `proxy_service.py` 中 cookie 模式仍支持自动降级

---

## Cookie 复用状态

### 无代理模式 (已验证正常)
```
[CookieFetcher] 不使用代理 (直连)
[CookieFetcher] 发起请求: https://www.69shuba.com/txt/90442/40956667 (尝试 1/2)
[CookieFetcher] 检查拦截: status=200, content_length=9399
[CookieFetcher] 未检测到拦截特征，请求成功
```

### 使用代理模式 (存在问题)

**问题描述**: 当规则配置使用代理时，Cookie 复用失败，被迫降级到浏览器直出。

**根本原因**: 代理 IP 不一致
```
问题链:
1. 规则配置使用代理 (proxy_mode=pool 或 fixed)
2. browser_pool.py 创建浏览器时从 proxy_manager.get_proxy() 获取代理
3. 浏览器过盾时使用代理 A 获取 cf_clearance Cookie
4. CookieFetcher 请求时可能使用代理 B (如果代理池有多个 IP)
5. 或者 CookieFetcher 使用的代理与浏览器不同
6. Cloudflare 检测到请求 IP 与 Cookie 获取时的 IP 不一致
7. 返回 403 拦截
```

**当前行为**:
- Cookie 复用失败后自动降级到 BrowserFetcher
- BrowserFetcher 直接使用浏览器获取内容，可以成功
- 但性能较差，每次请求都需要浏览器渲染

---

## IP 代理池架构问题 (待优化)

### 当前架构缺陷
```
规则配置代理 (proxy_mode)
    │
    ├── none: 不使用代理 → CookieFetcher 直连 ✓ 正常
    ├── pool: 从 proxy_manager 获取 → 可能与浏览器代理不一致 ✗
    └── fixed: 使用规则指定的 proxy → 可能与浏览器代理不一致 ✗

浏览器池 (browser_pool.py)
    │
    └── 创建实例时无条件从 proxy_manager.get_proxy() 获取代理
        (不管规则配置什么，浏览器都可能使用不同的代理)

credential_cache (cache_service.py)
    │
    └── get_credentials() 不接收 proxy 参数
        无法将规则的代理配置传递给浏览器过盾流程
```

### 问题总结
1. **浏览器代理与规则配置脱节**: 浏览器创建时不知道规则的代理配置
2. **代理不一致风险**: 浏览器过盾用的 IP 可能与 CookieFetcher 用的 IP 不同
3. **降级时代理问题**: BrowserFetcher 使用已有浏览器实例的代理，不是规则指定的
4. **代理池轮换问题**: 如果代理池有多个 IP，每次 get_proxy() 可能返回不同 IP

### 理想架构
```
规则配置代理
    ↓
CookieFetcher.fetch(proxy=规则代理)
    ↓
credential_cache.get_credentials(url, proxy=规则代理)
    ↓
solve_turnstile(url, proxy=规则代理)
    ↓
browser_pool.acquire(proxy=规则代理)
    ↓
创建/复用匹配该代理的浏览器实例
    ↓
浏览器过盾获取 Cookie (使用规则代理)
    ↓
CookieFetcher 使用相同代理发起请求
    ↓
IP 一致，Cookie 有效
```

### 需要修改的文件
1. `core/browser_pool.py` - `acquire()` 接收 `proxy` 参数，按代理分组管理实例
2. `core/solver.py` - `solve_turnstile()` 接收 `proxy` 参数
3. `services/cache_service.py` - `get_credentials()` 接收 `proxy` 参数，按 (domain, proxy) 缓存
4. `core/fetchers/cookie_fetcher.py` - 将 `proxy` 传递给 `credential_cache`

### 临时解决方案
1. **单代理模式**: 代理池只配置一个代理，确保浏览器和 CookieFetcher 使用相同 IP
2. **无代理模式**: 不使用代理，浏览器和 CookieFetcher 都直连
3. **浏览器直出模式**: 规则配置使用 `browser` 模式，跳过 Cookie 复用

---

## 当前状态

- [x] 前端问题已修复
- [x] 后端 API 问题已修复
- [x] Cookie 复用（无代理）正常工作
- [x] Cookie 复用失败时自动降级到浏览器直出
- [ ] **待优化**: 代理模式下 Cookie 复用需要架构改进确保 IP 一致性
