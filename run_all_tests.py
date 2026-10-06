# -*- coding: utf-8 -*-
"""
Direct test execution script to verify all tests rapidly.
"""
import sys
import os

# Safe UTF-8 configuration for Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tests.test_parser import test_clean_text, test_content_hash_consistency, test_parse_sample_workbook
from tests.test_ledger import test_ledger_record_and_check, test_ledger_stats
from tests.test_allocator import test_allocate_independent_platforms, test_allocate_same_copy_across_platforms, test_capacity_report
from tests.test_nl_parser import test_offline_rule_parsing_success, test_offline_rule_parsing_same_copy, test_proactive_clarification_on_missing_fields
from dispatcher.ledger import DispatchLedger
from dispatcher.parser import parse_workbook

import tempfile
import shutil


def run():
    passed = 0
    failed = 0

    tmp_dir = tempfile.mkdtemp()
    print(f"Running unit tests in temp dir: {tmp_dir}")

    # 1. Parser tests
    try:
        test_clean_text()
        test_content_hash_consistency()
        test_parse_sample_workbook()
        print("[PASS] test_parser: 3/3 passed")
        passed += 3
    except Exception as e:
        print(f"[FAIL] test_parser failed: {e}")
        failed += 1

    # 2. Ledger tests
    try:
        l1 = DispatchLedger(os.path.join(tmp_dir, "l1.db"))
        test_ledger_record_and_check(l1)
        l2 = DispatchLedger(os.path.join(tmp_dir, "l2.db"))
        test_ledger_stats(l2)
        print("[PASS] test_ledger: 2/2 passed")
        passed += 2
    except Exception as e:
        print(f"[FAIL] test_ledger failed: {e}")
        failed += 1

    # 3. Allocator tests
    try:
        mock_data = parse_workbook(os.path.join("examples", "sample_pool.xlsx"))
        al1 = DispatchLedger(os.path.join(tmp_dir, "al1.db"))
        test_allocate_independent_platforms(mock_data, al1)

        al2 = DispatchLedger(os.path.join(tmp_dir, "al2.db"))
        test_allocate_same_copy_across_platforms(mock_data, al2)

        al3 = DispatchLedger(os.path.join(tmp_dir, "al3.db"))
        test_capacity_report(mock_data, al3)
        print("[PASS] test_allocator: 3/3 passed")
        passed += 3
    except Exception as e:
        print(f"[FAIL] test_allocator failed: {e}")
        failed += 1

    # 4. NL Parser tests
    try:
        test_offline_rule_parsing_success()
        test_offline_rule_parsing_same_copy()
        test_proactive_clarification_on_missing_fields()
        print("[PASS] test_nl_parser: 3/3 passed")
        passed += 3
    except Exception as e:
        print(f"[FAIL] test_nl_parser failed: {e}")
        failed += 1

    shutil.rmtree(tmp_dir, ignore_errors=True)
    print("-----------------------------------------")
    print(f"TEST RESULTS: {passed} PASSED, {failed} FAILED")
    return failed == 0


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
