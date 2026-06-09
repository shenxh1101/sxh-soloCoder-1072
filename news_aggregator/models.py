from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


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
