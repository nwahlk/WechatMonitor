# tests/test_api_scheduler.py
from unittest.mock import patch

import pytest

from api_monitor.config import MonitorConfig, Endpoint
from api_monitor.scheduler import MonitorScheduler


@pytest.fixture
def config():
    return MonitorConfig(
        task_name="test-task",
        interval_minutes=1,
        endpoints=[
            Endpoint(
                name="test-api",
                url="https://httpbin.org/get",
                method="GET",
                expected_status=200,
            )
        ],
    )


class TestMonitorScheduler:
    def test_runs_check_immediately(self, config, tmp_path):
        """调度器启动后应立即执行一次检查"""
        scheduler = MonitorScheduler(config, db_path=str(tmp_path / "test.db"))
        scheduler.run_once()

        results = scheduler.storage.query()
        assert len(results) == 1
        assert results[0]["endpoint_name"] == "test-api"
        assert results[0]["task_name"] == "test-task"
        scheduler.stop()

    def test_runs_all_endpoints(self, tmp_path):
        """一次检查应覆盖所有端点"""
        config = MonitorConfig(
            task_name="multi-task",
            interval_minutes=1,
            endpoints=[
                Endpoint(name="api-1", url="https://httpbin.org/get", method="GET", expected_status=200),
                Endpoint(name="api-2", url="https://httpbin.org/status/200", method="GET", expected_status=200),
            ],
        )
        scheduler = MonitorScheduler(config, db_path=str(tmp_path / "test.db"))
        scheduler.run_once()

        results = scheduler.storage.query()
        assert len(results) == 2
        scheduler.stop()

    def test_records_failures(self, tmp_path):
        """失败的检查也应被记录"""
        config = MonitorConfig(
            task_name="fail-task",
            interval_minutes=1,
            endpoints=[
                Endpoint(name="will-fail", url="https://httpbin.org/status/500", method="GET", expected_status=200),
            ],
        )
        scheduler = MonitorScheduler(config, db_path=str(tmp_path / "test.db"))
        scheduler.run_once()

        results = scheduler.storage.query()
        assert len(results) == 1
        assert results[0]["status"] == "fail"
        scheduler.stop()
