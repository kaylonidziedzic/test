"""
Fetcher 抽象基类

定义所有 Fetcher 的统一接口，便于扩展新的获取策略。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class FetchResponse:
    """统一的响应数据结构

    无论使用哪种 Fetcher，都返回相同结构的响应对象，
    便于上层代码统一处理。
    """
    status_code: int
    content: bytes
    text: str
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: Dict[str, str] = field(default_factory=dict)
    url: str = ""
    encoding: str = "utf-8"

    @property
    def ok(self) -> bool:
        """请求是否成功 (2xx 状态码)"""
        return 200 <= self.status_code < 300


class BaseFetcher(ABC):
    """Fetcher 抽象基类

    所有 Fetcher 实现必须继承此类并实现 fetch 方法。

    扩展新 Fetcher 的步骤:
    1. 创建新文件 (如 my_fetcher.py)
    2. 继承 BaseFetcher
    3. 实现 fetch 方法
    4. 在 __init__.py 中导出
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Fetcher 名称，用于日志和调试"""
        pass

    @abstractmethod
    def fetch(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> FetchResponse:
        """获取页面内容

        Args:
            url: 目标 URL
            method: HTTP 方法 (GET, POST 等)
            headers: 请求头
            data: 表单数据
            json: JSON 数据
            **kwargs: 其他参数，由具体实现决定

        Returns:
            FetchResponse: 统一的响应对象

        Raises:
            Exception: 获取失败时抛出异常
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
