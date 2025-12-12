"""多用户 API Key 管理：支持 env 配置和文件存储，提供增删改查与随机生成。"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from threading import Lock
from typing import Dict, List

from config import settings
from utils.logger import log

_lock = Lock()


def _normalize_entries(raw) -> List[Dict]:
    """将多种输入格式归一为 [{'user':..,'key':..,'role':..}]"""
    if not raw:
        return []
    if isinstance(raw, dict):
        return [{"user": u, "key": k, "role": "user"} for u, k in raw.items()]
    if isinstance(raw, list):
        entries = []
        for i, item in enumerate(raw):
            if isinstance(item, dict) and item.get("key"):
                entries.append({
                    "user": item.get("user", f"user{i+1}"),
                    "key": item.get("key"),
                    "role": item.get("role", "user"),
                })
        return entries
    if isinstance(raw, str):
        # 尝试解析 JSON，否则按逗号分隔 key
        try:
            parsed = json.loads(raw)
            return _normalize_entries(parsed)
        except Exception:
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            return [{"user": f"user{i+1}", "key": k, "role": "user"} for i, k in enumerate(parts)]
    return []


def _load_env_entries() -> List[Dict]:
    entries = _normalize_entries(settings.API_KEYS_JSON)
    # 兼容单 key
    return entries


def _file_path() -> Path:
    return Path(settings.API_KEYS_FILE)


def _load_file_entries() -> List[Dict]:
    path = _file_path()
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        entries = _normalize_entries(data)
        return entries
    except Exception as e:  # noqa: BLE001
        log.error(f"[api_key_store] 读取 {path} 失败: {e}")
        return []


def _save_file_entries(entries: List[Dict]) -> None:
    path = _file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with path.open("w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)


def get_all_entries() -> List[Dict]:
    """返回当前有效的密钥列表，优先级：env > file > 单一 API_KEY"""
    env_entries = _load_env_entries()
    if env_entries:
        return env_entries

    file_entries = _load_file_entries()
    if file_entries:
        return file_entries

    if settings.API_KEY:
        return [{"user": "default", "key": settings.API_KEY, "role": "admin"}]
    return []


def find_user_by_key(key: str):
    if not key:
        return None
    for entry in get_all_entries():
        if key == entry.get("key"):
            return entry
    return None


def list_mutable_entries() -> List[Dict]:
    """仅返回可写（文件）部分的用户，用于管理界面。"""
    return _load_file_entries()


def add_user(user: str, role: str = "user") -> Dict:
    if not user:
        raise ValueError("用户名不能为空")
    entries = _load_file_entries()
    if any(e.get("user") == user for e in entries):
        raise ValueError("用户名已存在")
    new_entry = {"user": user, "role": role or "user", "key": generate_key()}
    entries.append(new_entry)
    _save_file_entries(entries)
    log.info(f"[api_key_store] 新增用户 {user} (role={role})")
    return new_entry


def delete_user(user: str) -> bool:
    entries = _load_file_entries()
    new_entries = [e for e in entries if e.get("user") != user]
    if len(new_entries) == len(entries):
        return False
    _save_file_entries(new_entries)
    log.info(f"[api_key_store] 已删除用户 {user}")
    return True


def rotate_key(user: str) -> Dict:
    entries = _load_file_entries()
    updated = None
    for e in entries:
        if e.get("user") == user:
            e["key"] = generate_key()
            updated = e
            break
    if not updated:
        raise ValueError("用户不存在")
    _save_file_entries(entries)
    log.info(f"[api_key_store] 已重置用户 {user} 的密钥")
    return updated


def generate_key() -> str:
    """生成高熵随机 Key"""
    return secrets.token_urlsafe(32)
