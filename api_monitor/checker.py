"""HTTP API 健康检查"""

import time
from dataclasses import dataclass

import httpx

from .config import Endpoint, MonitorConfig


@dataclass
class CheckResult:
    """单次端点检查结果"""
    endpoint_name: str
    passed: bool
    status_code: int | None = None
    latency_ms: float = 0
    details: str = ""


def check_endpoint(
    endpoint: Endpoint,
    base_url: str = "",
    shared_headers: dict | None = None,
    transport: httpx.BaseTransport | None = None,
) -> CheckResult:
    """
    检查单个 API 端点的可用性

    Args:
        endpoint: 端点配置
        base_url: URL 前缀，endpoint.url 以 / 开头时自动拼接
        shared_headers: 共享 headers，与 endpoint.headers 合并
        transport: 可选的 httpx transport（用于测试注入）

    Returns:
        CheckResult 检查结果
    """
    start = time.perf_counter()

    try:
        client_kwargs: dict = {
            "timeout": endpoint.timeout,
            "verify": False,
        }
        if transport is not None:
            client_kwargs["transport"] = transport

        with httpx.Client(**client_kwargs) as client:
            # 拼接 URL
            url = endpoint.url
            if base_url and url.startswith("/"):
                url = base_url.rstrip("/") + url

            # 合并 headers
            headers = {**(shared_headers or {}), **(endpoint.headers or {})}

            request_kwargs: dict = {
                "method": endpoint.method,
                "url": url,
                "headers": headers,
            }
            if endpoint.body:
                request_kwargs["content"] = endpoint.body

            response = client.request(**request_kwargs)

        latency_ms = (time.perf_counter() - start) * 1000

        # 状态码检查
        if response.status_code != endpoint.expected_status:
            return CheckResult(
                endpoint_name=endpoint.name,
                passed=False,
                status_code=response.status_code,
                latency_ms=latency_ms,
                details=f"状态码不匹配: 期望 {endpoint.expected_status}, 实际 {response.status_code}",
            )

        # JSON 字段检查
        if endpoint.expected_fields or endpoint.expected_data_fields:
            try:
                json_data = response.json()
            except Exception:
                return CheckResult(
                    endpoint_name=endpoint.name,
                    passed=False,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    details="响应不是有效的 JSON",
                )

            # 顶层字段检查
            if endpoint.expected_fields:
                if not isinstance(json_data, dict):
                    return CheckResult(
                        endpoint_name=endpoint.name,
                        passed=False,
                        status_code=response.status_code,
                        latency_ms=latency_ms,
                        details="响应体为空或非 JSON 对象",
                    )
                missing = [f for f in endpoint.expected_fields if f not in json_data]
                if missing:
                    return CheckResult(
                        endpoint_name=endpoint.name,
                        passed=False,
                        status_code=response.status_code,
                        latency_ms=latency_ms,
                        details=f"缺少字段: {', '.join(missing)}",
                    )

            # data 内部字段检查（验证 data[0] 包含关键信息）
            if endpoint.expected_data_fields:
                data_arr = json_data.get("data")
                if not isinstance(data_arr, list) or len(data_arr) == 0:
                    return CheckResult(
                        endpoint_name=endpoint.name,
                        passed=False,
                        status_code=response.status_code,
                        latency_ms=latency_ms,
                        details="data 为空或非数组",
                    )
                first_item = data_arr[0]
                missing = [f for f in endpoint.expected_data_fields if f not in first_item]
                if missing:
                    return CheckResult(
                        endpoint_name=endpoint.name,
                        passed=False,
                        status_code=response.status_code,
                        latency_ms=latency_ms,
                        details=f"data[0] 缺少字段: {', '.join(missing)}",
                    )

        return CheckResult(
            endpoint_name=endpoint.name,
            passed=True,
            status_code=response.status_code,
            latency_ms=latency_ms,
            details=f"HTTP {response.status_code}, {latency_ms:.0f}ms",
        )

    except httpx.TimeoutException:
        latency_ms = (time.perf_counter() - start) * 1000
        return CheckResult(
            endpoint_name=endpoint.name,
            passed=False,
            latency_ms=latency_ms,
            details=f"请求超时 ({endpoint.timeout}s)",
        )
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return CheckResult(
            endpoint_name=endpoint.name,
            passed=False,
            latency_ms=latency_ms,
            details=f"请求异常: {e}",
        )
