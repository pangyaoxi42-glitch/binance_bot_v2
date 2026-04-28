"""PnL Inspector — 一键生成 Markdown 盈亏报表"""
import asyncio
import time
import sys
from core.database import get_db, close_db, get_all_trades, get_snapshots
from analytics.metrics import compute_metrics

EXIT_REASONS = {
    "TP_FINAL": "终极止盈",
    "TP_PARTIAL": "分批止盈",
    "SL": "止损出场",
    "TRAILING_SL": "追踪止损",
    "AI_VETO": "AI否决",
    "STALEMATE": "僵局迁移",
    "BEAR_MARKET": "下跌保护",
}

def _fmt_time(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "-"


def _fmt_pnl(v, pct=False):
    if v is None:
        return "-"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.2f}" if not pct else f"{sign}{v:.2%}"


async def generate_report(output_path: str = "data/pnl_report.md"):
    db = await get_db()
    trades = await get_all_trades()
    daily_snaps = await get_snapshots("daily")

    closed = [t for t in trades if t['status'] == 'CLOSED']
    open_t = [t for t in trades if t['status'] in ('OPEN', 'PARTIAL')]
    metrics = compute_metrics(closed, daily_snaps)

    lines = []
    lines.append("# Binance Bot V2 — 盈亏审计报告")
    lines.append(f"\n生成时间: {_fmt_time(time.time())}\n")

    # ── 总览 ──
    lines.append("## 核心指标")
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    lines.append(f"| 总交易笔数 | {metrics['total_trades']} |")
    lines.append(f"| 已平仓盈利 | {metrics['total_trades'] - sum(1 for t in closed if (t['net_pnl'] or 0) <= 0)} 笔 |")
    lines.append(f"| 已平仓亏损 | {sum(1 for t in closed if (t['net_pnl'] or 0) <= 0)} 笔 |")
    lines.append(f"| 胜率 | {metrics['win_rate']:.1%} |")
    lines.append(f"| 盈亏比 | {metrics['profit_factor']:.2f} |")
    lines.append(f"| 累计净盈亏 | ${_fmt_pnl(metrics['total_net_pnl'])} |")
    lines.append(f"| 夏普比率 | {metrics['sharpe_ratio']:.2f} |")
    lines.append(f"| 最大回撤 | {metrics['max_drawdown']:.1%} |")

    # ── 当前持仓 ──
    if open_t:
        lines.append("\n## 当前持仓")
        lines.append("| ID | 交易对 | 入场时间 | 入场价 | 数量 | 状态 |")
        lines.append("|----|--------|----------|--------|------|------|")
        for t in open_t:
            status = "分批止盈后" if t['status'] == 'PARTIAL' else "持仓中"
            lines.append(
                f"| {t['id']} | {t['symbol']} | {_fmt_time(t['entry_time'])} | "
                f"${t['entry_price']:.2f} | {t['entry_amount']:.6f} | {status} |"
            )

    # ── 已平仓明细 ──
    lines.append(f"\n## 已平仓交易 ({len(closed)}笔)")
    lines.append("| ID | 交易对 | 入场时间 | 出场时间 | 入场价 | 出场价 | 数量 | 手续费 | 净盈亏 | 盈亏% | 出场原因 |")
    lines.append("|----|--------|----------|----------|--------|--------|------|--------|--------|-------|----------|")

    total_fees = 0
    for t in closed:
        fee = (t['entry_fee'] or 0) + (t['exit_fee'] or 0)
        total_fees += fee
        reason = EXIT_REASONS.get(t.get('exit_reason', ''), t.get('exit_reason', '-'))
        lines.append(
            f"| {t['id']} | {t['symbol']} | {_fmt_time(t['entry_time'])} | {_fmt_time(t['exit_time'])} | "
            f"${t['entry_price']:.2f} | ${t['exit_price']:.2f} | {t['entry_amount']:.6f} | "
            f"${fee:.4f} | ${_fmt_pnl(t['net_pnl'])} | {_fmt_pnl(t['net_pnl_pct'], True)} | {reason} |"
        )

    lines.append(f"\n累计手续费: ${total_fees:.4f}")

    # ── 按交易对统计 ──
    lines.append("\n## 按交易对统计")
    lines.append("| 交易对 | 笔数 | 胜率 | 净盈亏 | 手续费 |")
    lines.append("|--------|------|------|--------|--------|")

    by_symbol = {}
    for t in closed:
        s = t['symbol']
        if s not in by_symbol:
            by_symbol[s] = {"count": 0, "wins": 0, "pnl": 0, "fee": 0}
        by_symbol[s]["count"] += 1
        by_symbol[s]["wins"] += 1 if (t['net_pnl'] or 0) > 0 else 0
        by_symbol[s]["pnl"] += (t['net_pnl'] or 0)
        by_symbol[s]["fee"] += (t['entry_fee'] or 0) + (t['exit_fee'] or 0)

    for sym, d in sorted(by_symbol.items(), key=lambda x: x[1]['pnl'], reverse=True):
        wr = d['wins'] / d['count'] if d['count'] else 0
        lines.append(f"| {sym} | {d['count']} | {wr:.1%} | ${_fmt_pnl(d['pnl'])} | ${d['fee']:.4f} |")

    # ── 资产变化趋势 ──
    if daily_snaps:
        lines.append(f"\n## 每日资产变化 ({len(daily_snaps)}天)")
        lines.append("| 日期 | 总权益 | Sharpe | MDD | 胜率 | 盈亏比 |")
        lines.append("|------|--------|--------|-----|------|--------|")
        for s in daily_snaps[-30:]:
            ts = _fmt_time(s['timestamp'])[:10]
            lines.append(
                f"| {ts} | ${s['total_equity']:,.0f} | {s['sharpe_ratio'] or 0:.2f} | "
                f"{s['max_drawdown'] or 0:.1%} | {s['win_rate'] or 0:.1%} | {s['profit_factor'] or 0:.2f} |"
            )

    lines.append(f"\n---\n*报告由 pnl_inspector.py 自动生成*")

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"报表已生成 → {output_path}")
    print(f"  总交易: {metrics['total_trades']} | 胜率: {metrics['win_rate']:.1%} | 累计PnL: ${metrics['total_net_pnl']:+,.2f}")
    print(f"  Sharpe: {metrics['sharpe_ratio']:.2f} | MDD: {metrics['max_drawdown']:.1%} | 盈亏比: {metrics['profit_factor']:.2f}")

    await close_db()


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "data/pnl_report.md"
    asyncio.run(generate_report(output))