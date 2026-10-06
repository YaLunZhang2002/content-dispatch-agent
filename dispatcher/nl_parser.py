# -*- coding: utf-8 -*-
"""
Natural Language Task Parser with LLM and Offline Rule Engine.
Supports structured task specification extraction and proactive clarification requests
when instructions are ambiguous or missing essential parameters.
"""

import os
import re
import json
from typing import Optional, Union, Dict, Any, List
import requests

from dispatcher.spec import TaskSpec, PlatformBlock, ClarificationRequest


class NaturalLanguageParser:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")).rstrip("/")
        self.model = model or os.getenv("LLM_MODEL", "deepseek-chat")

    def parse(
        self,
        text: str,
        default_workbook: str = "sample_pool.xlsx",
        use_llm: bool = True
    ) -> Union[TaskSpec, ClarificationRequest]:
        """
        统一解析入口：优先尝试 LLM 接口，若无 API Key 或网络异常则自动回退至离线规则引擎
        """
        text = text.strip()
        if not text:
            return ClarificationRequest(
                need_clarification=True,
                missing_fields=["instruction"],
                questions=["请输入具体的分发指令，例如：'恒恒 10人 头条+小红书 序号41-50'。"],
                reason="输入指令为空"
            )

        if use_llm and self.api_key and self.api_key != "your_api_key_here":
            try:
                return self._parse_with_llm(text, default_workbook)
            except Exception as e:
                # 记录告警并回退
                print(f"[NLParser Warning] LLM 调用失败，降级为离线规则解析: {e}")

        return self._parse_with_rules(text, default_workbook)

    def _parse_with_rules(self, text: str, default_workbook: str) -> Union[TaskSpec, ClarificationRequest]:
        """离线规则提取引擎 (基于模式匹配与状态判定)"""
        missing = []
        questions = []

        # 1. 提取责任人
        owner = "主控节点"
        for name in ["亚伦", "恒恒", "宝哥"]:
            if name in text:
                owner = name
                break

        # 2. 提取平台
        platforms = []
        if any(k in text for k in ["头条", "今日头条"]):
            platforms.append("今日头条")
        if any(k in text for k in ["小红书", "红书"]):
            platforms.append("小红书")
        if any(k in text for k in ["公众号", "微信公众号"]):
            platforms.append("微信公众号")
        if "抖音" in text:
            platforms.append("抖音")

        if not platforms:
            missing.append("platforms")
            questions.append("请明确需要分发的发布平台（如：今日头条、小红书、微信公众号、抖音）？")

        # 3. 提取数量与序号范围
        seq_start = 1
        count = 10  # 默认常规模量

        # 匹配如 "41-50", "序号1-10", "41到50"
        m_range = re.search(r"(?:序号)?\s*(\d+)\s*[-~到至]\s*(\d+)", text)
        m_count = re.search(r"(\d+)\s*(?:人|篇|条|组)", text)

        if m_range:
            start_val = int(m_range.group(1))
            end_val = int(m_range.group(2))
            seq_start = start_val
            count = max(1, end_val - start_val + 1)
        elif m_count:
            count = int(m_count.group(1))
            # 尝试单序号匹配
            m_start = re.search(r"(?:从|起始|序号)?\s*(\d+)\s*(?:开始|起)", text)
            if m_start:
                seq_start = int(m_start.group(1))
        else:
            missing.append("count_or_range")
            questions.append("请指明分发的序号范围或人数（例如：序号 41-50 或 10人）？")

        # 4. 判断文案是否一致
        same_copy = False
        if any(k in text for k in ["文案一样", "文案相同", "同一篇", "同文案"]):
            same_copy = True
        elif any(k in text for k in ["文案不一样", "文案不同", "各不相同", "两个平台不同"]):
            same_copy = False
        elif len(platforms) > 1:
            # 两个平台但未明确说明文案是否相同时，发起澄清
            missing.append("same_copy_decision")
            questions.append("多个平台之间是使用同一篇文案分发，还是各自分配不同文案？")

        # 5. 判断是否带话题标签 (#tag)
        with_tags = False
        if any(k in text for k in ["tag", "标签", "话题"]):
            with_tags = True

        # 若存在必要缺失项，返回反问模型
        if missing:
            return ClarificationRequest(
                need_clarification=True,
                missing_fields=missing,
                questions=questions,
                reason=f"指令缺少必要约束: {', '.join(missing)}"
            )

        # 组装 blocks
        blocks = []
        for p in platforms:
            # 小红书/抖音默认带标签若指令提及
            p_tags = with_tags if p in ["小红书", "抖音"] else False
            blocks.append(PlatformBlock(
                platform=p,
                with_tags=p_tags
            ))

        return TaskSpec(
            campaign="q9m_art",
            workbook_path=default_workbook,
            owner=owner,
            seq_start=seq_start,
            count=count,
            blocks=blocks,
            same_copy_across_platforms=same_copy
        )

    def _parse_with_llm(self, text: str, default_workbook: str) -> Union[TaskSpec, ClarificationRequest]:
        """通过大模型 OpenAPI 结构化输出解析任务"""
        system_prompt = """你是一个营销文案自动化系统的任务调度架构师。
你的职责是将用户的中文指令解析为标准的 JSON 配置。
支持的字段要求：
{
  "need_clarification": false,
  "spec": {
    "campaign": "q9m_art",
    "workbook_path": "sample_pool.xlsx",
    "owner": "责任人姓名，如 恒恒/宝哥/亚伦/主控节点",
    "seq_start": 1,
    "count": 10,
    "same_copy_across_platforms": true或false,
    "blocks": [
      {"platform": "今日头条", "with_tags": false},
      {"platform": "小红书", "with_tags": true}
    ]
  }
}
若指令中存在模糊不清或关键字段缺失（如：缺少平台、缺少人数或序号、多平台未说明文案是否一样），必须返回反问格式：
{
  "need_clarification": true,
  "missing_fields": ["缺失字段名"],
  "questions": ["需要向用户追问的具体问题"],
  "reason": "原因说明"
}
请严格只返回有效的 JSON 字符串，不附加额外 Markdown 说明。"""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"工作簿默认路径: {default_workbook}\n用户指令: {text}"}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }

        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        raw_content = data["choices"][0]["message"]["content"]
        res_json = json.loads(raw_content)

        if res_json.get("need_clarification"):
            return ClarificationRequest(
                need_clarification=True,
                missing_fields=res_json.get("missing_fields", []),
                questions=res_json.get("questions", []),
                reason=res_json.get("reason", "模型判定缺少关键信息")
            )
        else:
            spec_data = res_json.get("spec", {})
            if "workbook_path" not in spec_data:
                spec_data["workbook_path"] = default_workbook
            return TaskSpec(**spec_data)
