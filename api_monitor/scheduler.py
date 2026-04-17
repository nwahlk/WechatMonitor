"""定时调度：串联配置、检查、存储、通知"""

import logging
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .checker import check_endpoint, CheckResult
from .config import MonitorConfig
from .report import print_report
from .storage import ResultStorage

logger = logging.getLogger(__name__)


class MonitorScheduler:
    """API 监控调度器"""

    def __init__(self, config: MonitorConfig, db_path: str = "data/api_monitor.db"):
        self.config = config
        self.storage = ResultStorage(db_path)
        self._scheduler = BlockingScheduler()
        self._dispatcher = None

        # 延迟导入通知模块，避免循环依赖
        if config.notification.enabled and config.notification.has_channels:
            self._init_dispatcher()

    def _init_dispatcher(self):
        """根据配置初始化通知分发器"""
        from alerting.dispatcher import NotificationDispatcher
        from alerting.handlers import FeishuHandler, EmailHandler

        notif = self.config.notification
        handlers = []

        if notif.feishu.webhook_url:
            handlers.append(FeishuHandler(
                webhook_url=notif.feishu.webhook_url,
                secret=notif.feishu.secret,
            ))

        if notif.email.sender and notif.email.receivers:
            handlers.append(EmailHandler(
                smtp_host=notif.email.smtp_host,
                smtp_port=notif.email.smtp_port,
                sender=notif.email.sender,
                password=notif.email.password,
                receivers=notif.email.receivers,
            ))

        if handlers:
            self._dispatcher = NotificationDispatcher(handlers)
            logger.info(f"通知渠道已启用: {len(handlers)} 个")
        else:
            logger.warning("通知配置存在但无有效渠道，跳过通知初始化")

    def _is_within_schedule(self) -> bool:
        """判断当前时间是否在配置的执行时间段内"""
        hour = datetime.now().hour
        start = self.config.schedule.start_hour
        end = self.config.schedule.end_hour
        if start < end:
            return start <= hour < end
        elif start > end:
            # 跨午夜，如 22:00-06:00
            return hour >= start or hour < end
        else:
            # start == end（默认 0,24）表示全天
            return True

    def _check_session(self) -> bool:
        """预检 session 是否有效（调用 basicInfo 接口）"""
        import httpx

        url = f"{self.config.base_url}/etfapp/retail/auth/basicInfo"
        try:
            with httpx.Client(timeout=10, verify=False) as client:
                resp = client.get(url, headers=self.config.shared_headers)
            data = resp.json()
            # code=="00000" 表示 session 有效
            return isinstance(data, dict) and data.get("code") == "00000"
        except Exception:
            return False

    def _run_checks(self):
        """执行所有端点的健康检查"""
        if not self._is_within_schedule():
            logger.debug("当前不在执行时间段内，跳过检查")
            return

        # 预检 session（仅在配置了 base_url 时）
        if self.config.base_url and not self._check_session():
            logger.warning("session 已失效，跳过本轮检查")
            if self._dispatcher:
                self._dispatcher.notify_session_expired(self.config.task_name)
            return

        max_retries = 3
        logger.info(f"开始检查: {self.config.task_name} ({len(self.config.endpoints)} 个端点, 失败重试 {max_retries} 次)")

        failures = []

        for endpoint in self.config.endpoints:
            result = None
            for attempt in range(1, max_retries + 1):
                try:
                    result = check_endpoint(
                        endpoint,
                        base_url=self.config.base_url,
                        shared_headers=self.config.shared_headers,
                    )
                    if result.passed:
                        break
                    if attempt < max_retries:
                        logger.warning(f"  [重试 {attempt}/{max_retries}] {endpoint.name}: {result.details}")
                except Exception as e:
                    result = None
                    if attempt < max_retries:
                        logger.warning(f"  [重试 {attempt}/{max_retries}] {endpoint.name}: {e}")

            # 拼接完整 URL
            url = endpoint.url
            if self.config.base_url and url.startswith("/"):
                url = self.config.base_url.rstrip("/") + url

            if result is None:
                logger.error(f"  [FAIL] {endpoint.name}: 连续 {max_retries} 次异常")
                failures.append({
                    "endpoint_name": endpoint.name,
                    "url": url,
                    "status": "fail",
                    "status_code": None,
                    "latency_ms": 0,
                    "details": f"连续 {max_retries} 次请求异常",
                })
            else:
                self.storage.save(self.config.task_name, result)
                status = "PASS" if result.passed else "FAIL"
                logger.info(f"  [{status}] {endpoint.name}: {result.details}")
                if not result.passed:
                    failures.append({
                        "endpoint_name": result.endpoint_name,
                        "url": url,
                        "status": "fail",
                        "status_code": result.status_code,
                        "latency_ms": result.latency_ms,
                        "details": f"{result.details} (重试 {max_retries} 次仍失败)",
                    })

        # 失败时发送告警通知
        if failures and self._dispatcher:
            self._dispatcher.notify_failure(self.config.task_name, failures)

    def _send_daily_summary(self):
        """发送每日检查摘要（含延迟分位、端点可用率、连续失败）"""
        if not self._dispatcher:
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        metrics = self.storage.query_metrics(self.config.task_name, since=today_str)

        if not metrics["endpoint_stats"]:
            logger.info("今日无检查记录，跳过摘要发送")
            return

        lp = metrics["latency_percentiles"]
        ep_stats = metrics["endpoint_stats"]
        consecutive = metrics["consecutive_failures"]

        total = sum(s["total"] for s in ep_stats.values())
        passed = sum(s["passed"] for s in ep_stats.values())
        failed = total - passed

        failure_details = [
            {"endpoint_name": name, "status": "fail", "details": f"可用率 {s['availability']:.1f}%"}
            for name, s in ep_stats.items() if s["availability"] < 100
        ]

        # 连续失败的端点
        consecutive_failing = {name: count for name, count in consecutive.items() if count > 0}

        self._dispatcher.notify_daily_summary(
            task_name=self.config.task_name,
            total=total,
            passed=passed,
            failed=failed,
            errors=0,
            avg_latency=lp["avg"],
            failure_details=failure_details,
            latency_percentiles=lp,
            endpoint_stats=ep_stats,
            consecutive_failures=consecutive_failing,
        )

    def run_once(self):
        """执行一次检查并打印报告"""
        self._run_checks()
        print_report(self.storage, self.config.task_name)

    def start(self):
        """启动定时调度（阻塞运行）"""
        logger.info(f"启动监控: {self.config.task_name}, 间隔 {self.config.interval_minutes} 分钟")

        # 启动时立即执行一次
        self._run_checks()

        # 添加定时检查任务
        self._scheduler.add_job(
            self._run_checks,
            trigger=IntervalTrigger(minutes=self.config.interval_minutes),
            id="api_health_check",
            replace_existing=True,
        )

        # 每日 9:00 发送摘要
        if self._dispatcher:
            self._scheduler.add_job(
                self._send_daily_summary,
                trigger=CronTrigger(hour=9, minute=0),
                id="daily_summary",
                replace_existing=True,
            )
            logger.info("每日摘要: 每天 09:00 发送")

        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("监控已停止")

    def stop(self):
        """停止调度"""
        try:
            self._scheduler.shutdown(wait=False)
        except Exception:
            pass
        self.storage.close()
