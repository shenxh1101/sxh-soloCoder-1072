from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

from .config import Config
from .models import NewsItem, SourceHealth
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

    def fetch_all_sources(self, use_incremental: bool = True) -> Dict:
        logger.info("开始抓取所有新闻源...")
        enabled_sources = [s for s in self.config.sources if s.enabled]
        logger.info(f"启用的源: {[s.name for s in enabled_sources]}")

        all_items: List[NewsItem] = []
        fetch_start_time = datetime.now()
        source_results: Dict[str, Dict] = {}

        with ThreadPoolExecutor(max_workers=self.config.fetch.max_threads) as executor:
            future_to_source = {}

            for source in enabled_sources:
                cursor_time = None
                if use_incremental:
                    cursor_time = self.storage.get_last_cursor_time(source.name)
                    if cursor_time:
                        logger.info(f"{source.name} 上次游标时间: {cursor_time}")

                future = executor.submit(
                    fetch_source,
                    source,
                    self.config.fetch,
                    cursor_time
                )
                future_to_source[future] = source

            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    items = future.result()
                    all_items.extend(items)

                    latest_publish_time = None
                    if items:
                        valid_times = [item.publish_time for item in items if item.publish_time]
                        if valid_times:
                            latest_publish_time = max(valid_times)
                        else:
                            latest_publish_time = fetch_start_time

                    cursor_time = latest_publish_time or fetch_start_time

                    source_results[source.name] = {
                        'success': True,
                        'items': items,
                        'fetched_count': len(items),
                        'cursor_time': cursor_time,
                        'error': None
                    }

                    logger.info(f"{source.name} 抓取完成，获取 {len(items)} 条，最新时间: {latest_publish_time}")

                    if use_incremental:
                        self.storage.set_last_fetch_time(source.name, fetch_start_time)
                        if latest_publish_time:
                            self.storage.set_last_cursor_time(source.name, latest_publish_time)
                        logger.info(f"{source.name} 增量时间已更新为: {fetch_start_time}, 游标: {cursor_time}")

                    self.storage.update_source_health_success(
                        source.name,
                        fetched_count=len(items),
                        cursor_time=cursor_time
                    )

                except Exception as e:
                    error_msg = str(e)
                    source_results[source.name] = {
                        'success': False,
                        'items': [],
                        'fetched_count': 0,
                        'cursor_time': None,
                        'error': error_msg
                    }
                    logger.error(f"{source.name} 抓取失败，不推进增量时间: {error_msg}")
                    self.storage.update_source_health_failure(source.name, error_msg)

        logger.info(f"所有源抓取完成，共获取 {len(all_items)} 条新闻")
        return {
            'items': all_items,
            'fetch_start_time': fetch_start_time,
            'source_results': source_results
        }

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
            'stats': {},
            'source_results': {}
        }

        fetch_result = self.fetch_all_sources(use_incremental=use_incremental)
        items = fetch_result['items']
        result['source_results'] = fetch_result['source_results']

        process_result = self.process_items(items)

        saved_by_source: Dict[str, int] = {}
        for item in process_result['items']:
            saved_by_source[item.source] = saved_by_source.get(item.source, 0) + 1

        for source_name, saved_count in saved_by_source.items():
            self.storage.update_source_health_success(
                source_name,
                saved_count=saved_count
            )

        result['fetch_end'] = datetime.now()
        result['items'] = process_result['items']
        result['stats'] = process_result

        if generate_brief and process_result['items']:
            result['brief_path'] = self.generator.generate(process_result['items'])

        if send_notifications and process_result['items']:
            result['notifications'] = self.notifier.send_notifications(process_result['items'])

        return result

    def generate_brief_from_storage(self, days: int = None,
                                    source: str = None,
                                    limit: int = None,
                                    keyword: str = None,
                                    start_date: datetime = None,
                                    end_date: datetime = None) -> str:
        if start_date is None and days is not None:
            end_date = end_date or datetime.now()
            start_date = end_date - timedelta(days=days)

        items = self.storage.get_news_with_filters(
            limit=limit,
            source=source,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date
        )

        title_parts = ["新闻简报"]
        if source:
            title_parts.append(f"来源: {source}")
        if keyword:
            title_parts.append(f"关键词: {keyword}")
        if days:
            title_parts.append(f"最近{days}天")
        elif start_date and end_date:
            title_parts.append(f"{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")

        title = " - ".join(title_parts)
        filename = f"brief_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

        return self.generator.generate(items, title=title, filename=filename)

    def get_recent_news(self, limit: int = 20, source: str = None,
                       keyword: str = None,
                       start_date: datetime = None,
                       end_date: datetime = None) -> List[NewsItem]:
        return self.storage.get_news_with_filters(
            limit=limit,
            source=source,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date
        )

    def get_source_health(self) -> List[SourceHealth]:
        return self.storage.get_all_source_health()

    def get_stats(self) -> Dict:
        sources = self.storage.get_sources()
        stats = {
            'total_news': self.storage.get_news_count(),
            'sources': {},
            'enabled_sources': [s.name for s in self.config.sources if s.enabled],
            'configured_sources': [s.name for s in self.config.sources],
            'source_health': self.get_source_health()
        }

        for source in sources:
            stats['sources'][source] = self.storage.get_news_count(source=source)

        return stats
