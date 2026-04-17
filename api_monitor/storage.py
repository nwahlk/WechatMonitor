"""API 检查结果持久化（sqlite3）"""

import sqlite3
from datetime import datetime
from pathlib import Path

from .checker import CheckResult


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS api_check_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name TEXT NOT NULL,
    endpoint_name TEXT NOT NULL,
    status TEXT NOT NULL,
    status_code INTEGER,
    latency_ms REAL,
    details TEXT,
    checked_at TEXT NOT NULL
);
"""


class ResultStorage:
    """API 检查结果存储"""

    def __init__(self, db_path: str = "data/api_monitor.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_CREATE_TABLE_SQL)
        self.conn.commit()

    def save(self, task_name: str, result: CheckResult) -> None:
        """保存单条检查结果"""
        if result.passed:
            status = "pass"
        elif result.status_code is not None:
            status = "fail"
        else:
            status = "error"

        self.conn.execute(
            "INSERT INTO api_check_results (task_name, endpoint_name, status, status_code, latency_ms, details, checked_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                task_name,
                result.endpoint_name,
                status,
                result.status_code,
                result.latency_ms,
                result.details,
                datetime.now().isoformat(),
            ),
        )
        self.conn.commit()

    def query(self, task_name: str | None = None, limit: int = 50) -> list[dict]:
        """查询检查结果，按时间倒序"""
        if task_name:
            rows = self.conn.execute(
                "SELECT * FROM api_check_results WHERE task_name = ? ORDER BY id DESC LIMIT ?",
                (task_name, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM api_check_results ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()

    def query_metrics(
        self,
        task_name: str,
        since: str,
    ) -> dict:
        """查询指定时间段内的聚合指标

        Args:
            task_name: 任务名
            since: 起始时间 (ISO 格式前缀, 如 "2026-04-17")

        Returns:
            包含 latency_percentiles, endpoint_stats, consecutive_failures 的字典
        """
        rows = self.conn.execute(
            "SELECT endpoint_name, status, latency_ms FROM api_check_results "
            "WHERE task_name = ? AND checked_at >= ?",
            (task_name, since),
        ).fetchall()

        if not rows:
            return {"latency_percentiles": {}, "endpoint_stats": {}, "consecutive_failures": {}}

        # P50/P95/P99 延迟
        latencies = sorted(r["latency_ms"] for r in rows if r["latency_ms"])
        if latencies:
            import math
            def percentile(data: list[float], p: float) -> float:
                if not data:
                    return 0
                k = (len(data) - 1) * p / 100
                f = math.floor(k)
                c = math.ceil(k)
                if f == c:
                    return data[int(k)]
                return data[int(f)] * (c - k) + data[int(c)] * (k - f)

            latency_percentiles = {
                "p50": percentile(latencies, 50),
                "p95": percentile(latencies, 95),
                "p99": percentile(latencies, 99),
                "avg": sum(latencies) / len(latencies),
            }
        else:
            latency_percentiles = {"p50": 0, "p95": 0, "p99": 0, "avg": 0}

        # 每个端点的可用率 + 延迟统计
        ep_total: dict[str, int] = {}
        ep_pass: dict[str, int] = {}
        ep_latencies: dict[str, list[float]] = {}
        for r in rows:
            name = r["endpoint_name"]
            ep_total[name] = ep_total.get(name, 0) + 1
            if r["status"] == "pass":
                ep_pass[name] = ep_pass.get(name, 0) + 1
            if r["latency_ms"]:
                ep_latencies.setdefault(name, []).append(r["latency_ms"])

        endpoint_stats = {}
        for name in ep_total:
            t = ep_total[name]
            p = ep_pass.get(name, 0)
            lats = ep_latencies.get(name, [])
            endpoint_stats[name] = {
                "total": t,
                "passed": p,
                "availability": p / t * 100 if t else 0,
                "avg_latency": sum(lats) / len(lats) if lats else 0,
                "max_latency": max(lats) if lats else 0,
            }

        # 连续失败次数（按时间倒序，从最新往前数）
        latest_rows = self.conn.execute(
            "SELECT endpoint_name, status FROM api_check_results "
            "WHERE task_name = ? AND checked_at >= ? "
            "ORDER BY id DESC",
            (task_name, since),
        ).fetchall()

        consecutive: dict[str, int] = {}
        for r in latest_rows:
            name = r["endpoint_name"]
            if name in consecutive:
                continue  # 已统计完
            count = 0
            for r2 in latest_rows:
                if r2["endpoint_name"] == name:
                    if r2["status"] == "pass":
                        break
                    count += 1
            consecutive[name] = count

        return {
            "latency_percentiles": latency_percentiles,
            "endpoint_stats": endpoint_stats,
            "consecutive_failures": consecutive,
        }
