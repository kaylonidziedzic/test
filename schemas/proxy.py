"""Pydantic models for proxy-related requests."""
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel


class ProxyRequest(BaseModel):
    url: str
    method: str = "GET"
    headers: Dict[str, str] = {}
    data: Optional[Dict[str, Any]] = None
    json_body: Optional[Dict[str, Any]] = None
    data_encoding: Optional[str] = None  # POST data 编码，如 "gbk"、"gb2312"，默认 UTF-8
