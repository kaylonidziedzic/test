# 项目进度

## 当前版本功能

### 1. 规则配置系统 (零代码平台核心)
- **规则创建/编辑/删除** - 完整 CRUD
- **Permlink 生成** - 保存规则后自动生成 `/v1/run/{id}` 链接
- **用户权限隔离** - 普通用户只能看到自己的规则，管理员可看所有

#### 规则配置项
| 配置项 | 说明 | 状态 |
|--------|------|------|
| 接口类型 | proxy(JSON) / raw(原始) / reader(阅读模式) | ✅ |
| 请求方式 | GET / POST | ✅ |
| 采集模式 | cookie(复用) / browser(直读) | ✅ |
| 访问控制 | 私有(需Key) / 公开(无需认证) | ✅ |
| 代理模式 | none / pool(IP池) / fixed(指定IP) | ✅ |
| POST 请求体 | none / json / form / raw | ✅ |
| 自定义请求头 | 支持多个 Header | ✅ |
| CSS 选择器 | 数据提取规则 | ✅ |

### 2. 快速测试 (已合并到规则配置页)
- 输入 URL 快速测试采集效果
- 支持选择：接口类型、采集模式、代理模式
- 显示测试结果（成功/失败、耗时、Cookies 数量等）

### 3. 代理管理
- 查看代理统计（总数、可用数、轮换策略）
- 添加/删除代理
- 从文件重新加载代理列表
- 支持 http/https/socks5 协议

### 4. 异步任务队列
- 基于 ARQ + Redis
- `POST /v1/jobs/` - 提交异步任务
- `GET /v1/jobs/{job_id}` - 查询任务状态

### 5. 多用户权限系统
- API Key 认证
- 用户角色：admin / user
- Dashboard SSE 实时推送

---

## 已知问题

### 待修复
1. **规则编辑显示旧值** - 部分字段（POST请求体、代理配置、自定义请求头）编辑时可能显示旧值
   - 原因：前端 `openRuleForm` 函数对某些字段的处理不够严格
   - 状态：已修复，待验证

2. **被拦截问题** - 某些网站 CookieFetcher 重试后仍被拦截
   - 原因：网站反爬机制，非代码问题
   - 建议：更换代理或使用浏览器直读模式

### 待优化
1. 快速测试的参数目前未传递到后端（需要修改 `testBypass` 函数）
2. 批量测试功能已移除，如需要可重新添加

---

## 文件结构

```
├── routers/
│   ├── runner.py      # 规则执行 API
│   ├── job.py         # 异步任务 API
│   └── dashboard.py   # Dashboard API
├── services/
│   ├── rule_service.py    # 规则服务 (Redis 存储)
│   ├── proxy_manager.py   # 代理管理
│   ├── job_queue.py       # ARQ Worker
│   └── proxy_service.py   # 请求调度
├── static/
│   └── index.html     # 前端 Dashboard (Vue 3)
└── docker-compose.yml # Redis + Worker 配置
```

---

## 下一步计划

1. 验证规则编辑显示旧值问题是否修复
2. 快速测试参数传递到后端
3. 规则缓存功能实现 (cache_ttl)
4. 规则执行统计（成功/失败次数）
