from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict, Optional
import logging

from .config import Config
from .models import NewsItem
from .fetcher import fetch_source
from .deduplicator import Deduplicator
from .filter import KeywordFilter
from .storage import Storage
from .generator import MarkdownGenerator
from .notifier import Notifier

logger = logging.getLogger(__name__)


class NewsAggregator:
    def __init__(self, config: Config):
        self.config = config
        self.storage = Storage(config.storage)
        self.deduplicator = Deduplicator(config.deduplication)
        self.filter = KeywordFilter(config.keywords, config.filter)
        self.generator = MarkdownGenerator(config.output)
        self.notifier = Notifier(config.notification, config.output)

        existing_news = self.storage.get_all_news()
        self.deduplicator.load_existing(existing_news)

    def fetch_all_sources(self, use_incremental: bool = True) -> List[NewsItem]:
        logger.info("开始抓取所有新闻源...")
        enabled_sources = [s for s in self.config.sources if s.enabled]
        logger.info(f"启用的源: {[s.name for s in enabled_sources]}")

        all_items: List[NewsItem] = []

        with ThreadPoolExecutor(max_workers=self.config.fetch.max_threads) as executor:
            future_to_source = {}

            for source in enabled_sources:
                last_fetch_time = None
                if use_incremental:
                    last_fetch_time = self.storage.get_last_fetch_time(source.name)
                    if last_fetch_time:
                        logger.info(f"{source.name} 上次抓取时间: {last_fetch_time}")

                future = executor.submit(
                    fetch_source,
                    source,
                    self.config.fetch,
                    last_fetch_time
                )
                future_to_source[future] = source

            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    items = future.result()
                    all_items.extend(items)
                    logger.info(f"{source.name} 抓取完成，获取 {len(items)} 条")
                except Exception as e:
                    logger.error(f"{source.name} 抓取失败: {e}")

        logger.info(f"所有源抓取完成，共获取 {len(all_items)} 条新闻")
        return all_items

    def process_items(self, items: List[NewsItem]) -> Dict:
        result = {
            'total_input': len(items),
            'after_dedupe': 0,
            'after_filter': 0,
            'saved': 0,
            'items': []
        }

        if not items:
            return result

        deduped_items = self.deduplicator.dedupe_items(items)
        result['after_dedupe'] = len(deduped_items)

        filtered_items = self.filter.filter_items(deduped_items)
        result['after_filter'] = len(filtered_items)

        saved_items = self.storage.save_news(filtered_items)
        result['saved'] = len(saved_items)
        result['items'] = saved_items

        for item in saved_items:
            self.deduplicator.add_item(item)
            self.storage.set_last_fetch_time(item.source, item.fetched_at or datetime.now())

        return result

    def fetch_and_process(self, use_incremental: bool = True,
                         generate_brief: bool = True,
                         send_notifications: bool = True) -> Dict:
        result = {
            'fetch_start': datetime.now(),
            'fetch_end': None,
            'items': [],
            'brief_path': '',
            'notifications': {},
            'stats': {}
        }

        items = self.fetch_all_sources(use_incremental=use_incremental)
        process_result = self.process_items(items)

        result['fetch_end'] = datetime.now()
        result['items'] = process_result['items']
        result['stats'] = process_result

        if generate_brief and process_result['items']:
            result['brief_path'] = self.generator.generate(process_result['items'])

        if send_notifications and process_result['items']:
            result['notifications'] = self.notifier.send_notifications(process_result['items'])

        return result

    def generate_brief_from_storage(self, days: int = 7,
                                    source: str = None,
                                    limit: int = None) -> str:
        from datetime import timedelta

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        items = self.storage.get_news_by_date_range(start_date, end_date)

        if source:
            items = [item for item in items if item.source == source]

        if limit:
            items = items[:limit]

        title = f"历史新闻简报 - 最近{days}天"
        filename = f"history_brief_{end_date.strftime('%Y%m%d_%H%M%S')}.md"

        return self.generator.generate(items, title=title, filename=filename)

    def get_recent_news(self, limit: int = 20, source: str = None) -> List[NewsItem]:
        return self.storage.get_all_news(limit=limit, source=source)

    def get_stats(self) -> Dict:
        sources = self.storage.get_sources()
        stats = {
            'total_news': self.storage.get_news_count(),
            'sources': {},
            'enabled_sources': [s.name for s in self.config.sources if s.enabled],
            'configured_sources': [s.name for s in self.config.sources]
        }

        for source in sources:
            stats['sources'][source] = self.storage.get_news_count(source=source)

        return stats
