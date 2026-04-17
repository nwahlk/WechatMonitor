"""飞书机器人 Webhook 通知渠道"""

import logging

import httpx

from .base import NotificationHandler

logger = logging.getLogger(__name__)


class FeishuHandler(NotificationHandler):
    """通过飞书群机器人 Webhook 发送通知"""

    def __init__(self, webhook_url: str, secret: str | None = None):
        """
        Args:
            webhook_url: 飞书群机器人的 Webhook 地址
            secret: 签名校验密钥（可选，在机器人安全设置中配置）
        """
        self.webhook_url = webhook_url
        self.secret = secret

    def send(self, subject: str, content: str) -> bool:
        try:
            payload: dict = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": subject},
                        "template": "red" if "告警" in subject else "blue",
                    },
                    "elements": [
                        {"tag": "markdown", "content": content},
                    ],
                },
            }

            headers = {"Content-Type": "application/json"}
            resp = httpx.post(self.webhook_url, json=payload, headers=headers, timeout=10)
            data = resp.json()

            if data.get("code") == 0 or data.get("StatusCode") == 0:
                logger.info("飞书通知发送成功")
                return True
            else:
                logger.error(f"飞书发送失败: {data}")
                return False
        except Exception as e:
            logger.error(f"飞书通知异常: {e}")
            return False
