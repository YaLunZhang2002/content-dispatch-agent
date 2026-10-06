# -*- coding: utf-8 -*-
import os
import pytest
from dispatcher.parser import parse_workbook, clean_text, compute_content_hash


def test_clean_text():
    assert clean_text("  hello world  ") == "hello world"
    # 测试 ----- 分隔线过滤
    text_with_separator = "标题：评测\n-----\n正文在这里\n-------\n文末"
    cleaned = clean_text(text_with_separator)
    assert "-----" not in cleaned
    assert "正文在这里" in cleaned


def test_content_hash_consistency():
    h1 = compute_content_hash("大屏电视测评", "正文内容第一段")
    h2 = compute_content_hash("  大屏电视测评  ", "正文内容第一段\n")
    assert h1 == h2
    assert len(h1) == 16


def test_parse_sample_workbook():
    sample_path = os.path.join("examples", "sample_pool.xlsx")
    assert os.path.exists(sample_path)

    data = parse_workbook(sample_path)
    assert "今日头条" in data
    assert "小红书" in data
    assert "抖音" in data

    tt_items = data["今日头条"]
    assert len(tt_items) == 40
    assert tt_items[0]["title"].startswith("大屏科技新标杆")
    assert len(tt_items[0]["content_hash"]) == 16
