# -*- coding: utf-8 -*-
import os
import pytest
from dispatcher.ledger import DispatchLedger


@pytest.fixture
def temp_ledger(tmp_path):
    db_file = str(tmp_path / "test_ledger.db")
    return DispatchLedger(db_file)


def test_ledger_record_and_check(temp_ledger):
    hash_val = "abc123def4567890"
    assert not temp_ledger.is_hash_used(hash_val)

    temp_ledger.record_dispatch(
        content_hash=hash_val,
        campaign="test_camp",
        owner="恒恒",
        platform="今日头条",
        seq=1,
        title="测试标题"
    )

    assert temp_ledger.is_hash_used(hash_val)
    used_set = temp_ledger.get_used_hashes(campaign="test_camp")
    assert hash_val in used_set


def test_ledger_stats(temp_ledger):
    temp_ledger.record_dispatch("hash1", "camp1", "恒恒", "头条", 1)
    temp_ledger.record_dispatch("hash2", "camp1", "宝哥", "小红书", 1)
    temp_ledger.record_dispatch("hash1", "camp1", "恒恒", "公众号", 1)  # 同文案另一平台

    stats = temp_ledger.get_stats()
    assert stats["total_dispatches"] == 3
    assert stats["unique_copies"] == 2
    assert stats["total_owners"] == 2
    assert stats["total_platforms"] == 3
