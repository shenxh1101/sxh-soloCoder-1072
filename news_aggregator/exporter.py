import csv
import os
from datetime import datetime, timedelta
from typing import List
import logging

from .models import NewsItem
from .storage import Storage

logger = logging.getLogger(__name__)


class CSVExporter:
    def __init__(self, storage: Storage):
        self.storage = storage

    def export_to_csv(self, filepath: str,
                      items: List[NewsItem] = None,
                      days: int = None,
                      source: str = None) -> str:
        if items is None:
            if days:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=days)
                items = self.storage.get_news_by_date_range(start_date, end_date)
            else:
                items = self.storage.get_all_news(source=source)

        if source and days is None:
            items = [item for item in items if item.source == source]

        if not items:
            logger.warning("没有数据可导出")
            return ""

        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)

        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)

            writer.writerow([
                'ID', '标题', 'URL', '摘要', '发布时间',
                '抓取时间', '来源', '关键词', '内容哈希', 'SimHash'
            ])

            for item in items:
                writer.writerow([
                    item.id,
                    item.title,
                    item.url,
                    item.summary,
                    item.publish_time.strftime('%Y-%m-%d %H:%M:%S') if item.publish_time else '',
                    item.fetched_at.strftime('%Y-%m-%d %H:%M:%S') if item.fetched_at else '',
                    item.source,
                    ','.join(item.keywords) if item.keywords else '',
                    item.content_hash,
                    str(item.simhash) if item.simhash else ''
                ])

        logger.info(f"已导出 {len(items)} 条新闻到 {filepath}")
        return filepath

    def export_recent(self, days: int = 7, output_dir: str = './output') -> str:
        filename = f"news_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}_recent_{days}days.csv"
        filepath = os.path.join(output_dir, filename)
        return self.export_to_csv(filepath, days=days)

    def export_all(self, output_dir: str = './output') -> str:
        filename = f"news_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}_all.csv"
        filepath = os.path.join(output_dir, filename)
        return self.export_to_csv(filepath)

    def export_by_source(self, source: str, output_dir: str = './output') -> str:
        safe_source = ''.join(c for c in source if c.isalnum() or c in ('-', '_'))
        filename = f"news_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_source}.csv"
        filepath = os.path.join(output_dir, filename)
        return self.export_to_csv(filepath, source=source)
