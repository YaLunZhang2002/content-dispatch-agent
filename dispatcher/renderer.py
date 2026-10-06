# -*- coding: utf-8 -*-
"""
Message renderer for clean copy presentation and chat payload construction.
Formats:
1. Category Title: 以下是【{platform}】文案
2. Sequence Marker: 序号{seq}
3. Clean Body: [Title\n\n][Body][\n\nTags]
"""

from typing import List, Dict, Any, Optional
from dispatcher.spec import CopyItem, PlatformBlock


def get_default_platform_header(platform_name: str) -> str:
    """生成规范化的平台提示语"""
    name = platform_name.strip()
    # 避免重复附加'文案'
    if name.endswith("文案") or name.endswith("素材"):
        return f"以下是【{name}】"
    return f"以下是【{name}】文案"


def render_copy_body(title: str, body: str, tags: str = "", with_tags: bool = False) -> str:
    """渲染单篇纯享正文"""
    parts = []
    if title:
        parts.append(title.strip() + "\n")
    if body:
        parts.append(body.strip())
    if with_tags and tags:
        parts.append(tags.strip())
    return "\n".join(parts).strip()


class RenderedPayload:
    def __init__(self, owner: str, platform: str, header: str, items: List[CopyItem]):
        self.owner = owner
        self.platform = platform
        self.header = header
        self.items = items

    def to_chat_messages(self) -> List[str]:
        """
        转换为顺序微信消息流：
        [人员标识(可选), 分类标题, 序号1, 文案1, 序号2, 文案2, ...]
        """
        messages = []
        if self.owner and self.owner != "主控节点":
            messages.append(f"【{self.owner}任务】")
        messages.append(self.header)

        for it in self.items:
            messages.append(f"序号{it.seq}")
            messages.append(it.full_text)

        return messages

    def to_export_text(self) -> str:
        """导出为标准的纯文本归档格式"""
        lines = []
        if self.owner and self.owner != "主控节点":
            lines.append(f"【{self.owner}任务】\n")
        lines.append(f"{self.header}\n")

        for it in self.items:
            lines.append(f"序号{it.seq}")
            lines.append(it.full_text)
            lines.append("")  # 空行分隔

        return "\n".join(lines).strip()
