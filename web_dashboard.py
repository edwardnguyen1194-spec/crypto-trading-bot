"""
Web Dashboard - Check bot status from your phone
Reads combined_report.json and serves a mobile-friendly HTML page.
Runs alongside the trading bot on port 8080.
"""

import json
import os
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler


REPORT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "combined_report.json")


def load_report():
    try:
        with open(REPORT_PATH) as f:
            return json.load(f)
    except Exception:
        return None


def build_html():
    report = load_report()
    if not report:
        return "<html><body><h1>No data yet. Bot starting...</h1></body></html>"

    bots = report.get("bots", [])
    total_trades = sum(b.get("total_trades", 0) for b in bots)
    total_wins = sum(b.get("wins", 0) for b in bots)
    total_pnl = sum(b.get("pnl_total", 0) for b in bots)
    overall_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0
    uptime = report.get("uptime_hours", 0)

    tuner = report.get("auto_tuner", {})
    tuner_level = tuner.get("level_name", "Normal")

    wr_color = "#00ff88" if overall_wr >= 88 else "#ff4444" if overall_wr < 70 else "#ffaa00"
    pnl_color = "#00ff88" if total_pnl >= 0 else "#ff4444"

    bot_rows = ""
    for b in bots:
        wr = b.get("win_rate", 0)
        pnl = b.get("pnl_total", 0)
        wr_c = "#00ff88" if wr >= 88 else "#ff4444" if wr < 70 else "#ffaa00"
        pnl_c = "#00ff88" if pnl >= 0 else "#ff4444"
        bot_rows += f"""
        <tr>
            <td>{b.get('bot_name','?')}</td>
            <td>{b.get('leverage','?')}x</td>
            <td>${b.get('allocation',0):.2f}</td>
            <td style="color:{pnl_c}">{'+' if pnl>=0 else ''}${pnl:.2f}</td>
            <td>{b.get('total_trades',0)}</td>
            <td>{b.get('wins',0)}/{b.get('losses',0)}</td>
            <td style="color:{wr_c}">{wr:.1f}%</td>
            <td>{b.get('open_positions',0)}</td>
        </tr>"""

    # Symbol breakdown
    sym_rows = ""
    for b in bots:
        for sym, data in b.get("trades_by_symbol", {}).items():
            wr = data.get("win_rate", 0)
            sym_rows += f"""
            <tr>
                <td>{b.get('bot_name','?')}</td>
                <td>{sym}</td>
                <td>{data.get('total',0)}</td>
                <td>{wr:.1f}%</td>
                <td>${data.get('pnl',0):.2f}</td>
            </tr>"""

    saved = report.get("saved_at", 0)
    age = int(time.time() - saved) if saved else 0
    age_str = f"{age//60}m {age%60}s ago" if age < 3600 else f"{age//3600}h {(age%3600)//60}m ago"

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Crypto Bot</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ background:#0a0a1a; color:#e0e0e0; font-family:-apple-system,system-ui,sans-serif; padding:12px; }}
        .header {{ text-align:center; padding:16px 0; border-bottom:1px solid #333; margin-bottom:16px; }}
        .header h1 {{ font-size:20px; color:#fff; }}
        .header .mode {{ color:#00ff88; font-size:14px; margin-top:4px; }}
        .stats {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:16px; }}
        .stat {{ background:#1a1a2e; border-radius:10px; padding:14px; text-align:center; }}
        .stat .value {{ font-size:24px; font-weight:bold; margin-top:4px; }}
        .stat .label {{ font-size:11px; color:#888; text-transform:uppercase; }}
        table {{ width:100%; border-collapse:collapse; font-size:13px; margin-bottom:16px; }}
        th {{ background:#1a1a2e; padding:8px 6px; text-align:left; color:#888; font-size:11px; text-transform:uppercase; }}
        td {{ padding:8px 6px; border-bottom:1px solid #1a1a2e; }}
        .section {{ background:#111; border-radius:10px; padding:12px; margin-bottom:12px; }}
        .section h2 {{ font-size:14px; color:#888; margin-bottom:8px; }}
        .footer {{ text-align:center; color:#555; font-size:11px; padding:8px 0; }}
        .alert {{ background:#ff444433; border:1px solid #ff4444; border-radius:8px; padding:10px; text-align:center; margin-bottom:12px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>CRYPTO TRADING BOT</h1>
        <div class="mode">{report.get('mode','paper').upper()} MODE | Uptime: {uptime:.1f}h | Tuner: {tuner_level}</div>
    </div>

    {'<div class="alert">WR BELOW 88% TARGET</div>' if total_trades >= 10 and overall_wr < 88 else ''}

    <div class="stats">
        <div class="stat">
            <div class="label">Total P&L</div>
            <div class="value" style="color:{pnl_color}">{'+' if total_pnl>=0 else ''}${total_pnl:.2f}</div>
        </div>
        <div class="stat">
            <div class="label">Win Rate</div>
            <div class="value" style="color:{wr_color}">{overall_wr:.1f}%</div>
        </div>
        <div class="stat">
            <div class="label">Total Trades</div>
            <div class="value">{total_trades}</div>
        </div>
        <div class="stat">
            <div class="label">W / L</div>
            <div class="value">{total_wins} / {total_trades - total_wins}</div>
        </div>
    </div>

    <div class="section">
        <h2>Bot Performance</h2>
        <table>
            <tr><th>Bot</th><th>Lev</th><th>Bal</th><th>P&L</th><th>Trades</th><th>W/L</th><th>WR</th><th>Open</th></tr>
            {bot_rows}
        </table>
    </div>

    <div class="section">
        <h2>By Symbol</h2>
        <table>
            <tr><th>Bot</th><th>Symbol</th><th>Trades</th><th>WR</th><th>P&L</th></tr>
            {sym_rows if sym_rows else '<tr><td colspan="5" style="text-align:center;color:#555">No trades yet</td></tr>'}
        </table>
    </div>

    <div class="footer">
        Updated {age_str} | Auto-refreshes every 30s
    </div>
</body>
</html>"""
    return html


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(build_html().encode())

    def log_message(self, format, *args):
        pass  # Suppress log spam


def start_dashboard(port=8080):
    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    print(f"Dashboard running at http://localhost:{port}")
    print(f"On your phone (same WiFi): http://<your-mac-ip>:{port}")
    server.serve_forever()


if __name__ == "__main__":
    start_dashboard()
