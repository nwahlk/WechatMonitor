"""通知分发器：管理多个通知渠道"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from .handlers.base import NotificationHandler

if TYPE_CHECKING:
    from .handlers.feishu import FeishuHandler
    from .handlers.email import EmailHandler

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """管理多个通知渠道，按渠道类型区分发送内容"""

    def __init__(self, handlers: list[NotificationHandler]):
        self.handlers = handlers

    def _send(self, handler: NotificationHandler, subject: str, content: str) -> None:
        """向单个渠道发送通知"""
        try:
            handler.send(subject, content)
        except Exception as e:
            logger.error(f"通知发送异常 [{handler.__class__.__name__}]: {e}")

    def _send_all(self, subject: str, content: str) -> None:
        """向所有渠道发送相同内容"""
        for handler in self.handlers:
            self._send(handler, subject, content)

    def _send_feishu(self, subject: str, content: str) -> None:
        """仅发送给飞书渠道"""
        for handler in self.handlers:
            if handler.__class__.__name__ == "FeishuHandler":
                self._send(handler, subject, content)

    def _send_email(self, subject: str, content: str) -> None:
        """仅发送给邮件渠道"""
        for handler in self.handlers:
            if handler.__class__.__name__ == "EmailHandler":
                self._send(handler, subject, content)

    def notify_session_expired(self, task_name: str) -> None:
        """session 失效告警（飞书+邮件都发）"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        content = f"**任务:** {task_name}\n**时间:** {now}\n\nsession 已失效，请从小程序重新抓包获取新 session，更新 config/settings.yaml 后恢复监控。"
        self._send_all(f"[告警] {task_name} session 已失效", content)

    def notify_failure(
        self,
        task_name: str,
        failures: list[dict],
    ) -> None:
        """发送失败告警通知（飞书发摘要，邮件发详情）"""
        if not failures:
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 飞书：简短摘要（最多列 5 个失败）
        feishu_subject = f"[告警] {task_name} {len(failures)} 个接口失败"
        feishu_lines = [
            f"**任务:** {task_name}",
            f"**时间:** {now}",
            f"**失败数:** {len(failures)}",
            "",
        ]
        for f in failures[:5]:
            latency = f'{f["latency_ms"]:.0f}ms' if f.get("latency_ms") else "-"
            code = f.get("status_code", "-")
            feishu_lines.append(
                f"- {f['endpoint_name']} | {code} | {latency}"
            )
        if len(failures) > 5:
            feishu_lines.append(f"- ... 共 {len(failures)} 个")
        self._send_feishu(feishu_subject, "\n".join(feishu_lines))

        # 邮件：完整失败列表（HTML 表格）
        email_subject = f"[告警] {task_name} API 检查失败 ({len(failures)} 个)"
        rows_html = ""
        for f in failures:
            latency = f'{f["latency_ms"]:.0f}ms' if f.get("latency_ms") else "-"
            code = f.get("status_code", "-")
            rows_html += (
                f'<tr>'
                f'<td>{f["endpoint_name"]}</td>'
                f'<td style="text-align:center">{code}</td>'
                f'<td style="text-align:right">{latency}</td>'
                f'<td>{f.get("details", "-")}</td>'
                f'</tr>'
            )
        email_html = f"""<html><body style="font-family: -apple-system, 'Microsoft YaHei', sans-serif; color:#333; max-width:800px;">
<h2 style="color:#ff4d4f">API 检查告警</h2>
<p><b>任务:</b> {task_name} &nbsp; <b>时间:</b> {now} &nbsp; <b>失败数:</b> {len(failures)}</p>
<table style="border-collapse:collapse; font-size:13px">
<tr style="background:#fff1f0">
  <th style="border:1px solid #ddd; padding:6px 10px; text-align:left">端点</th>
  <th style="border:1px solid #ddd; padding:6px 10px; text-align:center">状态码</th>
  <th style="border:1px solid #ddd; padding:6px 10px; text-align:right">延迟</th>
  <th style="border:1px solid #ddd; padding:6px 10px; text-align:left">详情</th>
</tr>
{rows_html}
</table>
</body></html>"""
        self._send_email(email_subject, email_html)

    def notify_daily_summary(
        self,
        task_name: str,
        total: int,
        passed: int,
        failed: int,
        errors: int,
        avg_latency: float,
        failure_details: list[dict] | None = None,
        latency_percentiles: dict | None = None,
        endpoint_stats: dict | None = None,
        consecutive_failures: dict | None = None,
    ) -> None:
        """发送每日检查摘要（飞书发统计，邮件发详情）"""
        today = datetime.now().strftime("%Y-%m-%d")
        pass_rate = passed / max(total, 1) * 100
        lp = latency_percentiles or {}
        ep_stats = endpoint_stats or {}
        consecutive = consecutive_failures or {}

        # 飞书：统计摘要（紧凑）
        feishu_lines = [
            f"**{task_name}** 每日监控",
            f"日期: {today}",
            "",
            f"总: {total} | 通过: {passed} | 失败: {failed} | 错误: {errors}",
            f"通过率: {pass_rate:.1f}%",
            f"P50: {lp.get('p50', 0):.0f}ms | P95: {lp.get('p95', 0):.0f}ms | P99: {lp.get('p99', 0):.0f}ms",
        ]
        if consecutive:
            feishu_lines.append("")
            feishu_lines.append(f"连续失败: {len(consecutive)} 个端点")
        self._send_feishu(f"[日报] {task_name} 通过率 {pass_rate:.1f}%", "\n".join(feishu_lines))

        # 邮件：HTML 表格格式
        sorted_eps = sorted(ep_stats.items(), key=lambda x: (x[1]["availability"], -x[1]["max_latency"]))

        # 端点表格行
        rows_html = ""
        for name, s in sorted_eps:
            status = '<span style="color:#52c41a">OK</span>' if s["availability"] == 100 else '<span style="color:#ff4d4f">FAIL</span>'
            avg_ms = f'{s["avg_latency"]:.0f}' if s["avg_latency"] else "-"
            max_ms = f'{s["max_latency"]:.0f}' if s["max_latency"] else "-"
            rows_html += (
                f'<tr>'
                f'<td>{name}</td>'
                f'<td style="text-align:center">{status}</td>'
                f'<td style="text-align:center">{s["availability"]:.1f}%</td>'
                f'<td style="text-align:center">{s["passed"]}/{s["total"]}</td>'
                f'<td style="text-align:right">{avg_ms}ms</td>'
                f'<td style="text-align:right">{max_ms}ms</td>'
                f'</tr>'
            )

        # 连续失败
        consecutive_html = ""
        if consecutive:
            items = "".join(
                f'<li><b>{name}</b>: 连续失败 {count} 次</li>'
                for name, count in sorted(consecutive.items(), key=lambda x: -x[1])
            )
            consecutive_html = (
                f'<h3 style="color:#ff4d4f;margin-top:20px">连续失败</h3>'
                f'<ul style="margin:4px 0">{items}</ul>'
            )

        email_html = f"""<html><body style="font-family: -apple-system, 'Microsoft YaHei', sans-serif; color:#333; max-width:900px;">

<h2 style="margin-bottom:4px">{task_name} 每日监控报告</h2>
<p style="color:#888; margin-top:0">{today}</p>

<table style="border-collapse:collapse; margin-bottom:16px">
<tr style="background:#f5f5f5">
  <th style="border:1px solid #ddd; padding:8px 12px; text-align:left">总检查</th>
  <th style="border:1px solid #ddd; padding:8px 12px; text-align:center">通过</th>
  <th style="border:1px solid #ddd; padding:8px 12px; text-align:center">失败</th>
  <th style="border:1px solid #ddd; padding:8px 12px; text-align:center">错误</th>
  <th style="border:1px solid #ddd; padding:8px 12px; text-align:center">通过率</th>
  <th style="border:1px solid #ddd; padding:8px 12px; text-align:right">平均延迟</th>
</tr>
<tr>
  <td style="border:1px solid #ddd; padding:8px 12px; text-align:center"><b>{total}</b></td>
  <td style="border:1px solid #ddd; padding:8px 12px; text-align:center; color:#52c41a"><b>{passed}</b></td>
  <td style="border:1px solid #ddd; padding:8px 12px; text-align:center; color:{'#ff4d4f' if failed else '#333'}"><b>{failed}</b></td>
  <td style="border:1px solid #ddd; padding:8px 12px; text-align:center; color:{'#ff4d4f' if errors else '#333'}"><b>{errors}</b></td>
  <td style="border:1px solid #ddd; padding:8px 12px; text-align:center"><b>{pass_rate:.1f}%</b></td>
  <td style="border:1px solid #ddd; padding:8px 12px; text-align:right"><b>{avg_latency:.0f}ms</b></td>
</tr>
</table>

<p style="margin:4px 0">延迟分布: P50=<b>{lp.get('p50', 0):.0f}ms</b> | P95=<b>{lp.get('p95', 0):.0f}ms</b> | P99=<b>{lp.get('p99', 0):.0f}ms</b></p>

<h3 style="margin-top:20px">端点详情 (共 {len(sorted_eps)} 个)</h3>
<table style="border-collapse:collapse; font-size:13px">
<tr style="background:#f5f5f5">
  <th style="border:1px solid #ddd; padding:6px 10px; text-align:left">端点名称</th>
  <th style="border:1px solid #ddd; padding:6px 10px; text-align:center">状态</th>
  <th style="border:1px solid #ddd; padding:6px 10px; text-align:center">可用率</th>
  <th style="border:1px solid #ddd; padding:6px 10px; text-align:center">通过/总计</th>
  <th style="border:1px solid #ddd; padding:6px 10px; text-align:right">平均延迟</th>
  <th style="border:1px solid #ddd; padding:6px 10px; text-align:right">最大延迟</th>
</tr>
{rows_html}
</table>

{consecutive_html}

</body></html>"""

        self._send_email(f"[摘要] {task_name} 每日监控报告 ({today})", email_html)
