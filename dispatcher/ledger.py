# -*- coding: utf-8 -*-
"""
Robust dispatch ledger with dual engine support (SQLite + JSON File Fallback).
Tracks every dispatched copy item by SHA-256 content hash to prevent duplicates
across different users, days, platforms, and spreadsheet revisions.
"""

import os
import json
from typing import Set, Dict, Any, List, Optional
from datetime import datetime

# 尝试导入 sqlite3，若环境缺少 DLL 则安全降级为 JSON 文件存储
HAS_SQLITE = False
try:
    import sqlite3
    HAS_SQLITE = True
except ImportError:
    HAS_SQLITE = False


class DispatchLedger:
    def __init__(self, db_path: str = "ledger.db"):
        self.db_path = db_path
        self.use_sqlite = HAS_SQLITE
        if self.use_sqlite:
            try:
                self._init_sqlite()
            except Exception as e:
                # 若 SQLite 初始化异常，降级为 JSON 引擎
                self.use_sqlite = False
                self.json_path = self.db_path + ".json" if not self.db_path.endswith(".json") else self.db_path
                self._init_json()
        else:
            self.json_path = self.db_path + ".json" if not self.db_path.endswith(".json") else self.db_path
            self._init_json()

    # ================= SQLite 引擎实现 =================
    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_sqlite(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dispatched_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_hash TEXT NOT NULL,
                    campaign TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    title TEXT,
                    source_workbook TEXT,
                    source_sheet TEXT,
                    source_row INTEGER,
                    dispatched_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hash ON dispatched_history(content_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_campaign ON dispatched_history(campaign)")

    # ================= JSON 文件引擎实现 (容灾兜底) =================
    def _init_json(self):
        if not os.path.exists(self.json_path):
            self._save_json([])

    def _load_json(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.json_path):
            return []
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_json(self, records: List[Dict[str, Any]]):
        os.makedirs(os.path.dirname(os.path.abspath(self.json_path)) or ".", exist_ok=True)
        tmp = self.json_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        if os.path.exists(self.json_path):
            os.replace(tmp, self.json_path)
        else:
            os.rename(tmp, self.json_path)

    # ================= 统一对外公开接口 =================
    def is_hash_used(self, content_hash: str) -> bool:
        """检查特定内容指纹是否已经被分发过"""
        if self.use_sqlite:
            with self._get_conn() as conn:
                cur = conn.execute(
                    "SELECT 1 FROM dispatched_history WHERE content_hash = ? LIMIT 1",
                    (content_hash,)
                )
                return cur.fetchone() is not None
        else:
            records = self._load_json()
            return any(r["content_hash"] == content_hash for r in records)

    def get_used_hashes(self, campaign: Optional[str] = None) -> Set[str]:
        """获取所有已使用的内容哈希集合"""
        if self.use_sqlite:
            with self._get_conn() as conn:
                if campaign:
                    cur = conn.execute(
                        "SELECT content_hash FROM dispatched_history WHERE campaign = ?",
                        (campaign,)
                    )
                else:
                    cur = conn.execute("SELECT content_hash FROM dispatched_history")
                return {row[0] for row in cur.fetchall()}
        else:
            records = self._load_json()
            if campaign:
                return {r["content_hash"] for r in records if r.get("campaign") == campaign}
            return {r["content_hash"] for r in records}

    def record_dispatch(
        self,
        content_hash: str,
        campaign: str,
        owner: str,
        platform: str,
        seq: int,
        title: str = "",
        source_workbook: str = "",
        source_sheet: str = "",
        source_row: int = 0
    ) -> bool:
        """登记分发记录"""
        now = datetime.now().isoformat()
        if self.use_sqlite:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO dispatched_history
                    (content_hash, campaign, owner, platform, seq, title, source_workbook, source_sheet, source_row, dispatched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (content_hash, campaign, owner, platform, seq, title, source_workbook, source_sheet, source_row, now)
                )
            return True
        else:
            records = self._load_json()
            records.append({
                "content_hash": content_hash,
                "campaign": campaign,
                "owner": owner,
                "platform": platform,
                "seq": seq,
                "title": title,
                "source_workbook": source_workbook,
                "source_sheet": source_sheet,
                "source_row": source_row,
                "dispatched_at": now
            })
            self._save_json(records)
            return True

    def get_stats(self) -> Dict[str, Any]:
        """获取台账汇总统计"""
        if self.use_sqlite:
            with self._get_conn() as conn:
                cur = conn.execute("SELECT COUNT(*), COUNT(DISTINCT content_hash) FROM dispatched_history")
                total_records, unique_copies = cur.fetchone()

                cur = conn.execute("SELECT COUNT(DISTINCT owner), COUNT(DISTINCT platform) FROM dispatched_history")
                owners_count, platforms_count = cur.fetchone()

                cur = conn.execute("SELECT owner, COUNT(*) FROM dispatched_history GROUP BY owner")
                owner_breakdown = dict(cur.fetchall())

                cur = conn.execute("SELECT platform, COUNT(*) FROM dispatched_history GROUP BY platform")
                platform_breakdown = dict(cur.fetchall())

                return {
                    "total_dispatches": total_records or 0,
                    "unique_copies": unique_copies or 0,
                    "total_owners": owners_count or 0,
                    "total_platforms": platforms_count or 0,
                    "by_owner": owner_breakdown,
                    "by_platform": platform_breakdown,
                    "engine": "SQLite"
                }
        else:
            records = self._load_json()
            total_records = len(records)
            unique_copies = len({r["content_hash"] for r in records})
            owners = {r["owner"] for r in records}
            platforms = {r["platform"] for r in records}

            owner_breakdown = {}
            for r in records:
                o = r["owner"]
                owner_breakdown[o] = owner_breakdown.get(o, 0) + 1

            platform_breakdown = {}
            for r in records:
                p = r["platform"]
                platform_breakdown[p] = platform_breakdown.get(p, 0) + 1

            return {
                "total_dispatches": total_records,
                "unique_copies": unique_copies,
                "total_owners": len(owners),
                "total_platforms": len(platforms),
                "by_owner": owner_breakdown,
                "by_platform": platform_breakdown,
                "engine": "JSON_Fallback"
            }

    def clear(self):
        """清空台账"""
        if self.use_sqlite:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM dispatched_history")
        else:
            self._save_json([])
