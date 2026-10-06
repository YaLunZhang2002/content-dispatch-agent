# -*- coding: utf-8 -*-
"""
Main CLI entry point for Content Dispatch Agent (cda).
Rich console UI with commands: run, ask, capacity, diff, stats, init-mock.
"""

import os
import sys
import yaml
import argparse
from typing import Optional

# Ensure package is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from dispatcher.spec import TaskSpec, ClarificationRequest
from dispatcher.parser import parse_workbook
from dispatcher.ledger import DispatchLedger
from dispatcher.allocator import CopyAllocator
from dispatcher.nl_parser import NaturalLanguageParser
from dispatcher.diff import WorkbookDiff
from dispatcher.senders.dry_run import DryRunSender
from dispatcher.senders.wechat_win32 import WeChatWin32Sender

console = Console(highlight=False)


def handle_run(args):
    """根据 YAML 配置文件执行分发"""
    with open(args.config, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    spec = TaskSpec(**config_data)
    execute_task(spec, dry_run=args.dry_run, target_chat=args.target)


def handle_ask(args):
    """基于自然语言指令驱动任务"""
    console.print(Panel(f"[bold cyan]自然语言指令:[/bold cyan] {args.prompt}", title="🤖 NL Dispatch Engine"))

    parser = NaturalLanguageParser()
    result = parser.parse(args.prompt, default_workbook=args.workbook)

    if isinstance(result, ClarificationRequest):
        console.print(Panel("[bold yellow]⚠️ 任务意图不完整，需要补充关键参数:[/bold yellow]", title="Clarifying Request"))
        for q in result.questions:
            console.print(f" • [bold yellow]{q}[/bold yellow]")
        return

    # 成功解析为 TaskSpec
    console.print(Panel(
        f"[green]解析成功！[/green]\n"
        f"• 责任人: [cyan]{result.owner}[/cyan]\n"
        f"• 序号范围: [cyan]{result.seq_start} ~ {result.seq_start + result.count - 1}[/cyan] (共 {result.count} 篇)\n"
        f"• 发布平台: [cyan]{', '.join(b.platform for b in result.blocks)}[/cyan]\n"
        f"• 文案策略: [cyan]{'同文案跨平台同步' if result.same_copy_across_platforms else '各平台独立分配'}[/cyan]",
        title="✅ 任务规格确认"
    ))

    if not args.yes and not args.dry_run:
        confirm = console.input("[bold yellow]是否确认执行分发? (y/N): [/bold yellow]")
        if confirm.lower() != 'y':
            console.print("[red]已取消执行。[/red]")
            return

    execute_task(result, dry_run=args.dry_run, target_chat=args.target)


def execute_task(spec: TaskSpec, dry_run: bool = False, target_chat: Optional[str] = None):
    """执行底层分发核心流程"""
    target = target_chat or spec.target_chat
    ledger_path = os.getenv("LEDGER_DB_PATH", "ledger.db")
    ledger = DispatchLedger(ledger_path)
    allocator = CopyAllocator(ledger)

    if not os.path.exists(spec.workbook_path):
        console.print(f"[bold red]错误: 素材文件未找到: {spec.workbook_path}[/bold red]")
        return

    workbook_data = parse_workbook(spec.workbook_path)
    payloads = allocator.allocate(spec, workbook_data)

    total_msgs = sum(len(p.to_chat_messages()) for p in payloads)

    table = Table(title="📋 分发清单预览")
    table.add_column("平台", style="cyan")
    table.add_column("篇数", justify="right")
    table.add_column("序号范围")
    table.add_column("首篇标题预览", style="green")

    for p in payloads:
        first_title = p.items[0].title if p.items[0].title else p.items[0].body[:20]
        table.add_row(
            p.platform,
            str(len(p.items)),
            f"{p.items[0].seq} ~ {p.items[-1].seq}",
            first_title
        )
    console.print(table)

    # 确定发送器
    sender = DryRunSender() if dry_run else WeChatWin32Sender()
    mode_text = "[yellow]本地模拟 (Dry Run)[/yellow]" if dry_run else "[green]物理微信注入[/green]"
    console.print(f"\n▶ 正在启动发送器: {mode_text} ➡️ 目标: [bold cyan]【{target}】[/bold cyan]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("分发进度", total=total_msgs)

        def on_prog(curr, total, desc):
            progress.update(task, completed=curr, description=desc)

        sender.dispatch(payloads, target_chat=target, on_progress=on_prog)

    # 发送成功后登记 SQLite 台账
    for p in payloads:
        for it in p.items:
            ledger.record_dispatch(
                content_hash=it.content_hash,
                campaign=spec.campaign,
                owner=spec.owner,
                platform=p.platform,
                seq=it.seq,
                title=it.title,
                source_workbook=spec.workbook_path,
                source_sheet=it.source_sheet or "",
                source_row=it.source_row or 0
            )

    console.print(f"[bold green]🎉 分发全部完成并已登记台账！共处理 {len(payloads)} 个平台板块，累计 {total_msgs} 条微信消息。[/bold green]")


def handle_capacity(args):
    """库存余量报告"""
    workbook_path = args.workbook
    if not os.path.exists(workbook_path):
        console.print(f"[red]文件不存在: {workbook_path}[/red]")
        return

    ledger = DispatchLedger()
    allocator = CopyAllocator(ledger)
    data = parse_workbook(workbook_path)
    report = allocator.get_capacity_report(data, campaign=args.campaign)

    table = Table(title=f"📊 素材池库存盘点 ({os.path.basename(workbook_path)})")
    table.add_column("Sheet 工作表", style="cyan")
    table.add_column("总容量", justify="right")
    table.add_column("已分发", justify="right", style="red")
    table.add_column("可用未分配", justify="right", style="green")

    for s_name, st in report["sheets"].items():
        table.add_row(s_name, str(st["total"]), str(st["used"]), str(st["available"]))

    table.add_section()
    table.add_row(
        "[bold]合计[/bold]",
        f"[bold]{report['total_pool']}[/bold]",
        f"[bold red]{report['total_dispatched']}[/bold red]",
        f"[bold green]{report['total_available']}[/bold green]"
    )
    console.print(table)


def handle_diff(args):
    """比对两份工作簿"""
    res = WorkbookDiff.compare(args.file_a, args.file_b)
    table = Table(title="🔍 工作簿版本差异深度比对")
    table.add_column("工作表")
    table.add_column("版本 A 行数", justify="right")
    table.add_column("版本 B 行数", justify="right")
    table.add_column("内容完全重合", justify="right")
    table.add_column("版本 B 新增", justify="right", style="green")
    table.add_column("状态判定")

    for s_name, d in res["sheet_diffs"].items():
        status = "[green]完全一致[/green]" if d["is_identical"] else f"[yellow]新增 {d['added_count']} 篇[/yellow]"
        table.add_row(
            s_name,
            str(d["count_a"]),
            str(d["count_b"]),
            str(d["common_count"]),
            str(d["added_count"]),
            status
        )
    console.print(table)
    console.print(f"• 全局重合度 (B 包含于 A): [bold cyan]{res['overlap_ratio_b_to_a']*100:.1f}%[/bold cyan]")
    if res["is_completely_identical"]:
        console.print("[bold green]结论: 两份文件文案内容 100% 完全相同，无需重复导入。[/bold green]")


def handle_stats(args):
    """台账统计"""
    ledger = DispatchLedger()
    st = ledger.get_stats()
    console.print(Panel(
        f"• 累计分发记录数: [bold cyan]{st['total_dispatches']}[/bold cyan] 次\n"
        f"• 独立去重文案数: [bold green]{st['unique_copies']}[/bold green] 篇\n"
        f"• 涉及执行责任人: [bold cyan]{st['total_owners']}[/bold cyan] 人 ({', '.join(st['by_owner'].keys())})\n"
        f"• 覆盖发布平台数: [bold cyan]{st['total_platforms']}[/bold cyan] 个 ({', '.join(st['by_platform'].keys())})",
        title="📈 SQLite 台账全景统计"
    ))


def handle_init_mock(args):
    """生成脱敏的合成测试数据集"""
    from examples.generate_mock_data import generate_synthetic_workbook
    out_path = args.output or os.path.join("examples", "sample_pool.xlsx")
    generate_synthetic_workbook(out_path)
    console.print(f"[bold green]✅ 已成功生成脱敏示例素材库: {out_path}[/bold green]")


def main():
    parser = argparse.ArgumentParser(description="Content Dispatch Agent (cda) - 营销文案智能调度与桌面分发智能体")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # run
    p_run = subparsers.add_parser("run", help="运行 YAML 任务配置")
    p_run.add_argument("config", help="YAML 配置文件路径")
    p_run.add_argument("--dry-run", action="store_true", help="本地导出测试，不向微信发送")
    p_run.add_argument("--target", default=None, help="目标会话名称，默认：文件传输助手")

    # ask
    p_ask = subparsers.add_parser("ask", help="自然语言指令驱动任务")
    p_ask.add_argument("prompt", help="中文分发指令，如：'恒恒 10人 头条+小红书 序号41-50'")
    p_ask.add_argument("--workbook", default=os.path.join("examples", "sample_pool.xlsx"), help="素材库路径")
    p_ask.add_argument("--dry-run", action="store_true", help="本地导出测试")
    p_ask.add_argument("--yes", "-y", action="store_true", help="跳过确认直接执行")
    p_ask.add_argument("--target", default=None, help="目标会话名称")

    # capacity
    p_cap = subparsers.add_parser("capacity", help="查询素材池余量")
    p_cap.add_argument("--workbook", default=os.path.join("examples", "sample_pool.xlsx"), help="素材库路径")
    p_cap.add_argument("--campaign", default="q9m_art", help="所属战役名")

    # diff
    p_diff = subparsers.add_parser("diff", help="比对两版素材工作簿")
    p_diff.add_argument("file_a", help="版本 A 路径")
    p_diff.add_argument("file_b", help="版本 B 路径")

    # stats
    subparsers.add_parser("stats", help="查看 SQLite 台账统计")

    # init-mock
    p_mock = subparsers.add_parser("init-mock", help="生成脱敏合成示例素材库")
    p_mock.add_argument("--output", default=None, help="输出文件路径")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    cmd_map = {
        "run": handle_run,
        "ask": handle_ask,
        "capacity": handle_capacity,
        "diff": handle_diff,
        "stats": handle_stats,
        "init-mock": handle_init_mock
    }
    cmd_map[args.command](args)


if __name__ == "__main__":
    main()
