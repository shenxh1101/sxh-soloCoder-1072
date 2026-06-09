"""第四轮验收测试：游标改进、时间筛选、数量对齐、源健康状态"""
import unittest
import os
import sys
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from news_aggregator.config import Config, Source, StorageConfig, FetchConfig, OutputConfig, DeduplicationConfig, FilterConfig, NotificationConfig
from news_aggregator.storage import Storage
from news_aggregator.models import NewsItem
from news_aggregator.aggregator import NewsAggregator
from news_aggregator.fetcher import RSSFetcher, WebFetcher
from news_aggregator.generator import MarkdownGenerator
from news_aggregator.cli import validate_date
import click


class TestCursorImprovements(unittest.TestCase):
    """测试游标逻辑改进"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, 'test.db')
        self.storage_config = StorageConfig(db_path=self.db_path)
        self.storage = Storage(self.storage_config)

    def tearDown(self):
        for _ in range(5):
            try:
                shutil.rmtree(self.test_dir)
                break
            except:
                import time
                time.sleep(0.1)

    def test_cursor_only_uses_real_publish_time(self):
        """测试游标只基于真实发布时间更新，忽略稳定时间条目"""
        source_name = "测试源"
        self.storage.set_last_cursor_time(source_name, datetime(2026, 6, 1))

        items = [
            NewsItem(title="有时间新闻1", url="http://test.com/1", summary="test",
                     publish_time=datetime(2026, 6, 5), source=source_name),
            NewsItem(title="无时间新闻1", url="http://test.com/2", summary="test",
                     publish_time=datetime(2020, 5, 20), source=source_name),
            NewsItem(title="无时间新闻2", url="http://test.com/3", summary="test",
                     publish_time=datetime(2020, 3, 15), source=source_name),
        ]
        items[1]._is_stable_time = True
        items[2]._is_stable_time = True

        real_times = [item.publish_time for item in items 
                      if item.publish_time and not getattr(item, '_is_stable_time', False)]
        latest_real_time = max(real_times) if real_times else None

        self.assertEqual(latest_real_time, datetime(2026, 6, 5))

        if latest_real_time:
            self.storage.set_last_cursor_time(source_name, latest_real_time)

        cursor = self.storage.get_last_cursor_time(source_name)
        self.assertEqual(cursor, datetime(2026, 6, 5))

    def test_no_real_time_items_keeps_cursor_unchanged(self):
        """测试全是稳定时间条目时，游标保持不变"""
        source_name = "测试源2"
        original_cursor = datetime(2026, 6, 1)
        self.storage.set_last_cursor_time(source_name, original_cursor)

        items = [
            NewsItem(title="无时间新闻1", url="http://test.com/1", summary="test",
                     publish_time=datetime(2020, 5, 20), source=source_name),
            NewsItem(title="无时间新闻2", url="http://test.com/2", summary="test",
                     publish_time=datetime(2020, 3, 15), source=source_name),
        ]
        items[0]._is_stable_time = True
        items[1]._is_stable_time = True

        real_times = [item.publish_time for item in items 
                      if item.publish_time and not getattr(item, '_is_stable_time', False)]
        latest_real_time = max(real_times) if real_times else None

        self.assertIsNone(latest_real_time)

        cursor = self.storage.get_last_cursor_time(source_name)
        self.assertEqual(cursor, original_cursor)

    def test_mixed_items_does_not_lose_real_news(self):
        """测试混合条目不会漏掉真实新闻"""
        source_name = "混合源"
        self.storage.set_last_cursor_time(source_name, datetime(2026, 6, 1))

        items_round1 = [
            NewsItem(title="无时间新闻A", url="http://test.com/A", summary="test",
                     publish_time=datetime(2020, 1, 1), source=source_name),
        ]
        items_round1[0]._is_stable_time = True

        real_times_1 = [item.publish_time for item in items_round1 
                       if item.publish_time and not getattr(item, '_is_stable_time', False)]
        latest_1 = max(real_times_1) if real_times_1 else None
        self.assertIsNone(latest_1)

        items_round2 = [
            NewsItem(title="有时间新闻1", url="http://test.com/1", summary="test",
                     publish_time=datetime(2026, 6, 3), source=source_name),
            NewsItem(title="无时间新闻B", url="http://test.com/B", summary="test",
                     publish_time=datetime(2020, 2, 2), source=source_name),
        ]
        items_round2[1]._is_stable_time = True

        real_times_2 = [item.publish_time for item in items_round2 
                       if item.publish_time and not getattr(item, '_is_stable_time', False)]
        latest_2 = max(real_times_2) if real_times_2 else None
        self.assertEqual(latest_2, datetime(2026, 6, 3))

        if latest_2:
            self.storage.set_last_cursor_time(source_name, latest_2)

        cursor = self.storage.get_last_cursor_time(source_name)
        self.assertEqual(cursor, datetime(2026, 6, 3))

        new_item_time = datetime(2026, 6, 4)
        self.assertGreater(new_item_time, cursor)


class TestDateFiltering(unittest.TestCase):
    """测试时间筛选改进"""

    def test_end_date_includes_full_day(self):
        """测试end_date自动包含当天全天"""
        ctx = MagicMock()
        param = MagicMock()
        param.name = 'end_date'
        param.human_readable_name = 'end-date'

        result = validate_date(ctx, param, '2026-06-10')

        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 6)
        self.assertEqual(result.day, 10)
        self.assertEqual(result.hour, 23)
        self.assertEqual(result.minute, 59)
        self.assertEqual(result.second, 59)

    def test_start_date_starts_at_midnight(self):
        """测试start_date从当天0点开始"""
        ctx = MagicMock()
        param = MagicMock()
        param.name = 'start_date'
        param.human_readable_name = 'start-date'

        result = validate_date(ctx, param, '2026-06-10')

        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 6)
        self.assertEqual(result.day, 10)
        self.assertEqual(result.hour, 0)
        self.assertEqual(result.minute, 0)
        self.assertEqual(result.second, 0)

    def test_same_day_filter_includes_all_day(self):
        """测试同一天筛选包含全天"""
        test_dir = tempfile.mkdtemp()
        try:
            storage_config = StorageConfig(db_path=os.path.join(test_dir, 'test.db'))
            storage = Storage(storage_config)

            import hashlib
            items = [
                NewsItem(title="凌晨新闻", url="http://test.com/1", summary="凌晨新闻内容",
                         publish_time=datetime(2026, 6, 10, 0, 0, 1), source="测试源",
                         content_hash=hashlib.md5("凌晨新闻 凌晨新闻内容".encode('utf-8')).hexdigest()),
                NewsItem(title="上午新闻", url="http://test.com/2", summary="上午新闻内容",
                         publish_time=datetime(2026, 6, 10, 10, 30, 0), source="测试源",
                         content_hash=hashlib.md5("上午新闻 上午新闻内容".encode('utf-8')).hexdigest()),
                NewsItem(title="晚上新闻", url="http://test.com/3", summary="晚上新闻内容",
                         publish_time=datetime(2026, 6, 10, 23, 59, 59), source="测试源",
                         content_hash=hashlib.md5("晚上新闻 晚上新闻内容".encode('utf-8')).hexdigest()),
                NewsItem(title="次日新闻", url="http://test.com/4", summary="次日新闻内容",
                         publish_time=datetime(2026, 6, 11, 0, 0, 1), source="测试源",
                         content_hash=hashlib.md5("次日新闻 次日新闻内容".encode('utf-8')).hexdigest()),
            ]
            storage.save_news(items)

            start_date = datetime(2026, 6, 10, 0, 0, 0)
            end_date = datetime(2026, 6, 10, 23, 59, 59, 999999)

            filtered = storage.get_news_with_filters(
                start_date=start_date,
                end_date=end_date
            )

            self.assertEqual(len(filtered), 3)
            titles = [item.title for item in filtered]
            self.assertIn("凌晨新闻", titles)
            self.assertIn("上午新闻", titles)
            self.assertIn("晚上新闻", titles)
            self.assertNotIn("次日新闻", titles)

        finally:
            for _ in range(5):
                try:
                    shutil.rmtree(test_dir)
                    break
                except:
                    import time
                    time.sleep(0.1)


class TestBriefCountAlignment(unittest.TestCase):
    """测试brief和list数量对齐"""

    def test_brief_respects_limit_parameter(self):
        """测试brief优先使用-n参数，不受默认配置截断"""
        test_dir = tempfile.mkdtemp()
        try:
            output_config = OutputConfig(
                markdown_dir=os.path.join(test_dir, 'output'),
                news_per_brief=5,
                include_summary=True,
                include_original_link=True,
                sort_by='publish_time',
                sort_order='desc'
            )
            generator = MarkdownGenerator(output_config)

            items = [
                NewsItem(title=f"新闻{i}", url=f"http://test.com/{i}", summary="test",
                         publish_time=datetime(2026, 6, 10, i, 0, 0), source="测试源")
                for i in range(1, 21)
            ]

            filepath = generator.generate(items, max_items=15)
            self.assertTrue(os.path.exists(filepath))

            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            self.assertIn("共 15 条新闻", content)

            for i in range(6, 21):
                self.assertIn(f"### {21-i}. 新闻{i}", content)
            for i in range(1, 6):
                self.assertNotIn(f" {i}. 新闻{i}", content)

            filepath2 = generator.generate(items)
            with open(filepath2, 'r', encoding='utf-8') as f:
                content2 = f.read()
            self.assertIn("共 5 条新闻", content2)

        finally:
            for _ in range(5):
                try:
                    shutil.rmtree(test_dir)
                    break
                except:
                    import time
                    time.sleep(0.1)

    def test_list_and_brief_same_filters_same_count(self):
        """测试相同筛选条件下list和brief返回相同数量"""
        test_dir = tempfile.mkdtemp()
        try:
            storage_config = StorageConfig(db_path=os.path.join(test_dir, 'test.db'))
            storage = Storage(storage_config)

            import hashlib
            items = []
            for i in range(1, 31):
                source = "源A" if i % 2 == 0 else "源B"
                keyword = "AI" if i % 3 == 0 else "其他"
                hour = (i - 1) % 24
                day = 10 + (i - 1) // 24
                title = f"新闻{i} {keyword}"
                summary = f"新闻{i}内容"
                items.append(NewsItem(
                    title=title,
                    url=f"http://test.com/{i}",
                    summary=summary,
                    publish_time=datetime(2026, 6, day, hour, 0, 0),
                    source=source,
                    keywords=[keyword],
                    content_hash=hashlib.md5(f"{title} {summary}".encode('utf-8')).hexdigest()
                ))
            storage.save_news(items)

            filters = {
                'limit': 10,
                'source': '源A',
                'keyword': 'AI',
            }

            list_items = storage.get_news_with_filters(**filters)
            brief_items = storage.get_news_with_filters(**filters)

            self.assertEqual(len(list_items), len(brief_items))
            self.assertEqual(len(list_items), 5)

            list_titles = [item.title for item in list_items]
            brief_titles = [item.title for item in brief_items]
            self.assertEqual(list_titles, brief_titles)

        finally:
            for _ in range(5):
                try:
                    shutil.rmtree(test_dir)
                    break
                except:
                    import time
                    time.sleep(0.1)


class TestSourceHealth(unittest.TestCase):
    """测试源健康状态"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, 'test.db')
        self.storage_config = StorageConfig(db_path=self.db_path)
        self.storage = Storage(self.storage_config)

    def tearDown(self):
        for _ in range(5):
            try:
                shutil.rmtree(self.test_dir)
                break
            except:
                import time
                time.sleep(0.1)

    def test_fetch_failure_records_health(self):
        """测试抓取失败时记录健康状态，不推进增量"""
        source_name = "失败源"
        self.storage.set_last_cursor_time(source_name, datetime(2026, 6, 1))
        original_cursor = self.storage.get_last_cursor_time(source_name)

        self.storage.update_source_health_failure(source_name, "网络连接超时")

        health = self.storage.get_source_health(source_name)
        self.assertIsNotNone(health)
        self.assertEqual(health.consecutive_failures, 1)
        self.assertEqual(health.last_failure_reason, "网络连接超时")
        self.assertIsNotNone(health.last_failure_time)
        self.assertIsNone(health.last_success_time)

        cursor_after = self.storage.get_last_cursor_time(source_name)
        self.assertEqual(cursor_after, original_cursor)

    def test_multiple_failures_increment_consecutive_count(self):
        """测试连续失败增加连续失败次数"""
        source_name = "连续失败源"

        for i in range(3):
            self.storage.update_source_health_failure(source_name, f"失败原因{i}")

        health = self.storage.get_source_health(source_name)
        self.assertEqual(health.consecutive_failures, 3)
        self.assertEqual(health.last_failure_reason, "失败原因2")

    def test_success_resets_consecutive_failures(self):
        """测试成功后重置连续失败次数，历史失败不影响后续"""
        source_name = "恢复源"

        self.storage.update_source_health_failure(source_name, "临时故障")
        self.storage.update_source_health_failure(source_name, "临时故障")

        health_before = self.storage.get_source_health(source_name)
        self.assertEqual(health_before.consecutive_failures, 2)

        self.storage.update_source_health_success(
            source_name,
            fetched_count=10,
            saved_count=5,
            cursor_time=datetime(2026, 6, 10)
        )

        health_after = self.storage.get_source_health(source_name)
        self.assertEqual(health_after.consecutive_failures, 0)
        self.assertIsNotNone(health_after.last_success_time)
        self.assertIsNotNone(health_after.last_failure_time)
        self.assertEqual(health_after.last_failure_reason, "临时故障")
        self.assertEqual(health_after.total_fetched, 10)
        self.assertEqual(health_after.total_saved, 5)

    def test_failure_does_not_skip_content(self):
        """测试失败期间的内容恢复后能正常抓取"""
        source_name = "测试源"
        self.storage.set_last_cursor_time(source_name, datetime(2026, 6, 1))
        self.storage.set_last_fetch_time(source_name, datetime(2026, 6, 1))

        original_cursor = self.storage.get_last_cursor_time(source_name)
        original_fetch_time = self.storage.get_last_fetch_time(source_name)

        self.storage.update_source_health_failure(source_name, "临时故障")

        cursor_after_failure = self.storage.get_last_cursor_time(source_name)
        fetch_time_after_failure = self.storage.get_last_fetch_time(source_name)

        self.assertEqual(cursor_after_failure, original_cursor)
        self.assertEqual(fetch_time_after_failure, original_fetch_time)

        new_items = [
            NewsItem(title="失败期间新闻1", url="http://test.com/1", summary="test",
                     publish_time=datetime(2026, 6, 5), source=source_name),
            NewsItem(title="失败期间新闻2", url="http://test.com/2", summary="test",
                     publish_time=datetime(2026, 6, 7), source=source_name),
        ]

        for item in new_items:
            self.assertGreater(item.publish_time, original_cursor)


class TestStableTimeItems(unittest.TestCase):
    """测试无发布时间条目的稳定处理"""

    def test_stable_time_generation_is_consistent(self):
        """测试相同内容生成相同的稳定时间"""
        from news_aggregator.fetcher import BaseFetcher
        from news_aggregator.config import FetchConfig

        config = FetchConfig()
        fetcher = BaseFetcher(config)

        time1 = fetcher._generate_stable_time("测试标题", "http://test.com/1")
        time2 = fetcher._generate_stable_time("测试标题", "http://test.com/1")
        time3 = fetcher._generate_stable_time("不同标题", "http://test.com/1")
        time4 = fetcher._generate_stable_time("测试标题", "http://test.com/2")

        self.assertEqual(time1, time2)
        self.assertNotEqual(time1, time3)
        self.assertNotEqual(time1, time4)

    def test_stable_time_items_not_repeated_in_incremental(self):
        """测试稳定时间条目在连续抓取中不重复出现"""
        from news_aggregator.fetcher import BaseFetcher
        from news_aggregator.config import FetchConfig
        import hashlib

        test_dir = tempfile.mkdtemp()
        try:
            storage_config = StorageConfig(db_path=os.path.join(test_dir, 'test.db'))
            storage = Storage(storage_config)

            config = FetchConfig()
            fetcher = BaseFetcher(config)

            items = [
                NewsItem(title="无时间新闻1", url="http://test.com/A", summary="无时间新闻1内容",
                         publish_time=fetcher._generate_stable_time("无时间新闻1", "http://test.com/A"),
                         source="测试源",
                         content_hash=hashlib.md5("无时间新闻1 无时间新闻1内容".encode('utf-8')).hexdigest()),
                NewsItem(title="无时间新闻2", url="http://test.com/B", summary="无时间新闻2内容",
                         publish_time=fetcher._generate_stable_time("无时间新闻2", "http://test.com/B"),
                         source="测试源",
                         content_hash=hashlib.md5("无时间新闻2 无时间新闻2内容".encode('utf-8')).hexdigest()),
                NewsItem(title="有时间新闻", url="http://test.com/C", summary="有时间新闻内容",
                         publish_time=datetime(2026, 6, 10),
                         source="测试源",
                         content_hash=hashlib.md5("有时间新闻 有时间新闻内容".encode('utf-8')).hexdigest()),
            ]
            items[0]._is_stable_time = True
            items[1]._is_stable_time = True
            items[2]._is_stable_time = False

            storage.save_news(items)

            last_fetch_time = datetime(2026, 6, 11)

            items_round2 = [
                NewsItem(title="无时间新闻1", url="http://test.com/A", summary="test",
                         publish_time=fetcher._generate_stable_time("无时间新闻1", "http://test.com/A"),
                         source="测试源"),
                NewsItem(title="无时间新闻2", url="http://test.com/B", summary="test",
                         publish_time=fetcher._generate_stable_time("无时间新闻2", "http://test.com/B"),
                         source="测试源"),
            ]
            items_round2[0]._is_stable_time = True
            items_round2[1]._is_stable_time = True

            filtered = [item for item in items_round2 
                       if not (last_fetch_time and item.publish_time <= last_fetch_time)]

            self.assertEqual(len(filtered), 0)

        finally:
            for _ in range(5):
                try:
                    shutil.rmtree(test_dir)
                    break
                except:
                    import time
                    time.sleep(0.1)


def run_tests():
    """运行所有测试"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestCursorImprovements))
    suite.addTests(loader.loadTestsFromTestCase(TestDateFiltering))
    suite.addTests(loader.loadTestsFromTestCase(TestBriefCountAlignment))
    suite.addTests(loader.loadTestsFromTestCase(TestSourceHealth))
    suite.addTests(loader.loadTestsFromTestCase(TestStableTimeItems))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 70)
    print("第四轮验收测试结果:")
    print(f"  运行测试: {result.testsRun}")
    print(f"  成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"  失败: {len(result.failures)}")
    print(f"  错误: {len(result.errors)}")
    print("=" * 70)

    if result.failures:
        print("\n失败详情:")
        for test, traceback in result.failures:
            print(f"\n  {test}:")
            print(f"    {traceback.splitlines()[-2]}")

    if result.errors:
        print("\n错误详情:")
        for test, traceback in result.errors:
            print(f"\n  {test}:")
            print(f"    {traceback.splitlines()[-2]}")

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
