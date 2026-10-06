# -*- coding: utf-8 -*-
import pytest
from dispatcher.nl_parser import NaturalLanguageParser
from dispatcher.spec import TaskSpec, ClarificationRequest


def test_offline_rule_parsing_success():
    parser = NaturalLanguageParser()
    prompt = "恒恒 10人 头条+小红书 序号41-50 文案不一样"
    res = parser.parse(prompt, use_llm=False)

    assert isinstance(res, TaskSpec)
    assert res.owner == "恒恒"
    assert res.count == 10
    assert res.seq_start == 41
    assert not res.same_copy_across_platforms
    assert len(res.blocks) == 2
    platforms = [b.platform for b in res.blocks]
    assert "今日头条" in platforms
    assert "小红书" in platforms


def test_offline_rule_parsing_same_copy():
    parser = NaturalLanguageParser()
    prompt = "亚伦 今天十个人 抖音+公众号，文案一样，序号1-10"
    res = parser.parse(prompt, use_llm=False)

    assert isinstance(res, TaskSpec)
    assert res.owner == "亚伦"
    assert res.count == 10
    assert res.seq_start == 1
    assert res.same_copy_across_platforms is True


def test_proactive_clarification_on_missing_fields():
    parser = NaturalLanguageParser()
    # 缺少平台和明确意图
    prompt = "今天发10条，序号1-10"
    res = parser.parse(prompt, use_llm=False)

    assert isinstance(res, ClarificationRequest)
    assert res.need_clarification is True
    assert "platforms" in res.missing_fields
    assert len(res.questions) > 0
