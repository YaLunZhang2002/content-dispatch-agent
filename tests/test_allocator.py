# -*- coding: utf-8 -*-
import os
import pytest
from dispatcher.spec import TaskSpec, PlatformBlock
from dispatcher.ledger import DispatchLedger
from dispatcher.allocator import CopyAllocator
from dispatcher.parser import parse_workbook


@pytest.fixture
def mock_workbook_data():
    sample_path = os.path.join("examples", "sample_pool.xlsx")
    return parse_workbook(sample_path)


@pytest.fixture
def clean_ledger(tmp_path):
    db_file = str(tmp_path / "test_allocator.db")
    return DispatchLedger(db_file)


def test_allocate_independent_platforms(mock_workbook_data, clean_ledger):
    allocator = CopyAllocator(clean_ledger)
    spec = TaskSpec(
        campaign="test",
        workbook_path="dummy",
        owner="恒恒",
        seq_start=1,
        count=5,
        same_copy_across_platforms=False,
        blocks=[
            PlatformBlock(platform="今日头条", source_sheet="今日头条"),
            PlatformBlock(platform="小红书", source_sheet="小红书", with_tags=True)
        ]
    )

    payloads = allocator.allocate(spec, mock_workbook_data)
    assert len(payloads) == 2

    tt_payload = payloads[0]
    xhs_payload = payloads[1]

    assert len(tt_payload.items) == 5
    assert len(xhs_payload.items) == 5
    assert tt_payload.items[0].seq == 1
    assert tt_payload.items[-1].seq == 5

    # 两个平台文案不重复
    tt_hashes = {it.content_hash for it in tt_payload.items}
    xhs_hashes = {it.content_hash for it in xhs_payload.items}
    assert tt_hashes.isdisjoint(xhs_hashes)


def test_allocate_same_copy_across_platforms(mock_workbook_data, clean_ledger):
    allocator = CopyAllocator(clean_ledger)
    spec = TaskSpec(
        campaign="test",
        workbook_path="dummy",
        owner="亚伦",
        seq_start=11,
        count=5,
        same_copy_across_platforms=True,
        blocks=[
            PlatformBlock(platform="今日头条", source_sheet="今日头条"),
            PlatformBlock(platform="微信公众号", source_sheet="今日头条")
        ]
    )

    payloads = allocator.allocate(spec, mock_workbook_data)
    assert len(payloads) == 2

    tt_hashes = [it.content_hash for it in payloads[0].items]
    gzh_hashes = [it.content_hash for it in payloads[1].items]
    # 同文案模式下，两个平台的文案指纹严格一致
    assert tt_hashes == gzh_hashes


def test_capacity_report(mock_workbook_data, clean_ledger):
    allocator = CopyAllocator(clean_ledger)
    report = allocator.get_capacity_report(mock_workbook_data)
    assert report["total_pool"] == 110  # 40+40+30
    assert report["total_available"] == 110
    assert report["total_dispatched"] == 0
