# -*- coding: utf-8 -*-
"""
Core specifications and Pydantic data models.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class CopyItem(BaseModel):
    """单条推广文案结构体"""
    seq: int = Field(description="发布序号，如 1, 2, 41")
    title: str = Field(default="", description="文案标题")
    body: str = Field(description="文案正文主体")
    tags: str = Field(default="", description="话题标签，如 #Q9MArt")
    full_text: str = Field(description="组装后的纯享文案全文")
    content_hash: str = Field(description="基于标题和正文生成的唯一指纹 (SHA-256 前16位)")
    source_sheet: Optional[str] = Field(default=None, description="来源 Sheet 名称")
    source_row: Optional[int] = Field(default=None, description="来源行号")


class PlatformBlock(BaseModel):
    """单一平台的分发块定义"""
    platform: str = Field(description="平台名称，如 '今日头条', '小红书', '微信公众号', '抖音'")
    source_sheet: Optional[str] = Field(default=None, description="指定来源 Sheet 名称，若为空则由调度器自适应分配")
    with_tags: bool = Field(default=False, description="是否在该平台文案后追加话题标签")
    custom_alias: Optional[str] = Field(default=None, description="自定义分类标题，如 '以下是【微信公众号】文案'")


class TaskSpec(BaseModel):
    """声明式任务规约"""
    campaign: str = Field(default="default_campaign", description="所属战役/活动名称")
    workbook_path: str = Field(description="素材 Excel 路径")
    owner: str = Field(description="执行节点/责任人标识，如 '恒恒', '宝哥', '主控节点'")
    seq_start: int = Field(default=1, ge=1, description="起始序号")
    count: int = Field(default=10, ge=1, description="需要分发的人数/套数")
    blocks: List[PlatformBlock] = Field(description="包含的发布平台列表")
    same_copy_across_platforms: bool = Field(
        default=False,
        description="多平台是否复用同一套正文内容（如头条+公众号使用同一篇文案分别成套发送）"
    )
    target_chat: str = Field(default="文件传输助手", description="分发目标微信窗口/会话名")

    @field_validator("blocks")
    @classmethod
    def validate_blocks(cls, v: List[PlatformBlock]):
        if not v:
            raise ValueError("至少需要指定一个发布平台 block")
        return v


class ClarificationRequest(BaseModel):
    """当自然语言指令不完整或存在歧义时的追问模型"""
    need_clarification: bool = Field(default=True, description="是否需要向用户追问")
    missing_fields: List[str] = Field(default_factory=list, description="缺失的必要字段列表")
    questions: List[str] = Field(default_factory=list, description="具体追问问题")
    reason: str = Field(default="", description="歧义或缺失原因")
    partial_spec: Optional[TaskSpec] = Field(default=None, description="已成功解析出的部分规格")
