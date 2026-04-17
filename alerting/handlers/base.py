"""通知渠道基类"""

from abc import ABC, abstractmethod


class NotificationHandler(ABC):
    """通知渠道抽象基类"""

    @abstractmethod
    def send(self, subject: str, content: str) -> bool:
        """
        发送通知

        Args:
            subject: 通知标题
            content: 通知正文（支持 HTML）

        Returns:
            是否发送成功
        """
        ...
