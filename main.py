"""FastAPI entrypoint wiring proxy-related routers.

严格保持路由签名与行为不变，仅做分层与可读性优化。
"""
from __future__ import annotations

from fastapi import FastAPI

from config import settings
from routers import health, proxy, raw, reader

app = FastAPI(title=settings.API_TITLE, version="2.0.0")

# Register routers
app.include_router(health.router)
app.include_router(proxy.router)
app.include_router(raw.router)
app.include_router(reader.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=False)
