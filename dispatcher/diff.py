# -*- coding: utf-8 -*-
"""
Spreadsheet version comparator.
Compares revisions (e.g. V1 vs V2 vs V3) by row counts and content hashes
to prevent redundant uploads and detect newly appended copy items.
"""

from typing import Dict, Any, List
from dispatcher.parser import parse_workbook


class WorkbookDiff:
    @staticmethod
    def compare(file_path_a: str, file_path_b: str) -> Dict[str, Any]:
        """比对两份 Excel 工作簿的文案异同"""
        data_a = parse_workbook(file_path_a)
        data_b = parse_workbook(file_path_b)

        all_sheets = set(data_a.keys()).union(set(data_b.keys()))
        sheet_diffs = {}

        total_a_hashes = set()
        total_b_hashes = set()

        for s_name in all_sheets:
            items_a = data_a.get(s_name, [])
            items_b = data_b.get(s_name, [])

            hashes_a = {it["content_hash"] for it in items_a}
            hashes_b = {it["content_hash"] for it in items_b}

            total_a_hashes.update(hashes_a)
            total_b_hashes.update(hashes_b)

            added_hashes = hashes_b - hashes_a
            removed_hashes = hashes_a - hashes_b
            common_hashes = hashes_a.intersection(hashes_b)

            sheet_diffs[s_name] = {
                "count_a": len(items_a),
                "count_b": len(items_b),
                "common_count": len(common_hashes),
                "added_count": len(added_hashes),
                "removed_count": len(removed_hashes),
                "is_identical": (hashes_a == hashes_b)
            }

        overall_common = total_a_hashes.intersection(total_b_hashes)
        overall_overlap_rate = len(overall_common) / max(1, len(total_b_hashes))

        return {
            "file_a": file_path_a,
            "file_b": file_path_b,
            "sheet_diffs": sheet_diffs,
            "total_items_a": len(total_a_hashes),
            "total_items_b": len(total_b_hashes),
            "common_items": len(overall_common),
            "overlap_ratio_b_to_a": overall_overlap_rate,
            "is_completely_identical": (total_a_hashes == total_b_hashes)
        }
