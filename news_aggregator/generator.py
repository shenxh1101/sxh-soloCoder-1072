import os
from datetime import datetime
from typing import List
import logging

from .config import OutputConfig
from .models import NewsItem

logger = logging.getLogger(__name__)


class MarkdownGenerator:
    def __init__(self, config: OutputConfig):
        self.config = config
        os.makedirs(config.markdown_dir, exist_ok=True)

    def _sort_items(self, items: List[NewsItem]) -> List[NewsItem]:
        sort_key = self.config.sort_by
        reverse = self.config.sort_order.lower() == 'desc'

        def get_sort_value(item: NewsItem):
            if sort_key == 'publish_time':
                return item.publish_time or datetime.min
            elif sort_key == 'source':
                return item.source
            elif sort_key == 'title':
                return item.title
            else:
                return item.fetched_at or datetime.min

        return sorted(items, key=get_sort_value, reverse=reverse)

    def generate(self, items: List[NewsItem], title: str = None, filename: str = None) -> str:
        if not items:
            logger.warning("没有新闻可生成简报")
            return ""

        sorted_items = self._sort_items(items)
        if self.config.news_per_brief > 0:
            sorted_items = sorted_items[:self.config.news_per_brief]

        if not title:
            title = f"新闻简报 - {datetime.now().strftime('%Y年%m月%d日 %H:%M')}"

        lines = [f"# {title}", ""]
        lines.append(f"_生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_")
        lines.append(f"_共 {len(sorted_items)} 条新闻_")
        lines.append("")

        current_date = None
        for idx, item in enumerate(sorted_items, 1):
            item_date = item.publish_time.strftime('%Y-%m-%d') if item.publish_time else '未知日期'

            if item_date != current_date:
                current_date = item_date
                lines.append(f"## 📅 {current_date}")
                lines.append("")

            lines.append(f"### {idx}. {item.title}")
            lines.append("")

            if self.config.include_original_link and item.url:
                lines.append(f"🔗 [原文链接]({item.url})")
                lines.append("")

            if item.source:
                lines.append(f"📰 来源: **{item.source}**")
                lines.append("")

            if item.publish_time:
                lines.append(f"⏰ 发布时间: {item.publish_time.strftime('%Y-%m-%d %H:%M:%S')}")
                lines.append("")

            if item.keywords:
                lines.append(f"🏷️ 标签: {' / '.join(f'`{k}`' for k in item.keywords)}")
                lines.append("")

            if self.config.include_summary and item.summary:
                lines.append("**摘要:**")
                lines.append("")
                lines.append(f"> {item.summary}")
                lines.append("")

            lines.append("---")
            lines.append("")

        content = '\n'.join(lines)

        if not filename:
            filename = f"news_brief_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

        filepath = os.path.join(self.config.markdown_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"Markdown简报已生成: {filepath}")
        return filepath

    def generate_text_for_notification(self, items: List[NewsItem], max_items: int = 20) -> str:
        if not items:
            return "暂无新新闻"

        sorted_items = self._sort_items(items)[:max_items]

        lines = [f"📰 **新闻简报** ({datetime.now().strftime('%Y-%m-%d %H:%M')})", ""]

        for idx, item in enumerate(sorted_items, 1):
            title_line = f"**{idx}. {item.title}**"
            if self.config.include_original_link and item.url:
                title_line += f" [→]({item.url})"
            lines.append(title_line)

            if item.source:
                lines.append(f"   📰 {item.source}")

            if item.publish_time:
                lines.append(f"   ⏰ {item.publish_time.strftime('%Y-%m-%d %H:%M')}")

            if item.keywords:
                lines.append(f"   🏷️ {' '.join(k for k in item.keywords[:5])}")

            if self.config.include_summary and item.summary:
                summary = item.summary[:150] + '...' if len(item.summary) > 150 else item.summary
                lines.append(f"   {summary}")

            lines.append("")

        if len(items) > max_items:
            lines.append(f"_...还有 {len(items) - max_items} 条新闻_")

        return '\n'.join(lines)
