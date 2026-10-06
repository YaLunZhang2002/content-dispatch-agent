# -*- coding: utf-8 -*-
"""
Constraint-based copy allocator.
Implements deduplication against SQLite ledger, cross-platform copy sharing,
fallback pool borrowing, and capacity reporting.
"""

from typing import List, Dict, Any, Optional, Set
from dispatcher.spec import TaskSpec, CopyItem, PlatformBlock
from dispatcher.ledger import DispatchLedger
from dispatcher.renderer import render_copy_body, get_default_platform_header, RenderedPayload


class CopyAllocator:
    def __init__(self, ledger: DispatchLedger):
        self.ledger = ledger

    def allocate(
        self,
        spec: TaskSpec,
        workbook_data: Dict[str, List[Dict[str, Any]]],
        allow_fallback_borrowing: bool = True
    ) -> List[RenderedPayload]:
        """
        根据 TaskSpec 执行约束分配，返回各个平台待分发的 RenderedPayload 列表
        """
        used_hashes = self.ledger.get_used_hashes(campaign=spec.campaign)
        allocated_in_this_session: Set[str] = set()

        payloads: List[RenderedPayload] = []

        # 模式一：同文案跨平台同步（如：头条+公众号使用同一篇文案，但分别独立分发）
        if spec.same_copy_across_platforms:
            primary_block = spec.blocks[0]
            sheet_name = primary_block.source_sheet or list(workbook_data.keys())[0]

            selected_raw = self._pick_available_items(
                workbook_data=workbook_data,
                preferred_sheet=sheet_name,
                count=spec.count,
                used_hashes=used_hashes,
                session_allocated=allocated_in_this_session,
                allow_borrowing=allow_fallback_borrowing
            )

            if len(selected_raw) < spec.count:
                raise ValueError(
                    f"素材池库存不足！请求 {spec.count} 篇，但可用未分配素材仅剩 {len(selected_raw)} 篇。"
                )

            # 为每个平台装配相同的正文
            for block in spec.blocks:
                items: List[CopyItem] = []
                for idx, raw in enumerate(selected_raw, start=spec.seq_start):
                    full_text = render_copy_body(
                        title=raw["title"],
                        body=raw["body"],
                        tags=raw["tags"],
                        with_tags=block.with_tags
                    )
                    items.append(CopyItem(
                        seq=idx,
                        title=raw["title"],
                        body=raw["body"],
                        tags=raw["tags"],
                        full_text=full_text,
                        content_hash=raw["content_hash"],
                        source_sheet=raw["source_sheet"],
                        source_row=raw["source_row"]
                    ))

                header = block.custom_alias or get_default_platform_header(block.platform)
                payloads.append(RenderedPayload(
                    owner=spec.owner,
                    platform=block.platform,
                    header=header,
                    items=items
                ))

            # 标记这一批文案已在本轮使用
            for raw in selected_raw:
                allocated_in_this_session.add(raw["content_hash"])

            return payloads

        # 模式二：多平台独立文案（每个平台使用完全不同且互不重合的文案）
        for block in spec.blocks:
            # 推断或使用指定 sheet
            sheet_name = block.source_sheet
            if not sheet_name:
                # 尝试自适应匹配名称相似的 Sheet
                for s_name in workbook_data.keys():
                    if block.platform in s_name or any(k in s_name for k in [block.platform[:2]]):
                        sheet_name = s_name
                        break
            if not sheet_name:
                sheet_name = list(workbook_data.keys())[0]

            selected_raw = self._pick_available_items(
                workbook_data=workbook_data,
                preferred_sheet=sheet_name,
                count=spec.count,
                used_hashes=used_hashes,
                session_allocated=allocated_in_this_session,
                allow_borrowing=allow_fallback_borrowing
            )

            if len(selected_raw) < spec.count:
                raise ValueError(
                    f"平台 [{block.platform}] 可用素材不足！需要 {spec.count} 篇，但仅获取到 {len(selected_raw)} 篇未用素材。"
                )

            items: List[CopyItem] = []
            for idx, raw in enumerate(selected_raw, start=spec.seq_start):
                full_text = render_copy_body(
                    title=raw["title"],
                    body=raw["body"],
                    tags=raw["tags"],
                    with_tags=block.with_tags
                )
                items.append(CopyItem(
                    seq=idx,
                    title=raw["title"],
                    body=raw["body"],
                    tags=raw["tags"],
                    full_text=full_text,
                    content_hash=raw["content_hash"],
                    source_sheet=raw["source_sheet"],
                    source_row=raw["source_row"]
                ))
                allocated_in_this_session.add(raw["content_hash"])

            header = block.custom_alias or get_default_platform_header(block.platform)
            payloads.append(RenderedPayload(
                owner=spec.owner,
                platform=block.platform,
                header=header,
                items=items
            ))

        return payloads

    def _pick_available_items(
        self,
        workbook_data: Dict[str, List[Dict[str, Any]]],
        preferred_sheet: str,
        count: int,
        used_hashes: Set[str],
        session_allocated: Set[str],
        allow_borrowing: bool
    ) -> List[Dict[str, Any]]:
        """按优先级选取尚未使用的条目，不足时支持从其他 Sheet 借调"""
        picked = []

        # 1. 优先从指定 Sheet 提取
        candidates = workbook_data.get(preferred_sheet, [])
        for item in candidates:
            h = item["content_hash"]
            if h not in used_hashes and h not in session_allocated:
                picked.append(item)
                if len(picked) >= count:
                    return picked

        # 2. 如果不足且允许借调，从其他 Sheet 补充
        if allow_fallback_borrowing and len(picked) < count:
            for s_name, other_items in workbook_data.items():
                if s_name == preferred_sheet:
                    continue
                for item in other_items:
                    h = item["content_hash"]
                    if h not in used_hashes and h not in session_allocated and item not in picked:
                        picked.append(item)
                        if len(picked) >= count:
                            return picked

        return picked

    def get_capacity_report(
        self,
        workbook_data: Dict[str, List[Dict[str, Any]]],
        campaign: Optional[str] = None
    ) -> Dict[str, Any]:
        """评估素材池余量，精准回答'还能发多少'"""
        used_hashes = self.ledger.get_used_hashes(campaign=campaign)
        sheet_stats = {}
        total_available = 0
        total_pool = 0

        for s_name, items in workbook_data.items():
            pool_count = len(items)
            avail_count = sum(1 for it in items if it["content_hash"] not in used_hashes)
            total_pool += pool_count
            total_available += avail_count
            sheet_stats[s_name] = {
                "total": pool_count,
                "used": pool_count - avail_count,
                "available": avail_count
            }

        return {
            "total_pool": total_pool,
            "total_available": total_available,
            "total_dispatched": total_pool - total_available,
            "sheets": sheet_stats
        }
