"""QQ邮箱 SMTP 通知渠道"""

import logging
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .base import NotificationHandler

logger = logging.getLogger(__name__)


def _markdown_to_html(md: str) -> str:
    """简易 markdown 转 HTML（覆盖本项目用到的格式）"""
    lines = md.split("\n")
    html_lines = []
    for line in lines:
        # 标题 **text**
        line = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', line)
        # 列表项 - text
        if re.match(r'^- ', line):
            line = f"<li>{line[2:]}</li>"
        # 空行
        if not line.strip():
            line = "<br>"
        html_lines.append(line)
    return "\n".join(html_lines)


class EmailHandler(NotificationHandler):
    """通过 SMTP 发送邮件通知"""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        sender: str,
        password: str,
        receivers: list[str],
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.sender = sender
        self.password = password
        self.receivers = receivers

    def send(self, subject: str, content: str) -> bool:
        try:
            # 已经是 HTML 内容则直接使用
            html_content = content if content.strip().startswith("<") else _markdown_to_html(content)

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.sender
            msg["To"] = ", ".join(self.receivers)

            msg.attach(MIMEText(html_content, "html", "utf-8"))

            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.login(self.sender, self.password)
                server.sendmail(self.sender, self.receivers, msg.as_string())

            logger.info(f"邮件通知发送成功 -> {self.receivers}")
            return True
        except Exception as e:
            logger.error(f"邮件通知异常: {e}")
            return False
