import os
import sys
import time
import logging
from datetime import datetime
from typing import Optional

import click
from tabulate import tabulate
from colorama import init, Fore, Style

from .config import load_config, Config
from .aggregator import NewsAggregator
from .exporter import CSVExporter
from .models import NewsItem

init(autoreset=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('news_aggregator.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def validate_positive_int(ctx, param, value):
    if value is None:
        return None

    param_name = param.human_readable_name or param.name

    try:
        value = int(value)
    except (ValueError, TypeError):
        raise click.BadParameter(
            f"{Style.BRIGHT}{param_name}{Style.RESET_ALL} 必须是有效的数字，"
            f"当前输入: {Style.BRIGHT}{Fore.RED}{value}{Fore.RESET}{Style.RESET_ALL}\n"
            f"  示例: {Style.BRIGHT}--{param.name} 10{Style.RESET_ALL}"
        )

    if value <= 0:
        error_type = "不能为0" if value == 0 else "不能为负数"
        raise click.BadParameter(
            f"{Style.BRIGHT}{param_name}{Style.RESET_ALL} {error_type}，"
            f"当前值: {Style.BRIGHT}{Fore.RED}{value}{Fore.RESET}{Style.RESET_ALL}\n"
            f"  请输入正整数，例如: {Style.BRIGHT}--{param.name} 10{Style.RESET_ALL}"
        )

    return value


def get_aggregator(config_path: str) -> NewsAggregator:
    try:
        config = load_config(config_path)
        return NewsAggregator(config)
    except FileNotFoundError:
        click.echo(Fore.RED + f"❌ 配置文件不存在: {config_path}")
        click.echo(f"请先创建配置文件，可复制 {Style.BRIGHT}config.example.yaml{Style.RESET_ALL} 为 {Style.BRIGHT}config.yaml{Style.RESET_ALL}")
        sys.exit(1)
    except Exception as e:
        click.echo(Fore.RED + f"❌ 加载配置失败: {e}")
        sys.exit(1)


def display_news(items: list, limit: int = None):
    if not items:
        click.echo(Fore.YELLOW + "⚠️  没有新闻可显示")
        return

    if limit:
        items = items[:limit]

    table_data = []
    for idx, item in enumerate(items, 1):
        publish_time = item.publish_time.strftime('%Y-%m-%d %H:%M') if item.publish_time else '未知'
        summary = (item.summary[:50] + '...') if len(item.summary) > 50 else item.summary
        keywords = ', '.join(item.keywords[:3]) if item.keywords else ''

        table_data.append([
            f"{Fore.CYAN}{idx}{Fore.RESET}",
            f"{Fore.GREEN}{item.title[:40]}{'...' if len(item.title) > 40 else ''}{Fore.RESET}",
            f"{Fore.YELLOW}{item.source}{Fore.RESET}",
            f"{Fore.MAGENTA}{publish_time}{Fore.RESET}",
            f"{Fore.BLUE}{keywords}{Fore.RESET}"
        ])

    headers = [
        f"{Fore.WHITE}{Style.BRIGHT}#",
        f"{Fore.WHITE}{Style.BRIGHT}标题",
        f"{Fore.WHITE}{Style.BRIGHT}来源",
        f"{Fore.WHITE}{Style.BRIGHT}发布时间",
        f"{Fore.WHITE}{Style.BRIGHT}标签"
    ]

    click.echo("\n" + tabulate(table_data, headers=headers, tablefmt="simple"))
    click.echo(f"\n共显示 {len(items)} 条新闻\n")


def display_news_detail(item: NewsItem):
    click.echo(f"\n{Fore.CYAN}{Style.BRIGHT}{'='*60}")
    click.echo(f"\n📰 {Fore.GREEN}{Style.BRIGHT}{item.title}{Style.RESET_ALL}\n")
    click.echo(f"{Fore.YELLOW}来源:{Fore.RESET} {item.source}")
    if item.publish_time:
        click.echo(f"{Fore.YELLOW}发布时间:{Fore.RESET} {item.publish_time.strftime('%Y-%m-%d %H:%M:%S')}")
    if item.fetched_at:
        click.echo(f"{Fore.YELLOW}抓取时间:{Fore.RESET} {item.fetched_at.strftime('%Y-%m-%d %H:%M:%S')}")
    if item.keywords:
        click.echo(f"{Fore.YELLOW}标签:{Fore.RESET} {', '.join(f'`{k}`' for k in item.keywords)}")
    click.echo(f"{Fore.YELLOW}链接:{Fore.RESET} {item.url}")
    click.echo(f"\n{Fore.CYAN}{Style.BRIGHT}摘要:{Style.RESET_ALL}\n")
    click.echo(f"  {item.summary}\n")
    click.echo(f"{Fore.CYAN}{Style.BRIGHT}{'='*60}{Fore.RESET}\n")


@click.group()
@click.option('--config', '-c', default='config.yaml', help='配置文件路径')
@click.pass_context
def cli(ctx, config):
    """📰 多源新闻聚合与去重工具"""
    ctx.ensure_object(dict)
    ctx.obj['config_path'] = config


@cli.command()
@click.option('--full', '-f', is_flag=True, help='全量抓取，忽略增量更新')
@click.option('--no-brief', is_flag=True, help='不生成Markdown简报')
@click.option('--no-notify', is_flag=True, help='不发送通知')
@click.pass_context
def fetch(ctx, full, no_brief, no_notify):
    """🔄 抓取新闻并处理"""
    config_path = ctx.obj['config_path']
    aggregator = get_aggregator(config_path)

    click.echo(Fore.CYAN + Style.BRIGHT + "\n🚀 开始抓取新闻...\n")

    result = aggregator.fetch_and_process(
        use_incremental=not full,
        generate_brief=not no_brief,
        send_notifications=not no_notify
    )

    stats = result['stats']
    duration = (result['fetch_end'] - result['fetch_start']).total_seconds()

    click.echo(f"\n{Fore.GREEN}{Style.BRIGHT}✅ 抓取完成!{Style.RESET_ALL}")
    click.echo(f"   ⏱️  耗时: {duration:.2f} 秒")
    click.echo(f"   📥 抓取总数: {stats['total_input']} 条")
    click.echo(f"   🔍 去重后: {stats['after_dedupe']} 条")
    click.echo(f"   🏷️  过滤后: {stats['after_filter']} 条")
    click.echo(f"   💾 已保存: {Fore.GREEN}{stats['saved']}{Fore.RESET} 条新新闻")

    if result['brief_path']:
        click.echo(f"   📄 Markdown简报: {Fore.CYAN}{result['brief_path']}{Fore.RESET}")

    if result['notifications']:
        email_status = Fore.GREEN + "成功" if result['notifications'].get('email') else Fore.RED + "失败/未启用"
        webhook_status = Fore.GREEN + "成功" if result['notifications'].get('webhook') else Fore.RED + "失败/未启用"
        click.echo(f"   📧 邮件通知: {email_status}{Fore.RESET}")
        click.echo(f"   🔔 Webhook通知: {webhook_status}{Fore.RESET}")

    if result['items']:
        click.echo(f"\n{Fore.CYAN}最新新闻:{Fore.RESET}")
        display_news(result['items'], limit=10)


@cli.command()
@click.option('--limit', '-n', default=20, type=int, callback=validate_positive_int, help='显示的新闻数量')
@click.option('--source', '-s', help='按来源过滤')
@click.option('--detail', '-d', is_flag=True, help='显示详细信息')
@click.pass_context
def list(ctx, limit, source, detail):
    """📋 查看最近新闻"""
    config_path = ctx.obj['config_path']
    aggregator = get_aggregator(config_path)

    items = aggregator.get_recent_news(limit=limit, source=source)

    if not items:
        click.echo(Fore.YELLOW + "⚠️  暂无新闻数据，请先执行抓取")
        return

    if detail and items:
        for i, item in enumerate(items, 1):
            if i > 1:
                click.echo(f"\n{Fore.CYAN}按 Enter 继续下一条，或输入 q 退出...{Fore.RESET}")
                user_input = input()
                if user_input.lower() == 'q':
                    break
            display_news_detail(item)
    else:
        display_news(items, limit=limit)


@cli.command()
@click.option('--days', '-d', default=7, type=int, callback=validate_positive_int, help='最近几天的新闻')
@click.option('--source', '-s', help='按来源过滤')
@click.option('--limit', '-n', type=int, callback=validate_positive_int, help='限制新闻数量')
@click.pass_context
def brief(ctx, days, source, limit):
    """📄 生成历史新闻简报"""
    config_path = ctx.obj['config_path']
    aggregator = get_aggregator(config_path)

    click.echo(Fore.CYAN + f"\n📄 正在生成最近 {days} 天的新闻简报...\n")

    filepath = aggregator.generate_brief_from_storage(
        days=days,
        source=source,
        limit=limit
    )

    if filepath:
        click.echo(Fore.GREEN + f"✅ 简报已生成: {filepath}")
    else:
        click.echo(Fore.YELLOW + "⚠️  没有足够的新闻生成简报")


@cli.command()
@click.option('--days', '-d', type=int, callback=validate_positive_int, help='导出最近几天的数据')
@click.option('--source', '-s', help='按来源导出')
@click.option('--output', '-o', default='./output', help='输出目录')
@click.argument('type', type=click.Choice(['all', 'recent', 'source']))
@click.pass_context
def export(ctx, type, days, source, output):
    """📊 导出新闻数据为CSV"""
    config_path = ctx.obj['config_path']
    aggregator = get_aggregator(config_path)
    exporter = CSVExporter(aggregator.storage)

    click.echo(Fore.CYAN + f"\n📊 正在导出数据...\n")

    filepath = ""
    if type == 'all':
        filepath = exporter.export_all(output_dir=output)
    elif type == 'recent':
        days = days or 7
        filepath = exporter.export_recent(days=days, output_dir=output)
    elif type == 'source':
        if not source:
            sources = aggregator.storage.get_sources()
            if not sources:
                click.echo(Fore.YELLOW + "⚠️  没有可用的来源")
                return
            click.echo(Fore.CYAN + "可用来源:")
            for i, s in enumerate(sources, 1):
                click.echo(f"  {i}. {s}")
            source = click.prompt("请输入要导出的来源名称", type=str)
        filepath = exporter.export_by_source(source=source, output_dir=output)

    if filepath:
        click.echo(Fore.GREEN + f"✅ 数据已导出: {filepath}")
    else:
        click.echo(Fore.YELLOW + "⚠️  没有数据可导出")


@cli.command()
@click.pass_context
def stats(ctx):
    """📈 查看统计信息"""
    config_path = ctx.obj['config_path']
    aggregator = get_aggregator(config_path)

    stats = aggregator.get_stats()

    click.echo(f"\n{Fore.CYAN}{Style.BRIGHT}📊 统计信息{Style.RESET_ALL}\n")
    click.echo(f"   {Fore.GREEN}总新闻数:{Fore.RESET} {stats['total_news']}")
    click.echo(f"   {Fore.GREEN}配置的源:{Fore.RESET} {len(stats['configured_sources'])} 个")
    click.echo(f"   {Fore.GREEN}启用的源:{Fore.RESET} {len(stats['enabled_sources'])} 个")

    if stats['enabled_sources']:
        click.echo(f"\n   {Fore.YELLOW}启用的源列表:{Fore.RESET}")
        for s in stats['enabled_sources']:
            count = stats['sources'].get(s, 0)
            click.echo(f"     • {s} ({count} 条新闻)")

    if stats['sources']:
        click.echo(f"\n   {Fore.YELLOW}各来源新闻数:{Fore.RESET}")
        for source, count in sorted(stats['sources'].items(), key=lambda x: x[1], reverse=True):
            click.echo(f"     • {source}: {count} 条")


@cli.command()
@click.option('--interval', '-i', type=int, callback=validate_positive_int, help='抓取间隔（分钟），覆盖配置文件')
@click.pass_context
def daemon(ctx, interval):
    """🔁 启动定时抓取服务"""
    config_path = ctx.obj['config_path']

    import schedule

    try:
        config = load_config(config_path)
        aggregator = NewsAggregator(config)
    except Exception as e:
        click.echo(Fore.RED + f"❌ 初始化失败: {e}")
        sys.exit(1)

    interval = interval or config.fetch.interval_minutes

    click.echo(Fore.CYAN + Style.BRIGHT + f"\n🔁 启动定时抓取服务，每 {interval} 分钟抓取一次\n")
    click.echo(Fore.YELLOW + "按 Ctrl+C 停止服务\n")

    def job():
        click.echo(f"\n{Fore.CYAN}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 开始定时抓取...{Fore.RESET}")
        try:
            result = aggregator.fetch_and_process()
            click.echo(f"{Fore.GREEN}抓取完成，新增 {result['stats']['saved']} 条新闻{Fore.RESET}")
        except Exception as e:
            click.echo(Fore.RED + f"抓取失败: {e}")

    schedule.every(interval).minutes.do(job)

    click.echo(Fore.GREEN + "服务已启动，正在等待下次抓取...\n")

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo(Fore.YELLOW + "\n\n⚠️  服务已停止")


@cli.command()
def init_config():
    """⚙️  创建默认配置文件"""
    if os.path.exists('config.yaml'):
        if not click.confirm(Fore.YELLOW + "config.yaml 已存在，是否覆盖？"):
            return

    from .config import create_default_config
    create_default_config('config.yaml')
    click.echo(Fore.GREEN + "✅ 已创建默认配置文件 config.yaml")
    click.echo("请根据需要修改配置，然后运行 fetch 命令开始抓取")


@cli.command()
@click.argument('news_id', type=int)
@click.pass_context
def show(ctx, news_id):
    """🔍 查看指定ID的新闻详情"""
    config_path = ctx.obj['config_path']
    aggregator = get_aggregator(config_path)

    all_news = aggregator.storage.get_all_news()
    item = next((n for n in all_news if n.id == news_id), None)

    if not item:
        click.echo(Fore.RED + f"❌ 找不到ID为 {news_id} 的新闻")
        return

    display_news_detail(item)


def main():
    cli(obj={})


if __name__ == '__main__':
    main()
