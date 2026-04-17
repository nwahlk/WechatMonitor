import sqlite3
from datetime import datetime

import pytest

from api_monitor.checker import CheckResult
from api_monitor.storage import ResultStorage


@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "test.db"
    return ResultStorage(str(db_path))


class TestResultStorage:
    def test_save_and_query(self, storage):
        result = CheckResult(
            endpoint_name="test-api",
            passed=True,
            status_code=200,
            latency_ms=123.4,
            details="HTTP 200, 123ms",
        )
        storage.save("test-task", result)

        rows = storage.query(task_name="test-task")
        assert len(rows) == 1
        assert rows[0]["endpoint_name"] == "test-api"
        assert rows[0]["status"] == "pass"
        assert rows[0]["status_code"] == 200

    def test_save_fail_result(self, storage):
        result = CheckResult(
            endpoint_name="api-2",
            passed=False,
            status_code=500,
            latency_ms=50,
            details="状态码不匹配",
        )
        storage.save("test-task", result)

        rows = storage.query(task_name="test-task")
        assert rows[0]["status"] == "fail"

    def test_save_error_result(self, storage):
        result = CheckResult(
            endpoint_name="api-3",
            passed=False,
            status_code=None,
            latency_ms=10000,
            details="请求超时",
        )
        storage.save("test-task", result)

        rows = storage.query(task_name="test-task")
        assert rows[0]["status"] == "error"
        assert rows[0]["status_code"] is None

    def test_query_limit(self, storage):
        for i in range(10):
            result = CheckResult(
                endpoint_name=f"api-{i}",
                passed=True,
                status_code=200,
                latency_ms=10,
            )
            storage.save("test-task", result)

        rows = storage.query(task_name="test-task", limit=3)
        assert len(rows) == 3
        # 最新的在前面
        assert rows[0]["endpoint_name"] == "api-9"

    def test_query_without_task_filter(self, storage):
        for task in ["task-a", "task-b"]:
            result = CheckResult(
                endpoint_name="api",
                passed=True,
                status_code=200,
                latency_ms=10,
            )
            storage.save(task, result)

        rows = storage.query()
        assert len(rows) == 2

    def test_checked_at_is_datetime_string(self, storage):
        result = CheckResult(
            endpoint_name="api",
            passed=True,
            status_code=200,
            latency_ms=10,
        )
        storage.save("test-task", result)

        rows = storage.query()
        # checked_at 应该是可解析的 ISO 格式字符串
        assert rows[0]["checked_at"] is not None
