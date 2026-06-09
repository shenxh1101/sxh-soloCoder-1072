#!/usr/bin/env python3
"""
多源新闻聚合与去重工具
======================

基于Python的命令行多源新闻聚合工具，支持：
- 多源RSS/网页抓取
- Simhash相似度去重
- 关键词过滤
- Markdown简报生成
- 邮件/Webhook通知
- 增量更新
- 多线程并发
- CSV导出
- 定时抓取
"""

from news_aggregator.cli import main

if __name__ == '__main__':
    main()
