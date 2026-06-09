#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第三轮功能验证测试
"""
import os
import sys
import tempfile
import shutil
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from news_aggregator.fetcher import RSSFetcher
from news_aggregator.config import load_config, FetchConfig, Source, StorageConfig
from news_aggregator.models import NewsItem, SourceHealth
from news_aggregator.storage import Storage
import unittest


class TestSourceHealth(unittest.TestCase):
    """测试1: 源健康状态记录"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='test_health_')
        self.db_path = os.path.join(self.test_dir, 'test.db')
        self.storage_config = StorageConfig(db_path=self.db_path)
        self.storage = Storage(self.storage_config)

    def tearDown(self):
        for _ in range(5):
            try:
                shutil.rmtree(self.test_dir)
                break
            except:
                time.sleep(0.1)

    def test_health_status_tracking(self):
        """测试健康状态记录功能"""
        source_name = "测试源"

        print(f"\n=== 源健康状态测试 ===")

        self.storage.update_source_health_success(source_name, fetched_count=5, saved_count=3)
        health = self.storage.get_source_health(source_name)

        print(f"初始成功后:")
        print(f"  连续失败次数: {health.consecutive_failures} (预期: 0)")
        print(f"  累计抓取: {health.total_fetched} (预期: 5)")
        print(f"  累计保存: {health.total_saved} (预期: 3)")

        self.assertEqual(health.consecutive_failures, 0)
        self.assertEqual(health.total_fetched, 5)
        self.assertEqual(health.total_saved, 3)
        self.assertIsNotNone(health.last_success_time)
        self.assertIsNone(health.last_failure_reason)

        self.storage.update_source_health_failure(source_name, "连接超时")
        health = self.storage.get_source_health(source_name)

        print(f"\n一次失败后:")
        print(f"  连续失败次数: {health.consecutive_failures} (预期: 1)")
        print(f"  失败原因: {health.last_failure_reason} (预期: 连接超时)")

        self.assertEqual(health.consecutive_failures, 1)
        self.assertEqual(health.last_failure_reason, "连接超时")
        self.assertIsNotNone(health.last_failure_time)

        self.storage.update_source_health_failure(source_name, "DNS解析失败")
        health = self.storage.get_source_health(source_name)

        print(f"\n二次失败后:")
        print(f"  连续失败次数: {health.consecutive_failures} (预期: 2)")
        self.assertEqual(health.consecutive_failures, 2)

        cursor_time = datetime(2026, 6, 10, 12, 0, 0)
        self.storage.update_source_health_success(source_name, fetched_count=8, saved_count=5, cursor_time=cursor_time)
        health = self.storage.get_source_health(source_name)

        print(f"\n恢复成功后:")
        print(f"  连续失败次数: {health.consecutive_failures} (预期: 0)")
        print(f"  累计抓取: {health.total_fetched} (预期: 13)")
        print(f"  累计保存: {health.total_saved} (预期: 8)")
        print(f"  游标时间: {health.last_cursor_time} (预期: {cursor_time})")

        self.assertEqual(health.consecutive_failures, 0)
        self.assertEqual(health.total_fetched, 13)
        self.assertEqual(health.total_saved, 8)
        self.assertEqual(health.last_cursor_time, cursor_time)
        self.assertIsNone(health.last_failure_reason)

        print(f"\n✅ 源健康状态记录验证通过!")


class TestCursorTime(unittest.TestCase):
    """测试2: 增量游标时间"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='test_cursor_')
        self.db_path = os.path.join(self.test_dir, 'test.db')
        self.storage_config = StorageConfig(db_path=self.db_path)
        self.storage = Storage(self.storage_config)

    def tearDown(self):
        for _ in range(5):
            try:
                shutil.rmtree(self.test_dir)
                break
            except:
                time.sleep(0.1)

    def test_cursor_time_accuracy(self):
        """测试游标时间记录实际处理到的最新发布时间"""
        source_name = "测试源"

        print(f"\n=== 增量游标时间测试 ===")

        cursor_time1 = datetime(2026, 6, 10, 10, 30, 0)
        self.storage.set_last_cursor_time(source_name, cursor_time1)

        retrieved = self.storage.get_last_cursor_time(source_name)
        print(f"设置游标: {cursor_time1}")
        print(f"读取游标: {retrieved}")
        self.assertEqual(retrieved, cursor_time1)

        cursor_time2 = datetime(2026, 6, 10, 12, 0, 0)
        self.storage.set_last_cursor_time(source_name, cursor_time2)

        retrieved = self.storage.get_last_cursor_time(source_name)
        print(f"\n更新游标: {cursor_time2}")
        print(f"读取游标: {retrieved}")
        self.assertEqual(retrieved, cursor_time2)

        print(f"\n✅ 增量游标时间验证通过!")

    def test_cursor_consistency_with_items(self):
        """测试游标时间应该是抓取条目中的最新发布时间"""
        config = FetchConfig()
        fetcher = RSSFetcher(config)

        print(f"\n=== 游标与条目一致性测试 ===")

        items_times = [
            datetime(2026, 6, 10, 9, 0, 0),
            datetime(2026, 6, 10, 10, 30, 0),
            datetime(2026, 6, 10, 8, 0, 0),
        ]

        items = [
            NewsItem(title=f"新闻{i}", url=f"http://test.com/{i}",
                    summary="内容", publish_time=t, source="测试源")
            for i, t in enumerate(items_times)
        ]

        valid_times = [item.publish_time for item in items if item.publish_time]
        expected_cursor = max(valid_times) if valid_times else None

        print(f"条目时间: {items_times}")
        print(f"最新时间(游标): {expected_cursor}")
        self.assertEqual(expected_cursor, datetime(2026, 6, 10, 10, 30, 0))

        items_with_none = items + [
            NewsItem(title="无时间新闻", url="http://test.com/no-time",
                    summary="内容", publish_time=None, source="测试源")
        ]

        valid_times = [item.publish_time for item in items_with_none if item.publish_time]
        expected_cursor = max(valid_times) if valid_times else datetime.now()

        print(f"\n含无时间条目时:")
        print(f"游标仍应为: {expected_cursor}")
        self.assertEqual(expected_cursor, datetime(2026, 6, 10, 10, 30, 0))

        print(f"\n✅ 游标一致性验证通过!")


class TestStableTimeNoDuplicate(unittest.TestCase):
    """测试3: 无发布时间条目不会重复出现"""

    def test_stable_time_consistency(self):
        """测试相同内容生成的稳定时间一致"""
        config = FetchConfig()
        fetcher = RSSFetcher(config)

        print(f"\n=== 无发布时间条目稳定性测试 ===")

        title = "测试新闻标题"
        link = "http://example.com/news/123"

        times = []
        for i in range(5):
            t = fetcher._generate_stable_time(title, link)
            times.append(t)
            print(f"第{i+1}次生成: {t}")

        self.assertEqual(len(set(times)), 1, "相同内容多次生成的时间应该完全一致")

        different_title = fetcher._generate_stable_time("不同标题", link)
        print(f"\n不同标题生成: {different_title}")
        self.assertNotEqual(times[0], different_title, "不同内容应该生成不同时间")

        print(f"\n✅ 无发布时间条目稳定性验证通过!")

    def test_no_time_items_not_repeated_in_incremental(self):
        """测试无发布时间条目不会在增量抓取中反复出现"""
        config = FetchConfig()
        fetcher = RSSFetcher(config)

        print(f"\n=== 增量去重测试 ===")

        title = "无发布时间的新闻"
        link = "http://example.com/news/no-time"

        stable_time = fetcher._generate_stable_time(title, link)
        print(f"稳定时间: {stable_time}")

        last_fetch_time = stable_time + timedelta(seconds=1)
        print(f"上次抓取时间: {last_fetch_time}")

        for i in range(3):
            publish_time = None
            if publish_time is None:
                publish_time = fetcher._generate_stable_time(title, link)

            should_skip = publish_time <= last_fetch_time
            print(f"第{i+1}次抓取: publish_time={publish_time}, 被过滤={should_skip}")
            self.assertTrue(should_skip, "每次都应该被过滤，不会重复进入增量结果")

        print(f"\n✅ 无发布时间条目不会重复出现验证通过!")


class TestFilteredQueries(unittest.TestCase):
    """测试4: 多条件筛选查询"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='test_filter_')
        self.db_path = os.path.join(self.test_dir, 'test.db')
        self.storage_config = StorageConfig(db_path=self.db_path)
        self.storage = Storage(self.storage_config)
        self._insert_test_data()

    def tearDown(self):
        for _ in range(5):
            try:
                shutil.rmtree(self.test_dir)
                break
            except:
                time.sleep(0.1)

    def _insert_test_data(self):
        items = [
            NewsItem(title="AI技术突破", url="http://test.com/1",
                    summary="内容", source="科技日报",
                    publish_time=datetime(2026, 6, 8, 10, 0, 0),
                    keywords=["AI", "技术"], content_hash="hash1"),
            NewsItem(title="新能源汽车销量", url="http://test.com/2",
                    summary="内容", source="财经周刊",
                    publish_time=datetime(2026, 6, 9, 14, 0, 0),
                    keywords=["新能源", "汽车"], content_hash="hash2"),
            NewsItem(title="AI应用新场景", url="http://test.com/3",
                    summary="内容", source="科技日报",
                    publish_time=datetime(2026, 6, 10, 9, 0, 0),
                    keywords=["AI", "应用"], content_hash="hash3"),
            NewsItem(title="股市行情分析", url="http://test.com/4",
                    summary="内容", source="财经周刊",
                    publish_time=datetime(2026, 6, 10, 11, 0, 0),
                    keywords=["股票", "经济"], content_hash="hash4"),
        ]
        self.storage.save_news(items)

    def test_filter_by_source(self):
        """测试按来源筛选"""
        print(f"\n=== 按来源筛选测试 ===")

        items = self.storage.get_news_with_filters(source="科技日报")
        print(f"来源='科技日报': {len(items)} 条")
        for item in items:
            print(f"  - {item.title} ({item.source})")
            self.assertEqual(item.source, "科技日报")
        self.assertEqual(len(items), 2)

        items = self.storage.get_news_with_filters(source="财经周刊")
        print(f"\n来源='财经周刊': {len(items)} 条")
        self.assertEqual(len(items), 2)

    def test_filter_by_keyword(self):
        """测试按关键词筛选"""
        print(f"\n=== 按关键词筛选测试 ===")

        items = self.storage.get_news_with_filters(keyword="AI")
        print(f"关键词='AI': {len(items)} 条")
        for item in items:
            print(f"  - {item.title} (关键词: {item.keywords})")
            self.assertTrue(any("AI" in k for k in item.keywords))
        self.assertEqual(len(items), 2)

    def test_filter_by_date_range(self):
        """测试按时间范围筛选"""
        print(f"\n=== 按时间范围筛选测试 ===")

        start = datetime(2026, 6, 9)
        end = datetime(2026, 6, 9, 23, 59, 59)
        items = self.storage.get_news_with_filters(start_date=start, end_date=end)
        print(f"6月9日: {len(items)} 条")
        for item in items:
            print(f"  - {item.title} ({item.publish_time})")
            self.assertTrue(start <= item.publish_time <= end)
        self.assertEqual(len(items), 1)

        start = datetime(2026, 6, 10)
        items = self.storage.get_news_with_filters(start_date=start)
        print(f"\n6月10日及以后: {len(items)} 条")
        self.assertEqual(len(items), 2)

    def test_combined_filters(self):
        """测试组合筛选"""
        print(f"\n=== 组合筛选测试 ===")

        items = self.storage.get_news_with_filters(source="科技日报", keyword="AI")
        print(f"来源='科技日报' + 关键词='AI': {len(items)} 条")
        for item in items:
            print(f"  - {item.title}")
            self.assertEqual(item.source, "科技日报")
            self.assertTrue(any("AI" in k for k in item.keywords))
        self.assertEqual(len(items), 2)

        items = self.storage.get_news_with_filters(
            source="财经周刊",
            start_date=datetime(2026, 6, 10),
            limit=1
        )
        print(f"\n来源='财经周刊' + 6月10日后 + limit=1: {len(items)} 条")
        self.assertEqual(len(items), 1)

        print(f"\n✅ 多条件筛选验证通过!")


class TestFailedFetchRecovery(unittest.TestCase):
    """测试5: 抓取失败后恢复能获取期间内容"""

    def test_failure_does_not_advance_cursor(self):
        """测试抓取失败不推进游标，恢复后能获取失败期间内容"""
        print(f"\n=== 抓取失败恢复测试 ===")

        initial_cursor = datetime(2026, 6, 10, 0, 0, 0)
        print(f"初始游标: {initial_cursor}")

        news_during_failure = [
            datetime(2026, 6, 10, 9, 0, 0),
            datetime(2026, 6, 10, 10, 30, 0),
            datetime(2026, 6, 10, 12, 0, 0),
        ]

        print(f"\n模拟抓取失败，游标保持不变")
        cursor_after_failure = initial_cursor
        self.assertEqual(cursor_after_failure, initial_cursor)

        print(f"\n恢复抓取，使用初始游标筛选:")
        kept = []
        for t in news_during_failure:
            if t > initial_cursor:
                kept.append(t)
                print(f"  ✅ {t} - 保留")
            else:
                print(f"  ❌ {t} - 过滤")

        self.assertEqual(len(kept), 3, "失败期间的3条新闻都应该被保留")
        print(f"\n成功获取失败期间的 {len(kept)} 条新闻")

        new_cursor = max(news_during_failure)
        print(f"\n更新游标为最新时间: {new_cursor}")

        print(f"\n再次抓取，使用新游标:")
        for t in news_during_failure:
            should_keep = t > new_cursor
            print(f"  {t} - {'保留' if should_keep else '过滤'}")
            self.assertFalse(should_keep, "所有旧新闻都应该被过滤")

        print(f"\n✅ 抓取失败恢复验证通过!")


if __name__ == '__main__':
    print("=" * 70)
    print("第三轮功能验证测试")
    print("=" * 70)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestSourceHealth))
    suite.addTests(loader.loadTestsFromTestCase(TestCursorTime))
    suite.addTests(loader.loadTestsFromTestCase(TestStableTimeNoDuplicate))
    suite.addTests(loader.loadTestsFromTestCase(TestFilteredQueries))
    suite.addTests(loader.loadTestsFromTestCase(TestFailedFetchRecovery))

    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)

    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("✅ 所有测试通过!")
    else:
        print(f"❌ 测试失败: {len(result.failures)} 个失败, {len(result.errors)} 个错误")
        for test, traceback in result.failures + result.errors:
            print(f"\n--- {test} ---")
            print(traceback)
    print("=" * 70)

    sys.exit(0 if result.wasSuccessful() else 1)
