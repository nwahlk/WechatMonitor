"""从 api-docs.json 自动生成监控配置"""

import json
from pathlib import Path

import yaml

# 需要参数的接口的示例值
DEFAULT_PARAMS = {
    "indexCode": "000300",
    "fundCode": "510300",
    "productCode": "510300",
    "isEtf": "true",
    "gridType": "1",
    "type": "1",
    "keyword": "沪深300",
    "startDate": "2025-01-01",
    "endDate": "2025-12-31",
    "day": "5",
    "managerId": "1",
    "StrategyId": "1",
    "filePath": "test",
    "code": "test",
    "encryptedData": "test",
    "iv": "test",
    "levelCode": "",
    "noPagination": "true",
    "pageNo": "1",
    "pageSize": "10",
    "sortDirection": "desc",
    "sortKey": "",
    "clas": "",
    "dataDate": "",
    "keyWord": "",
    "n": "10",
    "benchmark": "000300",
    "unionId": "",
}

# 跳过的 tag
SKIP_TAGS = {"调度任务", "测试", "外部应用调用且非互联网接口"}

# 跳过的接口（路径 -> 原因）
SKIP_ENDPOINTS = {
    "/etfapp/retail/user-info/getProfile": "返回文件流，非 JSON",
}

BASE_URL = "https://etfapp.euler.southernfund.com:13000"

# Session 示例值（需要定期更新）
SESSION = "b6ace0ba-4b57-4a29-9872-c3477279a489"


def main():
    docs_path = Path(__file__).parent.parent / "api-docs.json"
    output_path = Path(__file__).parent.parent / "config" / "api_monitor.yaml"

    with open(docs_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    paths = data.get("paths", {})
    schemas = data.get("components", {}).get("schemas", {})

    endpoints = []

    for path, methods in paths.items():
        for method, detail in methods.items():
            if method not in ("get", "post"):
                continue

            tags = detail.get("tags", [])
            summary = detail.get("summary", path)

            if any(t in tags for t in SKIP_TAGS):
                continue
            if path in SKIP_ENDPOINTS:
                continue

            # 生成端点名（同名时加方法后缀区分）
            tag_label = tags[0] if tags else "other"
            method_upper = method.upper()
            name = summary

            # 处理 query 参数
            params = detail.get("parameters", [])
            query_parts = []
            body_fields = {}

            for p in params:
                pname = p.get("name", "")
                if pname == "session":
                    continue
                ptype = p.get("schema", {}).get("type", "string")
                prequired = p.get("required", False)

                value = DEFAULT_PARAMS.get(pname, "1")
                if ptype == "integer" and value.isdigit():
                    value = str(int(value))
                if ptype == "boolean":
                    value = "true"

                if prequired or DEFAULT_PARAMS.get(pname):
                    query_parts.append(f"{pname}={value}")

            # 处理 request body
            req_body = detail.get("requestBody", {})
            if req_body:
                content = req_body.get("content", {})
                for ct, cv in content.items():
                    schema = cv.get("schema", {})
                    ref = schema.get("$ref", "")
                    if ref:
                        schema_name = ref.split("/")[-1]
                        if schema_name in schemas:
                            props = schemas[schema_name].get("properties", {})
                            for pname, pdef in props.items():
                                ptype = pdef.get("type", "string")
                                default_val = DEFAULT_PARAMS.get(pname, "")
                                if ptype == "integer" and default_val.isdigit():
                                    default_val = str(int(default_val))
                                if ptype == "boolean":
                                    default_val = True if default_val == "true" else False
                                body_fields[pname] = default_val

            # 构造 URL（相对路径 + query 参数）
            url = path
            if query_parts:
                url = f"{path}?{'&'.join(query_parts)}"

            # 构造 body（仅 POST）
            body = None
            if method == "post":
                if body_fields:
                    body = json.dumps(body_fields, ensure_ascii=False)
                else:
                    body = "{}"

            # 构造 headers
            headers = {}
            if body:
                headers["Content-Type"] = "application/json"

            # 判断是否需要 session（用户相关接口）
            needs_session = any(
                t in tags
                for t in ["权限", "自选列表", "哑铃策略", "网格策略", "风格轮动",
                          "用户行为", "小程序-订阅管理", "时点动量"]
            )
            if needs_session or any(p.get("name") == "session" for p in params):
                headers["session"] = SESSION

            ep = {
                "name": summary,
                "url": url,
                "method": method_upper,
                "expected_status": 200,
                "expected_fields": ["code", "message"],
                "timeout": 10,
            }
            if body:
                ep["body"] = body
            if headers:
                ep["headers"] = headers
            endpoints.append(ep)

    # 去重：同名端点加上方法后缀，仍重复则加路径编号
    name_count: dict[str, int] = {}
    for ep in endpoints:
        name = ep["name"]
        name_count[name] = name_count.get(name, 0) + 1
    # 第一轮：加方法后缀
    for ep in endpoints:
        if name_count[ep["name"]] > 1:
            ep["name"] = f"{ep['name']}({ep['method']})"
    # 第二轮：仍重复则加编号
    name_count2: dict[str, int] = {}
    for ep in endpoints:
        name = ep["name"]
        name_count2[name] = name_count2.get(name, 0) + 1
    for ep in endpoints:
        if name_count2[ep["name"]] > 1:
            name_count2[ep["name"]] -= 1
            ep["name"] = f"{ep['name']}#{name_count2[ep['name']]}"

    # 生成 YAML
    config = {
        "base_url": BASE_URL,
        "shared_headers": {
            "Content-Type": "application/json",
        },
        "task": {
            "name": "etfapp-api-monitor",
            "interval_minutes": 5,
        },
        "endpoints": endpoints,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"已生成 {len(endpoints)} 个端点配置 -> {output_path}")

    get_count = sum(1 for e in endpoints if e["method"] == "GET")
    post_count = sum(1 for e in endpoints if e["method"] == "POST")
    with_session = sum(1 for e in endpoints if e.get("headers") and "session" in e["headers"])
    print(f"  GET: {get_count}, POST: {post_count}")
    print(f"  需要 session: {with_session}")


if __name__ == "__main__":
    main()
