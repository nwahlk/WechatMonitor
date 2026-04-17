"""运行报告：汇总检查结果，输出到控制台"""

from datetime import datetime

from .storage import ResultStorage


def print_report(storage: ResultStorage, task_name: str, limit: int = 20) -> None:
    """打印最近检查结果汇总"""
    rows = storage.query(task_name=task_name, limit=limit)
    if not rows:
        print("暂无检查记录。")
        return

    # 按检查时间分组（同一批次的多条记录视为一次检查）
    batches: dict[str, list[dict]] = {}
    for row in rows:
        ts = row["checked_at"][:16]  # 精确到分钟
        batches.setdefault(ts, []).append(row)

    print()
    print("=" * 62)
    print(f"  API 健康监控报告 — {task_name}")
    print(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 62)

    # 最近一次检查详情
    latest_ts = list(batches.keys())[0]
    latest = batches[latest_ts]
    all_pass = all(r["status"] == "pass" for r in latest)

    status_icon = "OK" if all_pass else "!!"
    print(f"\n  最近一次检查: {latest_ts}  [{status_icon}]\n")
    print(f"  {'端点':<20} {'状态':<6} {'状态码':<8} {'延迟':<10} {'详情'}")
    print(f"  {'-'*20} {'-'*6} {'-'*8} {'-'*10} {'-'*16}")
    for r in latest:
        status = r["status"].upper()
        latency = f'{r["latency_ms"]:.0f}ms' if r["latency_ms"] else "-"
        code = str(r["status_code"]) if r["status_code"] else "-"
        details = (r["details"] or "-")[:16]
        print(f"  {r['endpoint_name']:<20} {status:<6} {code:<8} {latency:<10} {details}")

    # 基础统计摘要
    total = len(rows)
    passed = sum(1 for r in rows if r["status"] == "pass")
    failed = sum(1 for r in rows if r["status"] == "fail")
    errors = sum(1 for r in rows if r["status"] == "error")
    avg_latency = sum(r["latency_ms"] for r in rows if r["latency_ms"]) / max(total, 1)

    print(f"\n  统计 (最近 {total} 条):")
    print(f"    通过: {passed}  失败: {failed}  错误: {errors}")
    print(f"    平均延迟: {avg_latency:.0f}ms")
    print(f"    通过率: {passed / max(total, 1) * 100:.0f}%")
    print("=" * 62)
    print()


def print_metrics_report(storage: ResultStorage, task_name: str) -> None:
    """打印今日详细指标报告（P95/P99 延迟、端点可用率、连续失败）"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    metrics = storage.query_metrics(task_name, since=today_str)

    lp = metrics["latency_percentiles"]
    ep_stats = metrics["endpoint_stats"]
    consecutive = metrics["consecutive_failures"]

    if not ep_stats:
        print("今日暂无检查记录。")
        return

    print()
    print("=" * 62)
    print(f"  API 监控指标报告 — {task_name}")
    print(f"  日期: {today_str}")
    print("=" * 62)

    # 延迟分位
    print(f"\n  延迟分布:")
    print(f"    P50: {lp['p50']:.0f}ms  |  P95: {lp['p95']:.0f}ms  |  P99: {lp['p99']:.0f}ms")
    print(f"    平均: {lp['avg']:.0f}ms")

    # 端点可用率（按可用率升序，展示最低的 10 个 + 不可用的）
    sorted_eps = sorted(ep_stats.items(), key=lambda x: x[1]["availability"])
    unhealthy = [(name, s) for name, s in sorted_eps if s["availability"] < 100]

    print(f"\n  端点可用率 (共 {len(ep_stats)} 个):")
    if unhealthy:
        print(f"    {'端点':<28} {'检查':<6} {'通过':<6} {'可用率'}")
        print(f"    {'-'*28} {'-'*6} {'-'*6} {'-'*8}")
        for name, s in unhealthy[:20]:
            print(f"    {name:<28} {s['total']:<6} {s['passed']:<6} {s['availability']:.1f}%")
    else:
        print("    全部端点可用率 100%")

    healthy_count = sum(1 for _, s in ep_stats.items() if s["availability"] == 100)
    print(f"    健康: {healthy_count}/{len(ep_stats)}")

    # 连续失败
    failing = {name: count for name, count in consecutive.items() if count > 0}
    if failing:
        print(f"\n  连续失败 (当前):")
        for name, count in sorted(failing.items(), key=lambda x: -x[1]):
            print(f"    !! {name}: 连续失败 {count} 次")
    else:
        print(f"\n  连续失败: 无")

    print("=" * 62)
    print()
