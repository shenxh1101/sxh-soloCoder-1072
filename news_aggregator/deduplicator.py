import jieba
import hashlib
import re
from typing import List, Set, Tuple
from collections import defaultdict
import logging

from .config import DeduplicationConfig
from .models import NewsItem

logger = logging.getLogger(__name__)


class SimHash:
    def __init__(self, hash_bits: int = 64):
        self.hash_bits = hash_bits
        jieba.initialize()

    def _tokenize(self, text: str) -> List[str]:
        text = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        words = jieba.lcut(text)
        stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这', '那', '有', '这个', '那个', '什么', '怎么', '为什么', '可以', '这个', '那个', '但是', '因为', '所以', '如果', '虽然', '然后', '而且', '或者', '以及', '及其', '等等'}
        words = [w for w in words if w not in stopwords and len(w) > 1]
        return words

    def _word_hash(self, word: str) -> int:
        h = hashlib.md5(word.encode('utf-8')).hexdigest()
        return int(h, 16) % (2 ** self.hash_bits)

    def compute(self, text: str) -> int:
        if not text:
            return 0

        tokens = self._tokenize(text)
        if not tokens:
            return 0

        vector = [0] * self.hash_bits

        for token in tokens:
            h = self._word_hash(token)
            for i in range(self.hash_bits):
                if h & (1 << i):
                    vector[i] += 1
                else:
                    vector[i] -= 1

        fingerprint = 0
        for i, v in enumerate(vector):
            if v > 0:
                fingerprint |= (1 << i)

        return fingerprint

    @staticmethod
    def hamming_distance(hash1: int, hash2: int) -> int:
        x = hash1 ^ hash2
        distance = 0
        while x:
            distance += 1
            x &= x - 1
        return distance

    def similarity(self, hash1: int, hash2: int) -> float:
        if hash1 == 0 or hash2 == 0:
            return 0.0
        distance = self.hamming_distance(hash1, hash2)
        return 1.0 - (distance / self.hash_bits)


class Deduplicator:
    def __init__(self, config: DeduplicationConfig):
        self.config = config
        self.simhash = SimHash(hash_bits=config.hash_bits)
        self.existing_hashes: Set[str] = set()
        self.existing_simhashes: List[Tuple[int, int]] = []
        self._url_pattern = re.compile(r'https?://[^\s]+')

    def load_existing(self, items: List[NewsItem]) -> None:
        self.existing_hashes.clear()
        self.existing_simhashes.clear()

        for item in items:
            if item.content_hash:
                self.existing_hashes.add(item.content_hash)
            if item.simhash and item.id:
                self.existing_simhashes.append((item.simhash, item.id))

        logger.info(f"已加载 {len(self.existing_hashes)} 个内容哈希，{len(self.existing_simhashes)} 个SimHash")

    def _normalize_text(self, text: str) -> str:
        text = self._url_pattern.sub('', text)
        text = re.sub(r'[^\w\u4e00-\u9fff]', '', text)
        text = text.lower()
        return text

    def _content_hash(self, item: NewsItem) -> str:
        content = self._normalize_text(item.title + ' ' + item.summary)
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def is_duplicate(self, item: NewsItem) -> Tuple[bool, str]:
        content_hash = self._content_hash(item)
        item.content_hash = content_hash

        if not self.config.enabled:
            return False, ""

        if content_hash in self.existing_hashes:
            return True, "内容哈希重复"

        combined_text = item.title + ' ' + item.summary
        simhash_value = self.simhash.compute(combined_text)
        item.simhash = simhash_value

        if simhash_value == 0:
            return False, ""

        for existing_hash, existing_id in self.existing_simhashes:
            similarity = self.simhash.similarity(simhash_value, existing_hash)
            if similarity >= self.config.similarity_threshold:
                return True, f"SimHash相似度 {similarity:.2f}，与ID {existing_id} 重复"

        return False, ""

    def add_item(self, item: NewsItem) -> None:
        if item.content_hash:
            self.existing_hashes.add(item.content_hash)
        if item.simhash and item.id:
            self.existing_simhashes.append((item.simhash, item.id))

    def dedupe_items(self, items: List[NewsItem]) -> List[NewsItem]:
        if not self.config.enabled:
            for item in items:
                content_hash = self._content_hash(item)
                item.content_hash = content_hash
            logger.info(f"去重已关闭，直接返回 {len(items)} 条新闻")
            return items

        deduped: List[NewsItem] = []
        duplicate_count = 0

        temp_simhashes: List[int] = []
        temp_content_hashes: Set[str] = set()

        for item in items:
            is_dup, reason = self.is_duplicate(item)
            if is_dup:
                duplicate_count += 1
                logger.debug(f"跳过重复新闻: {item.title[:30]}... - 原因: {reason}")
                continue

            if item.content_hash in temp_content_hashes:
                duplicate_count += 1
                logger.debug(f"跳过批内内容哈希重复新闻: {item.title[:30]}...")
                continue

            if item.simhash:
                for temp_hash in temp_simhashes:
                    similarity = self.simhash.similarity(item.simhash, temp_hash)
                    if similarity >= self.config.similarity_threshold:
                        duplicate_count += 1
                        logger.debug(f"跳过批内相似度重复新闻: {item.title[:30]}...")
                        is_dup = True
                        break

            if not is_dup:
                deduped.append(item)
                temp_content_hashes.add(item.content_hash)
                if item.simhash:
                    temp_simhashes.append(item.simhash)

        logger.info(f"去重完成: 输入 {len(items)} 条，去重后 {len(deduped)} 条，移除 {duplicate_count} 条重复")
        return deduped
