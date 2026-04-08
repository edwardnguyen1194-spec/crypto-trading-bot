"""
Terminal Dashboard
Rich-powered real-time display of bot performance.
"""

import time
import os
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich import box


console = Console()


def format_pnl(value: float) -> Text:
    """Format PnL with color."""
    if value > 0:
        return Text(f"+${value:.2f}", style="bold green")
    elif value < 0:
        return Text(f"-${abs(value):.2f}", style="bold red")
    return Text(f"${value:.2f}", style="dim")


def format_pct(value: float) -> Text:
    """Format percentage with color."""
    if value > 0:
        return Text(f"+{value:.1f}%", style="green")
    elif value < 0:
        return Text(f"{value:.1f}%", style="red")
    return Text(f"{value:.1f}%", style="dim")


def format_wr(value: float) -> Text:
    """Format win rate with color coding."""
    if value >= 80:
        return Text(f"{value:.1f}%", style="bold green")
    elif value >= 60:
        return Text(f"{value:.1f}%", style="yellow")
    elif value > 0:
        return Text(f"{value:.1f}%", style="red")
    return Text("--", style="dim")


def create_bot_table(all_stats: list) -> Table:
    """Create the main bot comparison table."""
    table = Table(
        title="Bot Performance Comparison",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        title_style="bold white",
    )

    table.add_column("Bot", style="bold", width=10)
    table.add_column("Leverage", justify="center", width=8)
    table.add_column("Balance", justify="right", width=12)
    table.add_column("P&L", justify="right", width=12)
    table.add_column("P&L %", justify="right", width=8)
    table.add_column("Trades", justify="center", width=7)
    table.add_column("W/L", justify="center", width=7)
    table.add_column("Win Rate", justify="center", width=9)
    table.add_column("Open", justify="center", width=5)
    table.add_column("Status", justify="center", width=8)

    for stats in all_stats:
        status = "PAUSED" if stats.get("paused") else "ACTIVE"
        status_style = "red" if stats.get("paused") else "green"

        table.add_row(
            stats.get("bot_name", "?"),
            f"{stats.get('leverage', '?')}x",
            f"${stats.get('allocation', 0):.2f}",
            format_pnl(stats.get("pnl_total", 0)),
            format_pct(stats.get("pnl_pct", 0)),
            str(stats.get("total_trades", 0)),
            f"{stats.get('wins', 0)}/{stats.get('losses', 0)}",
            format_wr(stats.get("win_rate", 0)),
            str(stats.get("open_positions", 0)),
            Text(status, style=status_style),
        )

    return table


def create_trade_log(results: list, max_trades: int = 10) -> Table:
    """Create recent trades log table."""
    table = Table(
        title="Recent Trades",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold",
    )

    table.add_column("Bot", width=8)
    table.add_column("Symbol", width=10)
    table.add_column("Dir", width=5)
    table.add_column("Entry", justify="right", width=12)
    table.add_column("Exit", justify="right", width=12)
    table.add_column("P&L", justify="right", width=10)
    table.add_column("Reason", width=12)

    recent = []
    for r in results:
        for t in r.get("closed_trades", []):
            recent.append({**t, "bot": r.get("bot", "?")})

    recent.sort(key=lambda x: x.get("duration", 0), reverse=True)
    recent = recent[:max_trades]

    for t in recent:
        direction_style = "green" if t.get("direction") == "LONG" else "red"
        table.add_row(
            t.get("bot", "?")[:8],
            t.get("symbol", "?"),
            Text(t.get("direction", "?")[:5], style=direction_style),
            f"${t.get('entry_price', 0):.2f}",
            f"${t.get('exit_price', 0):.2f}",
            format_pnl(t.get("pnl", 0)),
            t.get("reason", "?"),
        )

    if not recent:
        table.add_row("--", "--", "--", "--", "--", "--", "--")

    return table


def create_symbol_breakdown(all_stats: list) -> Table:
    """Create per-symbol performance breakdown."""
    table = Table(
        title="Performance by Symbol",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold",
    )

    table.add_column("Symbol", width=10)
    table.add_column("Trades", justify="center", width=7)
    table.add_column("Win Rate", justify="center", width=9)
    table.add_column("P&L", justify="right", width=10)

    # Aggregate across all bots
    combined = {}
    for stats in all_stats:
        by_sym = stats.get("trades_by_symbol", {})
        for sym, data in by_sym.items():
            if sym not in combined:
                combined[sym] = {"total": 0, "wins": 0, "pnl": 0}
            combined[sym]["total"] += data.get("total", 0)
            combined[sym]["wins"] += data.get("wins", 0)
            combined[sym]["pnl"] += data.get("pnl", 0)

    for sym in config.TRADING_PAIRS:
        data = combined.get(sym, {"total": 0, "wins": 0, "pnl": 0})
        wr = (data["wins"] / data["total"] * 100) if data["total"] > 0 else 0
        table.add_row(
            sym,
            str(data["total"]),
            format_wr(wr),
            format_pnl(data["pnl"]),
        )

    return table


def print_dashboard(results: list, cycle: int, start_time: float, mode: str):
    """Print a single frame of the dashboard."""
    os.system("clear" if os.name != "nt" else "cls")

    uptime = time.time() - start_time
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)

    # Header
    header = Text()
    header.append("  CRYPTO TRADING BOT  ", style="bold white on blue")
    header.append(f"  Mode: ", style="dim")
    mode_style = "green" if mode == "paper" else "red bold"
    header.append(f"{mode.upper()}", style=mode_style)
    header.append(f"  |  Cycle: {cycle}", style="dim")
    header.append(f"  |  Uptime: {hours}h {minutes}m", style="dim")
    header.append(f"  |  Pairs: {len(config.TRADING_PAIRS)}", style="dim")

    console.print(Panel(header, box=box.DOUBLE))

    # Extract stats from results
    all_stats = [r.get("stats", r) for r in results]

    # Main table
    console.print(create_bot_table(all_stats))
    console.print()

    # Recent trades and symbol breakdown side by side
    console.print(create_trade_log(results))
    console.print()
    console.print(create_symbol_breakdown(all_stats))

    # Footer
    total_pnl = sum(s.get("pnl_total", 0) for s in all_stats)
    total_trades = sum(s.get("total_trades", 0) for s in all_stats)
    total_wins = sum(s.get("wins", 0) for s in all_stats)
    overall_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0

    footer = Text()
    footer.append("\n  TOTALS  ", style="bold")
    footer.append(f"  P&L: ", style="dim")
    footer.append(format_pnl(total_pnl))
    footer.append(f"  |  Trades: {total_trades}", style="dim")
    footer.append(f"  |  Overall WR: ", style="dim")
    footer.append(format_wr(overall_wr))
    footer.append(f"\n  Press Ctrl+C to stop", style="dim italic")

    console.print(footer)


# Need to import config at module level for symbol list
import config
