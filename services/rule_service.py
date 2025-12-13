
"""
规则服务 - 管理爬虫规则
"""
import json
import uuid
import time
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import redis

from config import settings
from utils.logger import log

class ScrapeConfig(BaseModel):
    id: Optional[str] = None
    name: str = "未命名规则"
    target_url: str
    method: str = "GET"
    selectors: Dict[str, str] = Field(default_factory=dict, description="CSS选择器映射")
    mode: str = "cookie"  # cookie 或 browser
    wait_for: Optional[str] = None  # 仅 browser 模式有效
    created_at: float = Field(default_factory=time.time)
    # 接口与格式
    api_type: str = "proxy"  # proxy / raw / reader
    headers: Dict[str, str] = Field(default_factory=dict, description="自定义请求头")
    body: Optional[str] = None  # POST 请求体
    body_type: str = "none"  # none / json / form / raw
    # 访问控制
    is_public: bool = False  # Permlink 是否公开访问
    owner: Optional[str] = None  # 规则所属用户
    # 代理配置
    proxy_mode: str = "none"  # none(不使用) / pool(IP池轮换) / fixed(指定IP)
    proxy: Optional[str] = None  # 指定代理地址（proxy_mode=fixed时使用）
    # 缓存
    cache_ttl: int = 0  # 缓存时间（秒），0 表示不缓存

class RuleService:
    def __init__(self):
        # 复用 Redis 连接配置
        self.redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379")
        self.client = redis.from_url(self.redis_url, decode_responses=True)
        self.prefix = "rule:"

    def _get_key(self, rule_id: str) -> str:
        return f"{self.prefix}{rule_id}"

    def create_rule(self, rule: ScrapeConfig) -> str:
        if not rule.id:
            rule.id = str(uuid.uuid4())[:8]
        
        rule.created_at = time.time()
        key = self._get_key(rule.id)
        
        try:
            self.client.set(key, rule.model_dump_json())
            log.info(f"[RuleService] 创建规则: {rule.id} ({rule.name})")
            return rule.id
        except Exception as e:
            log.error(f"[RuleService] 创建失败: {e}")
            raise

    def get_rule(self, rule_id: str) -> Optional[ScrapeConfig]:
        key = self._get_key(rule_id)
        try:
            data = self.client.get(key)
            if data:
                return ScrapeConfig.model_validate_json(data)
            return None
        except Exception as e:
            log.error(f"[RuleService]读取失败: {e}")
            return None

    def list_rules(self, owner: Optional[str] = None, is_admin: bool = False) -> List[ScrapeConfig]:
        """获取规则列表

        Args:
            owner: 用户名，非管理员只能看到自己的规则
            is_admin: 是否管理员，管理员可以看到所有规则
        """
        try:
            keys = self.client.keys(f"{self.prefix}*")
            rules = []
            for key in keys:
                data = self.client.get(key)
                if data:
                    try:
                        rule = ScrapeConfig.model_validate_json(data)
                        # 权限过滤：管理员看所有，普通用户只看自己的
                        if is_admin or not owner or rule.owner == owner or rule.owner is None:
                            rules.append(rule)
                    except Exception:
                        pass
            # 按时间倒序
            rules.sort(key=lambda x: x.created_at, reverse=True)
            return rules
        except Exception as e:
            log.error(f"[RuleService] 列表获取失败: {e}")
            return []

    def delete_rule(self, rule_id: str) -> bool:
        key = self._get_key(rule_id)
        try:
            return bool(self.client.delete(key))
        except Exception:
            return False

rule_service = RuleService()
