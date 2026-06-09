import os
import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional
import logging

from .config import StorageConfig
from .models import NewsItem

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self, config: StorageConfig):
        self.config = config
        db_dir = os.path.dirname(config.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._init_db()
        self._clean_old_data()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.config.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS news (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    summary TEXT,
                    publish_time TEXT,
                    source TEXT,
                    content_hash TEXT,
                    simhash TEXT,
                    keywords TEXT,
                    fetched_at TEXT NOT NULL
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fetch_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT NOT NULL,
                    last_fetch_time TEXT,
                    created_at TEXT NOT NULL
                )
            ''')

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_content_hash ON news(content_hash)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_publish_time ON news(publish_time)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_source ON news(source)')

            conn.commit()
            logger.info("数据库初始化完成")

    def _clean_old_data(self) -> None:
        if self.config.history_days <= 0:
            return

        cutoff_date = datetime.now() - timedelta(days=self.config.history_days)
        cutoff_str = cutoff_date.isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM news WHERE fetched_at < ?', (cutoff_str,))
            deleted = cursor.rowcount
            conn.commit()

            if deleted > 0:
                logger.info(f"清理了 {deleted} 条超过 {self.config.history_days} 天的旧数据")

    def save_news(self, items: List[NewsItem]) -> List[NewsItem]:
        saved_items = []

        with self._get_connection() as conn:
            cursor = conn.cursor()

            for item in items:
                cursor.execute(
                    'SELECT id FROM news WHERE content_hash = ?',
                    (item.content_hash,)
                )
                existing = cursor.fetchone()

                if existing:
                    logger.debug(f"新闻已存在，跳过: {item.title[:30]}...")
                    continue

                publish_time_str = item.publish_time.isoformat() if item.publish_time else None
                fetched_at_str = item.fetched_at.isoformat() if item.fetched_at else datetime.now().isoformat()

                cursor.execute('''
                    INSERT INTO news (title, url, summary, publish_time, source, content_hash, simhash, keywords, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    item.title,
                    item.url,
                    item.summary,
                    publish_time_str,
                    item.source,
                    item.content_hash,
                    str(item.simhash) if item.simhash else None,
                    ','.join(item.keywords) if item.keywords else None,
                    fetched_at_str
                ))

                item.id = cursor.lastrowid
                saved_items.append(item)

            conn.commit()

        logger.info(f"保存了 {len(saved_items)} 条新新闻到数据库")
        return saved_items

    def get_all_news(self, limit: int = None, source: str = None) -> List[NewsItem]:
        query = 'SELECT * FROM news'
        params = []

        if source:
            query += ' WHERE source = ?'
            params.append(source)

        query += ' ORDER BY publish_time DESC'

        if limit:
            query += ' LIMIT ?'
            params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

        items = []
        for row in rows:
            item = NewsItem(
                id=row['id'],
                title=row['title'],
                url=row['url'],
                summary=row['summary'] or '',
                source=row['source'] or '',
                content_hash=row['content_hash'] or '',
                simhash=int(row['simhash']) if row['simhash'] else None,
                keywords=row['keywords'].split(',') if row['keywords'] else [],
            )
            if row['publish_time']:
                item.publish_time = datetime.fromisoformat(row['publish_time'])
            if row['fetched_at']:
                item.fetched_at = datetime.fromisoformat(row['fetched_at'])
            items.append(item)

        return items

    def get_news_by_date_range(self, start_date: datetime, end_date: datetime) -> List[NewsItem]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM news
                WHERE publish_time >= ? AND publish_time <= ?
                ORDER BY publish_time DESC
            ''', (start_date.isoformat(), end_date.isoformat()))
            rows = cursor.fetchall()

        items = []
        for row in rows:
            item = NewsItem(
                id=row['id'],
                title=row['title'],
                url=row['url'],
                summary=row['summary'] or '',
                source=row['source'] or '',
                content_hash=row['content_hash'] or '',
                simhash=int(row['simhash']) if row['simhash'] else None,
                keywords=row['keywords'].split(',') if row['keywords'] else [],
            )
            if row['publish_time']:
                item.publish_time = datetime.fromisoformat(row['publish_time'])
            if row['fetched_at']:
                item.fetched_at = datetime.fromisoformat(row['fetched_at'])
            items.append(item)

        return items

    def get_last_fetch_time(self, source_name: str) -> Optional[datetime]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT last_fetch_time FROM fetch_metadata
                WHERE source_name = ?
                ORDER BY id DESC LIMIT 1
            ''', (source_name,))
            row = cursor.fetchone()

        if row and row['last_fetch_time']:
            return datetime.fromisoformat(row['last_fetch_time'])
        return None

    def set_last_fetch_time(self, source_name: str, fetch_time: datetime) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO fetch_metadata (source_name, last_fetch_time, created_at)
                VALUES (?, ?, ?)
            ''', (
                source_name,
                fetch_time.isoformat(),
                datetime.now().isoformat()
            ))
            conn.commit()

    def get_news_count(self, source: str = None) -> int:
        query = 'SELECT COUNT(*) FROM news'
        params = []

        if source:
            query += ' WHERE source = ?'
            params.append(source)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()[0]

    def get_sources(self) -> List[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT source FROM news WHERE source IS NOT NULL')
            return [row[0] for row in cursor.fetchall()]

    def delete_old_news(self, days: int) -> int:
        cutoff_date = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff_date.isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM news WHERE fetched_at < ?', (cutoff_str,))
            deleted = cursor.rowcount
            conn.commit()

        logger.info(f"删除了 {deleted} 条超过 {days} 天的新闻")
        return deleted
