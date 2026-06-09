from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class NewsItem:
    title: str
    url: str
    summary: str = ""
    publish_time: Optional[datetime] = None
    source: str = ""
    content_hash: str = ""
    simhash: Optional[int] = None
    keywords: List[str] = field(default_factory=list)
    fetched_at: Optional[datetime] = field(default_factory=datetime.now)
    id: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'summary': self.summary,
            'publish_time': self.publish_time.isoformat() if self.publish_time else None,
            'source': self.source,
            'content_hash': self.content_hash,
            'simhash': str(self.simhash) if self.simhash else None,
            'keywords': ','.join(self.keywords),
            'fetched_at': self.fetched_at.isoformat() if self.fetched_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'NewsItem':
        item = cls(
            title=data['title'],
            url=data['url'],
            summary=data.get('summary', ''),
            source=data.get('source', ''),
            content_hash=data.get('content_hash', ''),
            simhash=int(data['simhash']) if data.get('simhash') else None,
            keywords=data.get('keywords', '').split(',') if data.get('keywords') else [],
            id=data.get('id')
        )
        if data.get('publish_time'):
            item.publish_time = datetime.fromisoformat(data['publish_time'])
        if data.get('fetched_at'):
            item.fetched_at = datetime.fromisoformat(data['fetched_at'])
        return item


@dataclass
class SourceHealth:
    source_name: str
    last_success_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    last_failure_reason: Optional[str] = None
    consecutive_failures: int = 0
    last_cursor_time: Optional[datetime] = None
    total_fetched: int = 0
    total_saved: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'source_name': self.source_name,
            'last_success_time': self.last_success_time.isoformat() if self.last_success_time else None,
            'last_failure_time': self.last_failure_time.isoformat() if self.last_failure_time else None,
            'last_failure_reason': self.last_failure_reason,
            'consecutive_failures': self.consecutive_failures,
            'last_cursor_time': self.last_cursor_time.isoformat() if self.last_cursor_time else None,
            'total_fetched': self.total_fetched,
            'total_saved': self.total_saved,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SourceHealth':
        health = cls(
            source_name=data['source_name'],
            consecutive_failures=data.get('consecutive_failures', 0),
            total_fetched=data.get('total_fetched', 0),
            total_saved=data.get('total_saved', 0),
        )
        if data.get('last_success_time'):
            health.last_success_time = datetime.fromisoformat(data['last_success_time'])
        if data.get('last_failure_time'):
            health.last_failure_time = datetime.fromisoformat(data['last_failure_time'])
        health.last_failure_reason = data.get('last_failure_reason')
        if data.get('last_cursor_time'):
            health.last_cursor_time = datetime.fromisoformat(data['last_cursor_time'])
        return health
