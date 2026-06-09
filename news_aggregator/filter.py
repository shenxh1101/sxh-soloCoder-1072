import re
import jieba
from typing import List, Tuple
import logging

from .config import KeywordsConfig, FilterConfig
from .models import NewsItem

logger = logging.getLogger(__name__)


class KeywordFilter:
    def __init__(self, keywords_config: KeywordsConfig, filter_config: FilterConfig):
        self.keywords_config = keywords_config
        self.filter_config = filter_config
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        self.include_patterns = []
        for kw in self.keywords_config.include:
            try:
                pattern = re.compile(re.escape(kw), re.IGNORECASE)
                self.include_patterns.append((kw, pattern))
            except re.error:
                logger.warning(f"无效的关键词正则: {kw}")

        self.exclude_patterns = []
        for kw in self.keywords_config.exclude:
            try:
                pattern = re.compile(re.escape(kw), re.IGNORECASE)
                self.exclude_patterns.append((kw, pattern))
            except re.error:
                logger.warning(f"无效的排除关键词正则: {kw}")

    def _match_keywords(self, text: str, patterns: List[Tuple[str, re.Pattern]]) -> List[str]:
        matched = []
        for kw, pattern in patterns:
            if pattern.search(text):
                matched.append(kw)
        return matched

    def _extract_keywords(self, text: str) -> List[str]:
        words = jieba.lcut(text)
        stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这', '那'}
        words = [w for w in words if w not in stopwords and len(w) > 1]
        return words

    def filter_item(self, item: NewsItem) -> Tuple[bool, List[str]]:
        if len(item.title) < self.filter_config.min_title_length:
            logger.debug(f"标题过短，跳过: {item.title[:20]}...")
            return False, []

        combined_text = item.title + ' ' + item.summary

        excluded = self._match_keywords(combined_text, self.exclude_patterns)
        if excluded:
            logger.debug(f"包含排除关键词 {excluded}，跳过: {item.title[:30]}...")
            return False, []

        if self.keywords_config.include:
            included = self._match_keywords(combined_text, self.include_patterns)
            if not included:
                logger.debug(f"不包含任何关注关键词，跳过: {item.title[:30]}...")
                return False, []
            item.keywords = included
        else:
            item.keywords = self._extract_keywords(combined_text)[:10]

        if self.filter_config.max_summary_length and len(item.summary) > self.filter_config.max_summary_length:
            item.summary = item.summary[:self.filter_config.max_summary_length] + '...'

        return True, item.keywords

    def filter_items(self, items: List[NewsItem]) -> List[NewsItem]:
        filtered = []
        skipped = 0

        for item in items:
            passed, keywords = self.filter_item(item)
            if passed:
                filtered.append(item)
            else:
                skipped += 1

        logger.info(f"关键词过滤完成: 输入 {len(items)} 条，通过 {len(filtered)} 条，跳过 {skipped} 条")
        return filtered
