# 结构化重构建议（保持现有行为）

> ⚠️ 所有对外接口、请求顺序、headers/cookies/过盾流程保持 **100%** 原样。本文件仅提供可读性与维护性提升的参考。

## 推荐目录结构

```
.
├── main.py                # FastAPI 入口，集中挂载路由
├── routers/               # 仅包含路由层，避免业务逻辑掺杂
│   ├── health.py          # 健康检查
│   ├── proxy.py           # JSON 代理
│   ├── raw.py             # 原始二进制代理
│   └── reader.py          # 阅读模式 (GET/POST)
├── schemas/               # Pydantic 模型
│   └── proxy.py
├── services/              # 业务/域服务，封装 curl_cffi + 过盾逻辑
│   └── proxy_service.py
├── core/                  # 底层支撑：浏览器、过盾
│   ├── browser.py
│   └── solver.py
├── utils/                 # 工具库：日志、响应构造等
│   ├── logger.py
│   └── response_builder.py
├── dependencies.py        # FastAPI DI 依赖（鉴权等）
├── config.py              # 配置项
└── docs/                  # 文档与示例
    └── STRUCTURE.md
```

## APIRouter 最佳实践示例

```python
from fastapi import APIRouter, Depends
from dependencies import verify_api_key
from services.proxy_service import proxy_request

router = APIRouter()

@router.post("/v1/proxy", dependencies=[Depends(verify_api_key)])
def proxy_handler(req: ProxyRequest):
    """保持原有行为，避免修改 headers/cookies 处理顺序"""
    resp = proxy_request(...)
    return build_response(resp)
```

## services / utils / schemas 划分建议
- **services**：包含可复用的业务流程（如 `proxy_request`）。内部可以拆分子函数，但顺序与逻辑保持不变；如需改进，用中文 `TODO` 记录。
- **utils**：纯工具，不依赖业务上下文，如解码、HTML 注入、日志等。
- **schemas**：输入输出模型，保持字段与默认值一致，避免影响兼容性。

## 可以安全优化的部分
- 增加类型注解、文档字符串，帮助阅读；不改变任何默认值与分支。
- 提取重复代码为内部私有函数，前后调用顺序保持一致。
- 保留特殊站点策略（例如 69shuba.com），如需改写仅以 `TODO` 备注。

## 必须保持不动的部分
- Cloudflare 过盾流程（`solve_turnstile`）及其调用顺序。
- 69shuba.com 的浏览器直连策略。
- headers/cookies 过滤规则、重试次数与判断条件。
- 所有路由路径、请求方法、返回结构（含状态码、header、body 字段）。
