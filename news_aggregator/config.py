import os
import yaml
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class Source:
    name: str
    type: str
    url: str
    enabled: bool = True
    selector: Optional[Dict[str, str]] = None


@dataclass
class KeywordsConfig:
    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)


@dataclass
class DeduplicationConfig:
    enabled: bool = True
    similarity_threshold: float = 0.85
    hash_bits: int = 64


@dataclass
class FetchConfig:
    interval_minutes: int = 60
    max_threads: int = 5
    request_timeout: int = 30
    user_agent: str = "Mozilla/5.0"
    retry_count: int = 3


@dataclass
class FilterConfig:
    max_summary_length: int = 500
    min_title_length: int = 5


@dataclass
class EmailConfig:
    enabled: bool = False
    smtp_server: str = ""
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    from_addr: str = ""
    to_addrs: List[str] = field(default_factory=list)
    subject: str = "新闻简报"
    use_tls: bool = True


@dataclass
class WebhookConfig:
    enabled: bool = False
    url: str = ""
    method: str = "POST"
    content_type: str = "application/json"
    template: str = ""


@dataclass
class NotificationConfig:
    email: EmailConfig = field(default_factory=EmailConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)


@dataclass
class OutputConfig:
    markdown_dir: str = "./output"
    include_original_link: bool = True
    include_summary: bool = True
    news_per_brief: int = 50
    sort_by: str = "publish_time"
    sort_order: str = "desc"


@dataclass
class StorageConfig:
    db_path: str = "./data/news.db"
    history_days: int = 30


@dataclass
class Config:
    sources: List[Source] = field(default_factory=list)
    keywords: KeywordsConfig = field(default_factory=KeywordsConfig)
    deduplication: DeduplicationConfig = field(default_factory=DeduplicationConfig)
    fetch: FetchConfig = field(default_factory=FetchConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)


def load_config(config_path: str) -> Config:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    sources = [Source(**s) for s in data.get('sources', [])]
    keywords = KeywordsConfig(**data.get('keywords', {}))
    deduplication = DeduplicationConfig(**data.get('deduplication', {}))
    fetch = FetchConfig(**data.get('fetch', {}))
    filter_config = FilterConfig(**data.get('filter', {}))

    notif_data = data.get('notification', {})
    email = EmailConfig(**notif_data.get('email', {}))
    webhook = WebhookConfig(**notif_data.get('webhook', {}))
    notification = NotificationConfig(email=email, webhook=webhook)

    output = OutputConfig(**data.get('output', {}))
    storage = StorageConfig(**data.get('storage', {}))

    return Config(
        sources=sources,
        keywords=keywords,
        deduplication=deduplication,
        fetch=fetch,
        filter=filter_config,
        notification=notification,
        output=output,
        storage=storage
    )


def create_default_config(config_path: str) -> None:
    default_config = {
        'sources': [],
        'keywords': {'include': [], 'exclude': []},
        'deduplication': {'enabled': True, 'similarity_threshold': 0.85, 'hash_bits': 64},
        'fetch': {'interval_minutes': 60, 'max_threads': 5, 'request_timeout': 30},
        'filter': {'max_summary_length': 500, 'min_title_length': 5},
        'notification': {
            'email': {'enabled': False},
            'webhook': {'enabled': False}
        },
        'output': {'markdown_dir': './output'},
        'storage': {'db_path': './data/news.db', 'history_days': 30}
    }

    os.makedirs(os.path.dirname(config_path) if os.path.dirname(config_path) else '.', exist_ok=True)

    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(default_config, f, allow_unicode=True, default_flow_style=False)
