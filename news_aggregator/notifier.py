import smtplib
import json
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from typing import List
import logging

from .config import NotificationConfig
from .models import NewsItem
from .generator import MarkdownGenerator

logger = logging.getLogger(__name__)


class EmailNotifier:
    def __init__(self, config):
        self.config = config

    def send(self, subject: str, content: str, is_html: bool = False) -> bool:
        if not self.config.enabled:
            logger.info("邮件通知未启用")
            return False

        try:
            msg = MIMEMultipart()
            msg['From'] = Header(self.config.from_addr, 'utf-8')
            msg['To'] = Header(','.join(self.config.to_addrs), 'utf-8')
            msg['Subject'] = Header(subject, 'utf-8')

            content_type = 'html' if is_html else 'plain'
            msg.attach(MIMEText(content, content_type, 'utf-8'))

            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port, timeout=30) as server:
                if self.config.use_tls:
                    server.starttls()
                server.login(self.config.username, self.config.password)
                server.sendmail(self.config.from_addr, self.config.to_addrs, msg.as_string())

            logger.info(f"邮件发送成功，收件人: {self.config.to_addrs}")
            return True
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return False


class WebhookNotifier:
    def __init__(self, config):
        self.config = config

    def send(self, content: str) -> bool:
        if not self.config.enabled:
            logger.info("Webhook通知未启用")
            return False

        try:
            payload = self.config.template.format(content=content)
            headers = {'Content-Type': self.config.content_type}

            response = requests.request(
                method=self.config.method,
                url=self.config.url,
                data=payload,
                headers=headers,
                timeout=30
            )

            if response.status_code >= 200 and response.status_code < 300:
                logger.info("Webhook发送成功")
                return True
            else:
                logger.error(f"Webhook发送失败，状态码: {response.status_code}, 响应: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Webhook发送异常: {e}")
            return False


class Notifier:
    def __init__(self, config: NotificationConfig, output_config):
        self.config = config
        self.email_notifier = EmailNotifier(config.email)
        self.webhook_notifier = WebhookNotifier(config.webhook)
        self.markdown_generator = MarkdownGenerator(output_config)

    def send_notifications(self, items: List[NewsItem], subject: str = None) -> dict:
        results = {'email': False, 'webhook': False}

        if not items:
            logger.info("没有新新闻，跳过通知")
            return results

        if not subject:
            from datetime import datetime
            subject = f"新闻简报 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        if self.config.email.enabled:
            markdown_content = self.markdown_generator.generate_text_for_notification(items)
            html_content = self._markdown_to_html(markdown_content)
            results['email'] = self.email_notifier.send(subject, html_content, is_html=True)

        if self.config.webhook.enabled:
            notification_text = self.markdown_generator.generate_text_for_notification(items)
            results['webhook'] = self.webhook_notifier.send(notification_text)

        return results

    def _markdown_to_html(self, markdown_text: str) -> str:
        import re

        html = markdown_text
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'_(.+?)_', r'<em>\1</em>', html)
        html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
        html = re.sub(r'`(.+?)`', r'<code>\1</code>', html)
        html = html.replace('\n', '<br>')

        return f"""
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        {html}
        </body>
        </html>
        """
