import pytest
from api_monitor.config import Endpoint
from api_monitor.checker import check_endpoint, CheckResult


class TestCheckEndpoint:
    """使用 httpx MockTransport 测试，不发起真实 HTTP 请求"""

    def _make_endpoint(self, **overrides):
        defaults = {
            "name": "test-api",
            "url": "https://api.example.com/test",
            "method": "GET",
            "body": None,
            "headers": {},
            "expected_status": 200,
            "expected_fields": [],
            "timeout": 10,
        }
        defaults.update(overrides)
        return Endpoint(**defaults)

    def test_pass_when_status_matches(self):
        ep = self._make_endpoint()

        def handler(request):
            import httpx
            return httpx.Response(200, json={"data": "ok"})

        import httpx
        transport = httpx.MockTransport(handler)
        result = check_endpoint(ep, transport=transport)

        assert result.passed is True
        assert result.status_code == 200
        assert result.endpoint_name == "test-api"

    def test_fail_when_status_mismatch(self):
        ep = self._make_endpoint(expected_status=200)

        def handler(request):
            import httpx
            return httpx.Response(500, json={"error": "internal"})

        import httpx
        transport = httpx.MockTransport(handler)
        result = check_endpoint(ep, transport=transport)

        assert result.passed is False
        assert result.status_code == 500

    def test_fail_when_expected_field_missing(self):
        ep = self._make_endpoint(expected_fields=["data", "missing_field"])

        def handler(request):
            import httpx
            return httpx.Response(200, json={"data": "ok"})

        import httpx
        transport = httpx.MockTransport(handler)
        result = check_endpoint(ep, transport=transport)

        assert result.passed is False
        assert "missing_field" in result.details

    def test_pass_when_all_fields_present(self):
        ep = self._make_endpoint(expected_fields=["data", "count"])

        def handler(request):
            import httpx
            return httpx.Response(200, json={"data": "ok", "count": 42})

        import httpx
        transport = httpx.MockTransport(handler)
        result = check_endpoint(ep, transport=transport)

        assert result.passed is True

    def test_error_on_timeout(self):
        """MockTransport 不遵守 timeout，通过抛出 TimeoutException 模拟超时"""
        ep = self._make_endpoint(timeout=10)

        def handler(request):
            import httpx
            raise httpx.ReadTimeout("模拟超时")

        import httpx
        transport = httpx.MockTransport(handler)
        result = check_endpoint(ep, transport=transport)

        assert result.passed is False
        assert result.status_code is None
        assert "timeout" in result.details.lower() or "timed out" in result.details.lower() or "超时" in result.details

    def test_error_on_connection_failure(self):
        ep = self._make_endpoint(url="https://nonexistent.invalid.test/api")

        result = check_endpoint(ep)

        assert result.passed is False
        assert result.status_code is None

    def test_latency_ms_recorded(self):
        ep = self._make_endpoint()

        def handler(request):
            import httpx
            return httpx.Response(200, json={})

        import httpx
        transport = httpx.MockTransport(handler)
        result = check_endpoint(ep, transport=transport)

        assert result.latency_ms > 0

    def test_post_with_body(self):
        ep = self._make_endpoint(method="POST", body='{"page": 1}')

        def handler(request):
            import httpx
            import json
            body = json.loads(request.content)
            assert body["page"] == 1
            return httpx.Response(200, json={"list": []})

        import httpx
        transport = httpx.MockTransport(handler)
        result = check_endpoint(ep, transport=transport)

        assert result.passed is True

    def test_non_json_response(self):
        """后端返回非 JSON 时不应崩溃"""
        ep = self._make_endpoint()

        def handler(request):
            import httpx
            return httpx.Response(200, text="not json", headers={"content-type": "text/plain"})

        import httpx
        transport = httpx.MockTransport(handler)
        result = check_endpoint(ep, transport=transport)

        assert result.passed is True
        assert result.status_code == 200

    def test_non_json_response_with_expected_fields(self):
        """期望 JSON 字段但响应非 JSON 时应失败"""
        ep = self._make_endpoint(expected_fields=["data"])

        def handler(request):
            import httpx
            return httpx.Response(200, text="not json", headers={"content-type": "text/plain"})

        import httpx
        transport = httpx.MockTransport(handler)
        result = check_endpoint(ep, transport=transport)

        assert result.passed is False
