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

## 2024-12-14 BrowserFetcher POST 请求支持 (已修复)

### 问题描述
访问 `http://127.0.0.1:8000/v1/run/0c64f4f3?q=斗破` 时，看到的是搜索页而不是搜索结果页。

### 规则配置
```json
{
  "name": "tesat",
  "target_url": "https://www.69shuba.com/modules/article/search.php",
  "method": "POST",
  "body": "searchkey={q}",
  "body_type": "form",
  "api_type": "reader"
}
```

### 根本原因
1. CookieFetcher 发送 POST 请求时被 Cloudflare Turnstile 拦截
2. 系统降级到 BrowserFetcher
3. **BrowserFetcher 只支持 GET 请求**，POST 请求被当作 GET 处理
4. 表单数据 `searchkey=斗破` 丢失，只访问了 URL 本身
5. 结果返回的是搜索页（空表单）而不是搜索结果页

### 日志证据
```
[ProxyService] 降级到 BrowserFetcher，但 POST 请求将被当作 GET 处理
[BrowserFetcher] 正在访问: https://www.69shuba.com/modules/article/search.php
[BrowserFetcher] 页面加载成功，标题: 小说搜索_69书吧  ← 搜索页，不是结果页
```

### 修复方案
1. **`core/fetchers/browser_fetcher.py`**：
   - 添加 `_submit_form_via_js()` 方法
   - 通过 JavaScript 动态创建表单并提交，实现 POST 请求
   - 先访问目标域名首页（确保同域），再执行 JS 提交表单

2. **`services/proxy_service.py`**：
   - 修改 `_fallback_to_browser()` 函数
   - 将 `method` 和 `data` 参数传递给 BrowserFetcher
   - 删除强制转换为 GET 的逻辑

### 修复后日志
```
[CookieFetcher] 未检测到拦截特征，请求成功
标题: 《斗破》搜索结果_69书吧  ← 正确的搜索结果页
```

### 补充说明
实际上 CookieFetcher 对 POST 请求本身是支持的。之前失败是因为 **Cookie 过期/失效**，容器重启后浏览器重新过盾获取了新的有效 Cookie，所以 POST 请求能直接成功。

BrowserFetcher POST 修复是一个**兜底方案**，确保即使 Cookie 失效且重试也失败时，降级到浏览器仍能正确处理 POST 请求。

**待解决问题**：~~Cookie 失效后，CookieFetcher 重试时重新过盾，但新 Cookie 仍可能被拦截（原因待查）。~~ 已解决，见下方。

---

## 2024-12-14 Cookie 重试失败后清理机制 (已修复)

### 问题描述
CookieFetcher 被拦截后重试，即使重新过盾获取新 Cookie，仍可能被拦截。

### 根本原因
1. 重新过盾时复用了**同一个浏览器实例**
2. 该浏览器实例的状态/指纹可能已被 Cloudflare 标记
3. 新 Cookie 虽然有效，但与被标记的浏览器环境关联，仍被拦截

### 修复方案
在 `cookie_fetcher.py` 中添加 `_cleanup_on_persistent_block()` 方法：

1. **清除域名缓存**：调用 `credential_cache.invalidate(domain)` 删除该域名的凭证
2. **销毁浏览器实例**：从浏览器池中取出所有空闲实例并销毁
3. **自动补充**：`browser_pool.destroy()` 会自动创建新实例补充到最小数量

### 流程变化
```
之前：
请求 → 被拦截 → 重新过盾(复用旧浏览器) → 仍被拦截 → 降级到 BrowserFetcher

现在：
请求 → 被拦截 → 重新过盾(复用旧浏览器) → 仍被拦截 → 清除缓存+销毁浏览器 → 降级到 BrowserFetcher
下次请求 → 用全新浏览器过盾 → 成功
```

### 修改文件
- `core/fetchers/cookie_fetcher.py`：添加 `_cleanup_on_persistent_block()` 方法

---

## 2024-12-14 代理模式优化 (已完成)

### 问题描述
使用代理时，CookieFetcher 因 TLS 指纹不一致必定失败，导致每次请求都要经历：
1. CookieFetcher 过盾（5-10秒）
2. CookieFetcher 请求失败（2-3秒）
3. 降级到 BrowserFetcher（3-5秒）

总计约 10-18 秒，严重影响速度。

### 根本原因
- 浏览器通过代理过盾获取的 `cf_clearance` Cookie 与该代理 IP + TLS 指纹绑定
- CookieFetcher 使用 curl_cffi 发请求，即使用相同代理，**TLS 指纹不同**
- Cloudflare 检测到不一致，返回 403

### 优化方案
**方案 C：根据是否使用代理选择 Fetcher**

1. **使用代理时**：直接使用 BrowserFetcher，跳过 CookieFetcher
2. **不使用代理时**：先尝试 CookieFetcher（Cookie 复用），失败再降级

### 修改文件
- `services/proxy_service.py`：在 Fetcher 选择逻辑中，检测到 proxy 时直接使用 BrowserFetcher
- `core/fetchers/cookie_fetcher.py`：移除清除缓存逻辑（不再需要）

### 优化后流程
```
使用代理：
检测到 proxy → 直接使用 BrowserFetcher → 约 3-5 秒

不使用代理：
CookieFetcher（Cookie 复用）→ 成功 → 约 0.5-2 秒
CookieFetcher → 被拦截 → 降级到 BrowserFetcher → 约 3-5 秒
```

### 前端说明
当规则配置使用代理（proxy_mode=pool 或 fixed）时，系统会自动使用浏览器直出模式，不会尝试 Cookie 复用。这是因为代理模式下 Cookie 复用存在 TLS 指纹不一致的问题，暂时无法解决。

---

## 当前状态

- [x] 前端问题已修复
- [x] 后端 API 问题已修复
- [x] Cookie 复用（无代理）正常工作
- [x] Cookie 复用失败时自动降级到浏览器直出
- [x] **BrowserFetcher POST 请求支持** (2024-12-14)
- [x] ~~Cookie 重试失败后清理机制~~ (已移除，改为直接降级)
- [x] **代理模式优化：直接使用 BrowserFetcher** (2024-12-14)
- [ ] **待优化**: 代理模式下 Cookie 复用需要架构改进确保 TLS 指纹一致性（长期目标）
