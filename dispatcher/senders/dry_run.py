# -*- coding: utf-8 -*-
"""
Dry-run sender for local simulation, offline testing, and text artifact generation.
"""

import os
from datetime import datetime
from typing import List, Callable, Optional
from dispatcher.renderer import RenderedPayload
from dispatcher.senders.base import BaseSender


class DryRunSender(BaseSender):
    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or os.path.join("output", datetime.now().strftime("%Y-%m-%d"))

    def dispatch(
        self,
        payloads: List[RenderedPayload],
        target_chat: str = "文件传输助手",
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> bool:
        os.makedirs(self.output_dir, exist_ok=True)

        total_msgs = sum(len(p.to_chat_messages()) for p in payloads)
        current_msg = 0

        for p in payloads:
            filename = f"{p.owner}_{p.platform}_{len(p.items)}条_序号{p.items[0].seq}至{p.items[-1].seq}.txt"
            # 清理文件名非法字符
            safe_filename = "".join(c for c in filename if c not in r'\/:*?"<>|')
            file_path = os.path.join(self.output_dir, safe_filename)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(p.to_export_text() + "\n")

            for msg in p.to_chat_messages():
                current_msg += 1
                if on_progress:
                    on_progress(current_msg, total_msgs, f"[{p.platform}] {msg[:25]}...")

        return True
