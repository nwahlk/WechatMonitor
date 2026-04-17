"""API 监控配置加载"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Endpoint:
    """单个 API 端点配置"""
    name: str
    url: str
    method: str = "GET"
    body: str | None = None
    headers: dict = field(default_factory=dict)
    expected_status: int = 200
    expected_fields: list[str] = field(default_factory=list)
    expected_data_fields: list[str] = field(default_factory=list)
    timeout: float = 10


@dataclass
class FeishuConfig:
    """飞书 Webhook 配置"""
    webhook_url: str = ""
    secret: str | None = None


@dataclass
class EmailConfig:
    """邮件 SMTP 配置"""
    smtp_host: str = "smtp.qq.com"
    smtp_port: int = 465
    sender: str = ""
    password: str = ""
    receivers: list[str] = field(default_factory=list)


@dataclass
class NotificationConfig:
    """通知配置"""
    enabled: bool = True
    feishu: FeishuConfig = field(default_factory=FeishuConfig)
    email: EmailConfig = field(default_factory=EmailConfig)

    @property
    def has_channels(self) -> bool:
        """是否配置了至少一个通知渠道"""
        return bool(self.feishu.webhook_url) or bool(self.email.sender)


@dataclass
class ScheduleConfig:
    """执行时间段配置"""
    start_hour: int = 0
    end_hour: int = 24


@dataclass
class MonitorConfig:
    """监控任务配置"""
    task_name: str
    interval_minutes: int = 5
    base_url: str = ""
    shared_headers: dict = field(default_factory=dict)
    endpoints: list[Endpoint] = field(default_factory=list)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(path: str | Path) -> MonitorConfig:
    """从 YAML 文件加载监控配置（自动合并同目录下的 settings.yaml）"""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    # 加载端点配置
    raw = _load_yaml(config_path)

    # 合并 settings.yaml（base_url、task、schedule、notification）
    settings_file = config_path.parent / "settings.yaml"
    if settings_file.exists():
        settings = _load_yaml(settings_file)
    else:
        settings = {}

    # settings 为主，raw 为兜底
    task = settings.get("task", raw.get("task", {}))
    notif_raw = settings.get("notification", raw.get("notification", {}))
    schedule_raw = settings.get("schedule", raw.get("schedule", {}))
    base_url = settings.get("base_url", raw.get("base_url", ""))
    shared_headers = settings.get("shared_headers", raw.get("shared_headers", {}))

    # 解析端点列表
    endpoints = []
    for ep_raw in raw.get("endpoints", []):
        endpoints.append(Endpoint(
            name=ep_raw["name"],
            url=ep_raw["url"],
            method=ep_raw.get("method", "GET"),
            body=ep_raw.get("body"),
            headers=ep_raw.get("headers", {}),
            expected_status=ep_raw.get("expected_status", 200),
            expected_fields=ep_raw.get("expected_fields", []),
            expected_data_fields=ep_raw.get("expected_data_fields", []),
            timeout=ep_raw.get("timeout", 10),
        ))

    # 解析通知配置
    feishu_raw = notif_raw.get("feishu", {})
    email_raw = notif_raw.get("email", {})

    feishu = FeishuConfig(
        webhook_url=feishu_raw.get("webhook_url", ""),
        secret=feishu_raw.get("secret"),
    )
    email = EmailConfig(
        smtp_host=email_raw.get("smtp_host", "smtp.qq.com"),
        smtp_port=email_raw.get("smtp_port", 465),
        sender=email_raw.get("sender", ""),
        password=email_raw.get("password", ""),
        receivers=email_raw.get("receivers", []),
    )

    # 解析执行时间段
    schedule = ScheduleConfig(
        start_hour=schedule_raw.get("start_hour", 0),
        end_hour=schedule_raw.get("end_hour", 24),
    )

    return MonitorConfig(
        task_name=task.get("name", "unnamed"),
        interval_minutes=task.get("interval_minutes", 5),
        base_url=base_url,
        shared_headers=shared_headers,
        endpoints=endpoints,
        notification=NotificationConfig(
            enabled=notif_raw.get("enabled", True),
            feishu=feishu,
            email=email,
        ),
        schedule=schedule,
    )
