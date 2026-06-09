import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from dateutil import parser as date_parser
from typing import List, Optional
import time
import logging
from urllib.parse import urljoin

from .config import Source, FetchConfig
from .models import NewsItem

logger = logging.getLogger(__name__)


class BaseFetcher:
    def __init__(self, config: FetchConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': config.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })

    def _fetch_with_retry(self, url: str) -> Optional[requests.Response]:
        for attempt in range(self.config.retry_count):
            try:
                response = self.session.get(
                    url,
                    timeout=self.config.request_timeout,
                    allow_redirects=True
                )
                response.encoding = response.apparent_encoding or 'utf-8'
                if response.status_code == 200:
                    return response
                logger.warning(f"获取 {url} 失败，状态码: {response.status_code}，重试 {attempt + 1}/{self.config.retry_count}")
            except requests.RequestException as e:
                logger.warning(f"获取 {url} 异常: {e}，重试 {attempt + 1}/{self.config.retry_count}")
            time.sleep(1)
        logger.error(f"获取 {url} 失败，已达最大重试次数")
        return None


class RSSFetcher(BaseFetcher):
    def fetch(self, source: Source, last_fetch_time: Optional[datetime] = None) -> List[NewsItem]:
        logger.info(f"开始抓取RSS源: {source.name} - {source.url}")

        response = self._fetch_with_retry(source.url)
        if not response:
            return []

        feed = feedparser.parse(response.content)
        items: List[NewsItem] = []

        for entry in feed.entries:
            try:
                title = entry.get('title', '').strip()
                if not title:
                    continue

                link = entry.get('link', '')
                if not link:
                    continue

                summary = entry.get('description', '') or entry.get('summary', '')
                if summary:
                    soup = BeautifulSoup(summary, 'lxml')
                    summary = soup.get_text().strip()

                publish_time = self._parse_time(entry)

                if last_fetch_time and publish_time and publish_time <= last_fetch_time:
                    continue

                item = NewsItem(
                    title=title,
                    url=link,
                    summary=summary,
                    publish_time=publish_time,
                    source=source.name
                )
                items.append(item)
            except Exception as e:
                logger.error(f"解析RSS条目失败: {e}")
                continue

        logger.info(f"RSS源 {source.name} 抓取完成，共获取 {len(items)} 条新闻")
        return items

    def _parse_time(self, entry) -> Optional[datetime]:
        time_fields = ['published', 'updated', 'created', 'issued']
        for field in time_fields:
            time_str = entry.get(field)
            if time_str:
                try:
                    return date_parser.parse(time_str)
                except Exception:
                    continue

        if 'published_parsed' in entry and entry.published_parsed:
            try:
                return datetime(*entry.published_parsed[:6])
            except Exception:
                pass

        return datetime.now()


class WebFetcher(BaseFetcher):
    def fetch(self, source: Source, last_fetch_time: Optional[datetime] = None) -> List[NewsItem]:
        logger.info(f"开始抓取网页源: {source.name} - {source.url}")

        response = self._fetch_with_retry(source.url)
        if not response:
            return []

        soup = BeautifulSoup(response.text, 'lxml')
        items: List[NewsItem] = []

        selector = source.selector or {}
        title_selector = selector.get('title', 'h1, h2, .title')
        summary_selector = selector.get('summary', '.summary, .description, p')
        date_selector = selector.get('date', '.date, .time')
        link_selector = selector.get('link', 'a')

        article_containers = soup.select('article, .news-item, .item, li')

        for container in article_containers[:30]:
            try:
                title_el = container.select_one(title_selector)
                if not title_el:
                    continue

                title = title_el.get_text().strip()
                if not title:
                    continue

                link_el = container.select_one(link_selector)
                link = link_el.get('href', '') if link_el else ''
                if link and not link.startswith('http'):
                    link = urljoin(source.url, link)
                if not link:
                    continue

                summary_el = container.select_one(summary_selector)
                summary = summary_el.get_text().strip() if summary_el else ''

                date_el = container.select_one(date_selector)
                publish_time = None
                if date_el:
                    date_str = date_el.get_text().strip()
                    try:
                        publish_time = date_parser.parse(date_str, fuzzy=True)
                    except Exception:
                        publish_time = datetime.now()

                if last_fetch_time and publish_time and publish_time <= last_fetch_time:
                    continue

                item = NewsItem(
                    title=title,
                    url=link,
                    summary=summary,
                    publish_time=publish_time or datetime.now(),
                    source=source.name
                )
                items.append(item)
            except Exception as e:
                logger.error(f"解析网页条目失败: {e}")
                continue

        logger.info(f"网页源 {source.name} 抓取完成，共获取 {len(items)} 条新闻")
        return items


class FetcherFactory:
    @staticmethod
    def create(source: Source, config: FetchConfig) -> Optional[BaseFetcher]:
        if source.type == 'rss':
            return RSSFetcher(config)
        elif source.type == 'web':
            return WebFetcher(config)
        else:
            logger.warning(f"不支持的源类型: {source.type}")
            return None


def fetch_source(source: Source, config: FetchConfig, last_fetch_time: Optional[datetime] = None) -> List[NewsItem]:
    fetcher = FetcherFactory.create(source, config)
    if not fetcher:
        return []
    return fetcher.fetch(source, last_fetch_time)
