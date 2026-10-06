# -*- coding: utf-8 -*-
"""
Sender base interface.
"""

from abc import ABC, abstractmethod
from typing import List, Callable, Optional
from dispatcher.renderer import RenderedPayload


class BaseSender(ABC):
    @abstractmethod
    def dispatch(
        self,
        payloads: List[RenderedPayload],
        target_chat: str = "文件传输助手",
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> bool:
        """分发执行接口"""
        pass
