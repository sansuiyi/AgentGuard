"""Self-contained HTML report generator (no external assets)."""

from __future__ import annotations

import html
from pathlib import Path

_BADGE_COLORS = {
    "PASS": "#16a34a",
    "REVIEW": "#d97706",
    "BLOCK": "#dc2626",
    "ERROR": "#6b7280",
}

_STATUS_COLORS = {
    "pass": "#16a34a",
    "fail": "#dc2626",
    "error": "#6b7280",
}


def _badge(text: str, color: str) -> str:
    style = (
        f"background:{color};color:#fff;padding:2px 10px;"
        "border-radius:12px;font-size:12px;font-weight:600"
    )
    return f'<span style="{style}">{html.escape(text)}</span>'


def render_html(report: dict) -> str:
    decision = report["decision"]
    aggregate = report["aggregate"]
    decision_value = decision["decision"]
    badge_color = _BADGE_COLORS.get(decision_value, "#6b7280")

    rows: list[str] = []
    for rec in report["case_records"]:
        base = rec["base"]["status"]
        candidate = rec["candidate"]["status"]
        regressed = rec["pairwise"]["regressed"]
        regressed_flag = "REGRESSION" if regressed else ""
        rows.append(
            "<tr>"
            f"<td><code>{html.escape(rec['case_id'])}</code></td>"
            f"<td>{html.escape(rec['title'])}</td>"
            f"<td>{html.escape(rec['category'])}</td>"
            f"<td>{html.escape(rec['priority'])}</td>"
            f"<td>{_badge(base, _STATUS_COLORS.get(base, '#6b7280'))}</td>"
            f"<td>{_badge(candidate, _STATUS_COLORS.get(candidate, '#6b7280'))}</td>"
            f"<td>{html.escape(regressed_flag)}</td>"
            "</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AgentGuard 行为回归报告 — {html.escape(report['run_id'])}</title>
<style>
body {{
    font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
    margin: 0;
    background: #f5f6f8;
    color: #1f2937;
}}
.container {{ max-width: 1080px; margin: 0 auto; padding: 24px; }}
h1 {{ font-size: 22px; margin: 0 0 4px; }}
.sub {{ color: #6b7280; font-size: 13px; margin-bottom: 20px; }}
.cards {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }}
.card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 16px 20px; min-width: 160px; }}
.card .label {{ font-size: 12px; color: #6b7280; }}
.card .value {{ font-size: 26px; font-weight: 700; margin-top: 4px; }}
.reason {{
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 14px 20px;
    margin-bottom: 24px;
    font-size: 14px;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    overflow: hidden;
}}
th, td {{ text-align: left; padding: 10px 14px; border-bottom: 1px solid #eef0f3; font-size: 13px; }}
th {{ background: #f9fafb; color: #374151; font-weight: 600; }}
code {{ background: #f3f4f6; padding: 1px 6px; border-radius: 4px; }}
</style>
</head>
<body>
<div class="container">
<h1>AgentGuard 行为回归报告</h1>
<div class="sub">
Run ID: <code>{html.escape(report['run_id'])}</code>
· 生成时间 {html.escape(decision.get('timestamp', ''))}
</div>

<div class="cards">
<div class="card"><div class="label">最终决策</div><div class="value">{_badge(decision_value, badge_color)}</div></div>
<div class="card"><div class="label">用例总数</div><div class="value">{aggregate['total']}</div></div>
<div class="card"><div class="label">Candidate 通过</div><div class="value">{aggregate['candidate_passed']}</div></div>
<div class="card"><div class="label">回归数</div><div class="value">{len(aggregate['regressed'])}</div></div>
</div>

<div class="reason"><strong>决策理由：</strong>{html.escape(decision.get('decision_reason', ''))}</div>

<table>
<thead><tr><th>用例</th><th>标题</th><th>能力</th><th>优先级</th><th>Base</th><th>Candidate</th><th>回归</th></tr></thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</div>
</body>
</html>"""


def write_html(report: dict, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_html(report), encoding="utf-8")
    return p
