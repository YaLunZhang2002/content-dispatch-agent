# -*- coding: utf-8 -*-
"""
Robust Excel parser and text sanitizer.
Supports memory patching for corrupted <fill/> tags, header adaptation,
'-----' separator cleaning, and SHA-256 fingerprinting.
"""

import io
import re
import hashlib
import zipfile
from typing import List, Dict, Any, Optional
import openpyxl

from dispatcher.spec import CopyItem


def load_workbook_safe(file_path: str):
    """
    针对部分第三方工具导出的 Excel 包含空 `<fill/>` 标签导致 openpyxl 抛出
    `TypeError: Fill() takes no arguments` 的问题进行无损内存补丁加载。
    """
    with open(file_path, "rb") as f:
        content = f.read()

    data_io = io.BytesIO(content)
    out_io = io.BytesIO()

    with zipfile.ZipFile(data_io, "r") as zin, zipfile.ZipFile(out_io, "w") as zout:
        for item in zin.infolist():
            buf = zin.read(item.filename)
            if item.filename == "xl/styles.xml":
                buf = buf.replace(
                    b"<fill/>", b'<fill><patternFill patternType="none"/></fill>'
                )
            zout.writestr(item, buf)

    out_io.seek(0)
    return openpyxl.load_workbook(out_io, data_only=True)


def clean_text(text: Any) -> str:
    """清理多余空行、首尾空格，并严格剔除 3 个以上横杠构成的 '-----' 分隔线"""
    if text is None:
        return ""
    text = str(text).strip()
    lines = [
        line.strip()
        for line in text.split("\n")
        if not re.match(r"^[-—_]{3,}$", line.strip())
    ]
    return "\n".join(lines).strip()


def compute_content_hash(title: str, body: str) -> str:
    """
    根据文案标题与正文主体生成规范化的 SHA-256 内容指纹 (取前16位十六进制)。
    忽略首尾多余空白和换行差异，确保即使更换文件/复制Sheet也能精准判定为同一内容。
    """
    norm_title = re.sub(r"\s+", " ", title.strip())
    norm_body = re.sub(r"\s+", " ", body.strip())
    payload = f"T:{norm_title}|B:{norm_body}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def parse_sheet_items(sheet, default_sheet_name: str = "") -> List[Dict[str, Any]]:
    """
    解析单个工作表的数据，自适应探测表头并返回规范化的原始行字典列表。
    """
    if sheet.max_row < 2:
        return []

    # 1. 扫描表头
    col_mapping = {}
    for col_idx in range(1, sheet.max_column + 1):
        cell_val = sheet.cell(1, col_idx).value
        if cell_val is None:
            continue
        header_name = str(cell_val).strip()
        col_mapping[header_name] = col_idx

    title_col = None
    body_preferred_col = None  # 如 '增加技术点修正版'
    body_default_col = None    # 如 '正文'
    tags_col = None

    for h, idx in col_mapping.items():
        h_lower = h.lower()
        if "标题" in h or h_lower == "title":
            title_col = idx
        elif any(k in h for k in ["修正版", "修改版", "技术点"]):
            body_preferred_col = idx
        elif "正文" in h or "内容" in h or h_lower in ["content", "body"]:
            body_default_col = idx
        elif "话题" in h or "标签" in h or h_lower == "tags":
            tags_col = idx

    # 如果没有探测到显式表头，按常规第1列标题、第2列正文、第3列标签推断
    if not title_col and not body_default_col:
        title_col = 1
        body_default_col = 2
        tags_col = 3 if sheet.max_column >= 3 else None

    raw_items = []

    for row_idx in range(2, sheet.max_row + 1):
        title = ""
        if title_col:
            val = sheet.cell(row_idx, title_col).value
            if val is not None:
                title = clean_text(val)

        body = ""
        if body_preferred_col:
            val = sheet.cell(row_idx, body_preferred_col).value
            if val is not None and str(val).strip():
                body = clean_text(val)

        if not body and body_default_col:
            val = sheet.cell(row_idx, body_default_col).value
            if val is not None:
                body = clean_text(val)

        tags = ""
        if tags_col:
            val = sheet.cell(row_idx, tags_col).value
            if val is not None:
                tags = clean_text(val)

        # 若标题和正文均为空则跳过空行
        if not body and not title:
            continue

        raw_items.append({
            "source_row": row_idx,
            "source_sheet": sheet.title or default_sheet_name,
            "title": title,
            "body": body,
            "tags": tags,
            "content_hash": compute_content_hash(title, body)
        })

    return raw_items


def parse_workbook(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    解析整个工作簿，返回各 Sheet 名对应的原始条目列表字典
    """
    wb = load_workbook_safe(file_path)
    res = {}
    for name in wb.sheetnames:
        sheet = wb[name]
        items = parse_sheet_items(sheet, default_sheet_name=name)
        if items:
            res[name] = items
    wb.close()
    return res
