#!/usr/bin/env python3
"""
功能测试脚本 - 验证各模块核心功能
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from news_aggregator.models import NewsItem
from news_aggregator.deduplicator import SimHash, Deduplicator
from news_aggregator.filter import KeywordFilter
from news_aggregator.config import DeduplicationConfig, KeywordsConfig, FilterConfig
from news_aggregator.generator import MarkdownGenerator
from news_aggregator.config import OutputConfig
from news_aggregator.exporter import CSVExporter
from news_aggregator.storage import Storage
from news_aggregator.config import StorageConfig

def test_simhash():
    print("=" * 60)
    print("📊 测试 SimHash 相似度计算")
    print("=" * 60)

    simhash = SimHash(hash_bits=64)

    text1 = "人工智能技术在医疗领域的应用取得重大突破"
    text2 = "人工智能技术在医疗领域的应用取得了重大突破"
    text3 = "新能源汽车市场销量持续增长"

    hash1 = simhash.compute(text1)
    hash2 = simhash.compute(text2)
    hash3 = simhash.compute(text3)

    sim12 = simhash.similarity(hash1, hash2)
    sim13 = simhash.similarity(hash1, hash3)

    print(f"文本1: {text1}")
    print(f"文本2: {text2}")
    print(f"文本3: {text3}")
    print()
    print(f"文本1与文本2相似度: {sim12:.4f} (应该接近1.0)")
    print(f"文本1与文本3相似度: {sim13:.4f} (应该较低)")
    print()

    assert sim12 > 0.8, f"相似文本相似度应该 > 0.8, 实际: {sim12}"
    assert sim13 < 0.5, f"不相似文本相似度应该 < 0.5, 实际: {sim13}"

    print("✅ SimHash 测试通过!")
    print()

def test_deduplicator():
    print("=" * 60)
    print("🔍 测试去重功能")
    print("=" * 60)

    dedup_config = DeduplicationConfig(enabled=True, similarity_threshold=0.85, hash_bits=64)
    deduplicator = Deduplicator(dedup_config)

    existing_items = [
        NewsItem(
            id=1,
            title="人工智能技术在医疗领域的应用取得重大突破",
            url="http://example.com/news/1",
            summary="AI技术正在改变医疗行业的面貌...",
            source="测试源1",
            publish_time=datetime.now()
        ),
        NewsItem(
            id=2,
            title="新能源汽车销量创新高",
            url="http://example.com/news/2",
            summary="电动汽车市场持续火热...",
            source="测试源2",
            publish_time=datetime.now()
        )
    ]

    for item in existing_items:
        content = item.title + ' ' + item.summary
        from hashlib import md5
        import re
        normalized = re.sub(r'[^\w\u4e00-\u9fff]', '', content).lower()
        item.content_hash = md5(normalized.encode('utf-8')).hexdigest()
        item.simhash = SimHash(64).compute(content)

    deduplicator.load_existing(existing_items)

    test_items = [
        NewsItem(
            title="人工智能技术在医疗领域的应用取得了重大突破",
            url="http://example.com/news/3",
            summary="AI技术正在改变医疗行业的面貌...",
            source="测试源3",
            publish_time=datetime.now()
        ),
        NewsItem(
            title="量子计算取得新进展",
            url="http://example.com/news/4",
            summary="量子计算机研发取得重大突破...",
            source="测试源1",
            publish_time=datetime.now()
        ),
        NewsItem(
            title="新能源汽车市场销量持续增长",
            url="http://example.com/news/5",
            summary="电动汽车市场销量持续增长...",
            source="测试源2",
            publish_time=datetime.now()
        )
    ]

    deduped = deduplicator.dedupe_items(test_items)

    print(f"输入: {len(test_items)} 条")
    print(f"去重后: {len(deduped)} 条")
    print()
    for item in deduped:
        print(f"  ✅ {item.title[:30]}...")

    print()
    assert len(deduped) == 2, f"应该去重到2条, 实际: {len(deduped)}"
    print("✅ 去重功能测试通过!")
    print()

def test_keyword_filter():
    print("=" * 60)
    print("🏷️  测试关键词过滤")
    print("=" * 60)

    keywords_config = KeywordsConfig(
        include=["AI", "人工智能", "新能源", "电动汽车"],
        exclude=["广告", "推广"]
    )
    filter_config = FilterConfig(max_summary_length=200, min_title_length=5)
    keyword_filter = KeywordFilter(keywords_config, filter_config)

    test_items = [
        NewsItem(
            title="AI技术在医疗领域的应用",
            url="http://example.com/1",
            summary="人工智能技术正在改变医疗行业...",
            source="测试",
            publish_time=datetime.now()
        ),
        NewsItem(
            title="新能源汽车销量创新高",
            url="http://example.com/2",
            summary="电动汽车市场持续增长...",
            source="测试",
            publish_time=datetime.now()
        ),
        NewsItem(
            title="这是一条广告推广信息",
            url="http://example.com/3",
            summary="快来购买我们的产品...",
            source="测试",
            publish_time=datetime.now()
        ),
        NewsItem(
            title="天气晴朗适合出游",
            url="http://example.com/4",
            summary="今天天气很好...",
            source="测试",
            publish_time=datetime.now()
        ),
        NewsItem(
            title="短",
            url="http://example.com/5",
            summary="标题过短的新闻",
            source="测试",
            publish_time=datetime.now()
        )
    ]

    filtered = keyword_filter.filter_items(test_items)

    print(f"输入: {len(test_items)} 条")
    print(f"过滤后: {len(filtered)} 条")
    print()
    for item in filtered:
        print(f"  ✅ {item.title} (关键词: {item.keywords})")

    print()
    assert len(filtered) == 2, f"应该过滤到2条, 实际: {len(filtered)}"
    print("✅ 关键词过滤测试通过!")
    print()

def test_markdown_generator():
    print("=" * 60)
    print("📄 测试 Markdown 生成")
    print("=" * 60)

    output_config = OutputConfig(
        markdown_dir="./test_output",
        include_original_link=True,
        include_summary=True,
        news_per_brief=10,
        sort_by="publish_time",
        sort_order="desc"
    )

    generator = MarkdownGenerator(output_config)

    test_items = [
        NewsItem(
            id=1,
            title="AI技术在医疗领域的应用取得重大突破",
            url="http://example.com/news/1",
            summary="人工智能技术正在深刻改变医疗行业的各个方面，从诊断到治疗都展现出巨大潜力。",
            source="科技日报",
            publish_time=datetime.now(),
            keywords=["AI", "医疗", "人工智能"]
        ),
        NewsItem(
            id=2,
            title="新能源汽车市场销量创历史新高",
            url="http://example.com/news/2",
            summary="随着技术成熟和政策支持，新能源汽车市场持续火爆，销量不断攀升。",
            source="财经新闻",
            publish_time=datetime.now() - timedelta(hours=2),
            keywords=["新能源", "电动汽车"]
        )
    ]

    filepath = generator.generate(test_items, title="测试新闻简报")

    print(f"生成的文件: {filepath}")
    assert os.path.exists(filepath), "Markdown文件应该存在"

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    assert "AI技术在医疗领域的应用" in content
    assert "新能源汽车市场销量" in content
    assert "科技日报" in content
    assert "http://example.com/news/1" in content

    print("✅ Markdown 生成测试通过!")
    print()

def test_storage():
    print("=" * 60)
    print("💾 测试数据存储")
    print("=" * 60)

    storage_config = StorageConfig(
        db_path="./test_data/test_news.db",
        history_days=30
    )

    if os.path.exists(storage_config.db_path):
        os.remove(storage_config.db_path)

    storage = Storage(storage_config)

    test_items = [
        NewsItem(
            title="测试新闻1",
            url="http://example.com/1",
            summary="这是测试新闻1的摘要",
            source="测试源",
            publish_time=datetime.now(),
            content_hash="hash1",
            simhash=12345,
            keywords=["测试", "新闻"]
        ),
        NewsItem(
            title="测试新闻2",
            url="http://example.com/2",
            summary="这是测试新闻2的摘要",
            source="测试源",
            publish_time=datetime.now(),
            content_hash="hash2",
            simhash=67890,
            keywords=["测试", "数据"]
        )
    ]

    saved = storage.save_news(test_items)
    print(f"保存了 {len(saved)} 条新闻")
    assert len(saved) == 2, "应该保存2条新闻"

    all_news = storage.get_all_news()
    print(f"数据库中共有 {len(all_news)} 条新闻")
    assert len(all_news) == 2, "应该有2条新闻"

    count = storage.get_news_count()
    print(f"新闻总数: {count}")
    assert count == 2, "总数应该是2"

    storage.set_last_fetch_time("测试源", datetime.now())
    last_fetch = storage.get_last_fetch_time("测试源")
    print(f"上次抓取时间: {last_fetch}")
    assert last_fetch is not None, "应该有上次抓取时间"

    print("✅ 数据存储测试通过!")
    print()

def test_csv_exporter():
    print("=" * 60)
    print("📊 测试 CSV 导出")
    print("=" * 60)

    storage_config = StorageConfig(
        db_path="./test_data/test_news.db",
        history_days=30
    )
    storage = Storage(storage_config)
    exporter = CSVExporter(storage)

    filepath = exporter.export_all(output_dir="./test_output")
    print(f"导出的文件: {filepath}")

    assert os.path.exists(filepath), "CSV文件应该存在"

    with open(filepath, 'r', encoding='utf-8-sig') as f:
        lines = f.readlines()

    print(f"CSV行数: {len(lines)}")
    assert len(lines) >= 3, "应该至少有表头+2条数据"
    assert "标题" in lines[0], "表头应该包含'标题'"

    print("✅ CSV 导出测试通过!")
    print()

def main():
    print("\n" + "=" * 60)
    print("🚀 开始功能测试")
    print("=" * 60 + "\n")

    try:
        test_simhash()
        test_deduplicator()
        test_keyword_filter()
        test_markdown_generator()
        test_storage()
        test_csv_exporter()

        print("=" * 60)
        print("🎉 所有测试通过!")
        print("=" * 60)

        print("\n🧹 清理测试数据...")
        import shutil
        import time
        for path in ["./test_data", "./test_output"]:
            if os.path.exists(path):
                for attempt in range(3):
                    try:
                        shutil.rmtree(path)
                        break
                    except Exception as e:
                        if attempt < 2:
                            time.sleep(0.5)
                        else:
                            print(f"⚠️  清理 {path} 失败: {e}")
        print("✅ 清理完成")

        return 0

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
