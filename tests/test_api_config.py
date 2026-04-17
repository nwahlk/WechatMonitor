# tests/test_api_config.py
import pytest
from pathlib import Path


@pytest.fixture
def sample_config_path(tmp_path):
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("""
task:
  name: test-task
  interval_minutes: 5

endpoints:
  - name: 首页数据
    url: https://api.example.com/home
    method: GET
    expected_status: 200
    expected_fields: ["banner", "menu"]
    timeout: 10
  - name: 业务接口
    url: https://api.example.com/data
    method: POST
    body: '{"page": 1}'
    expected_status: 200
    expected_fields: ["list"]
    timeout: 10
    headers:
      Authorization: "Bearer test-token"
""", encoding="utf-8")
    return config_file


class TestLoadConfig:
    def test_loads_task_name(self, sample_config_path):
        from api_monitor.config import load_config
        config = load_config(sample_config_path)
        assert config.task_name == "test-task"

    def test_loads_interval(self, sample_config_path):
        from api_monitor.config import load_config
        config = load_config(sample_config_path)
        assert config.interval_minutes == 5

    def test_loads_endpoints(self, sample_config_path):
        from api_monitor.config import load_config
        config = load_config(sample_config_path)
        assert len(config.endpoints) == 2

    def test_endpoint_fields(self, sample_config_path):
        from api_monitor.config import load_config
        config = load_config(sample_config_path)
        ep = config.endpoints[0]
        assert ep.name == "首页数据"
        assert ep.url == "https://api.example.com/home"
        assert ep.method == "GET"
        assert ep.expected_status == 200
        assert ep.expected_fields == ["banner", "menu"]
        assert ep.timeout == 10
        assert ep.body is None
        assert ep.headers == {}

    def test_endpoint_with_body_and_headers(self, sample_config_path):
        from api_monitor.config import load_config
        config = load_config(sample_config_path)
        ep = config.endpoints[1]
        assert ep.method == "POST"
        assert ep.body == '{"page": 1}'
        assert ep.headers == {"Authorization": "Bearer test-token"}

    def test_defaults_when_optional_missing(self, tmp_path):
        config_file = tmp_path / "minimal.yaml"
        config_file.write_text("""
task:
  name: minimal
endpoints:
  - name: test
    url: https://example.com
    method: GET
    expected_status: 200
""", encoding="utf-8")
        from api_monitor.config import load_config
        config = load_config(config_file)
        assert config.interval_minutes == 5
        ep = config.endpoints[0]
        assert ep.expected_fields == []
        assert ep.timeout == 10
        assert ep.body is None
        assert ep.headers == {}

    def test_file_not_found_raises(self):
        from api_monitor.config import load_config
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.yaml")
