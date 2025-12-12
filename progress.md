# 工作进度记录

## 当前改动概览
- 文档：新增 `README.md`、`docs/WIKI.md`，详细说明特性、接口、部署、排障，以及建议/不建议（含原因）。
- 多密钥/权限：`data/api_keys.json` 示例，支持 admin/user 角色；`dependencies.py` 与 `services/api_key_store.py` 实现多 Key 加载与管理员校验。
- 后端：`routers/dashboard.py` 新增用户管理接口、日志分桶/SSE 流；状态/测试/批量测试等接口带用户标记；日志解析函数 `_parse_log_lines`。
- 日志：`utils/logger.py` 注入 `[user:xxx]` 格式；前端/后端支持按用户过滤。
- 前端：`static/index.html` 支持 SSE（数据+日志）、用户筛选、双栏日志、批量测试进度、用户管理、后端地址配置、自动刷新开关等。
- 开发体验：`docker-compose.override.yml` 用于挂载 static + uvicorn --reload。
- 配置：`config.py` 增加 `API_KEYS_JSON`/`API_KEYS_FILE`；回退逻辑仅在 env/file 都为空时使用 `API_KEY`。

## 待处理/注意事项
- Compose `version` 字段提示弃用，如需可移除。
- 批量测试进一步优化（重试失败/分组导出）尚未实施。
- 默认 admin key 请尽快在控制台“用户/密钥”页重置为强随机。

## 推送建议
- 提交前检查：`git status`。
- 提交示例：`git add . && git commit -m "docs: add README and wiki; dashboard auth/log updates"`
- 推送：`git push <remote> <branch>`（如 `origin main`）。

