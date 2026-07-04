#!/usr/bin/env python3
"""Generate a standalone HTML dashboard for model results."""

from __future__ import annotations

import argparse
import csv
import html
import json
from collections import defaultdict
from pathlib import Path


DEFAULT_PANEL_SUMMARY = "data/model/panel_summary.json"
DEFAULT_METRICS = "reports/metrics.json"
DEFAULT_IMPORTANCE = "reports/feature_importance.csv"
DEFAULT_PREDICTIONS = "reports/predictions_sample.csv"
DEFAULT_PANEL = "data/model/business_month_panel.csv"
DEFAULT_OUTPUT = "reports/dashboard.html"


def read_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_csv(path: str):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def metric_card(title: str, value: str, note: str = "") -> str:
    return f"""
    <section class="metric">
      <div class="metric-title">{html.escape(title)}</div>
      <div class="metric-value">{html.escape(value)}</div>
      <div class="metric-note">{html.escape(note)}</div>
    </section>
    """


def bar_chart(rows, label_key: str, value_key: str, title: str, limit: int = 12) -> str:
    rows = rows[:limit]
    max_value = max((float(r[value_key]) for r in rows), default=1.0) or 1.0
    items = []
    for row in rows:
        label = row[label_key]
        value = float(row[value_key])
        pct = value / max_value * 100
        items.append(
            f"""
            <div class="bar-row">
              <div class="bar-label">{html.escape(label)}</div>
              <div class="bar-track"><div class="bar-fill" style="width:{pct:.2f}%"></div></div>
              <div class="bar-value">{value:.4f}</div>
            </div>
            """
        )
    return f"""
    <section class="panel">
      <h2>{html.escape(title)}</h2>
      <div class="bars">{''.join(items)}</div>
    </section>
    """


def metrics_table(metrics: dict) -> str:
    rows = []
    for split, values in metrics.items():
        if not values:
            continue
        rows.append(
            f"""
            <tr>
              <td>{html.escape(split)}</td>
              <td>{int(values['rows']):,}</td>
              <td>{values['model_mae']:.4f}</td>
              <td>{values['baseline_mae']:.4f}</td>
              <td>{values['model_rmse']:.4f}</td>
              <td>{values['baseline_rmse']:.4f}</td>
              <td>{values['model_rmsle']:.4f}</td>
              <td>{values['baseline_rmsle']:.4f}</td>
            </tr>
            """
        )
    return f"""
    <section class="panel">
      <h2>模型误差对比</h2>
      <table>
        <thead>
          <tr>
            <th>数据集</th><th>样本数</th><th>模型 MAE</th><th>上月基线 MAE</th>
            <th>模型 RMSE</th><th>上月基线 RMSE</th><th>模型 RMSLE</th><th>上月基线 RMSLE</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    """


def prediction_table(rows, limit: int = 20) -> str:
    body = []
    for row in rows[:limit]:
        body.append(
            f"""
            <tr>
              <td>{html.escape(row['business_id'])}</td>
              <td>{html.escape(row['month'])}</td>
              <td>{html.escape(row['target_month'])}</td>
              <td>{float(row['actual']):.0f}</td>
              <td>{float(row['prediction']):.2f}</td>
              <td>{float(row['baseline']):.0f}</td>
            </tr>
            """
        )
    return f"""
    <section class="panel">
      <h2>测试集预测样例</h2>
      <table>
        <thead><tr><th>business_id</th><th>特征月</th><th>标签月</th><th>真实值</th><th>模型预测</th><th>上月基线</th></tr></thead>
        <tbody>{''.join(body)}</tbody>
      </table>
    </section>
    """


def split_summary(panel_path: str):
    splits = defaultdict(int)
    target_sum = defaultdict(float)
    monthly = defaultdict(float)
    with open(panel_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            split = row["split"]
            target = float(row["target_next_month_reviews"])
            splits[split] += 1
            target_sum[split] += target
            monthly[row["target_month"]] += target
    return splits, target_sum, sorted(monthly.items())


def line_chart(monthly, title: str, limit: int = 72) -> str:
    data = monthly[-limit:]
    if not data:
        return ""
    width, height = 900, 260
    pad_l, pad_r, pad_t, pad_b = 48, 20, 18, 38
    values = [v for _, v in data]
    max_v = max(values) or 1.0
    min_v = min(values)
    span = max(max_v - min_v, 1.0)
    points = []
    for i, (_, value) in enumerate(data):
        x = pad_l + i * (width - pad_l - pad_r) / max(len(data) - 1, 1)
        y = pad_t + (max_v - value) * (height - pad_t - pad_b) / span
        points.append((x, y))
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    labels = [
        f'<text x="{pad_l + i * (width - pad_l - pad_r) / max(len(data) - 1, 1):.1f}" y="{height-10}" text-anchor="middle">{m}</text>'
        for i, (m, _) in enumerate(data)
        if i % max(len(data) // 8, 1) == 0
    ]
    return f"""
    <section class="panel">
      <h2>{html.escape(title)}</h2>
      <svg viewBox="0 0 {width} {height}" class="line-chart" role="img">
        <polyline points="{path}" fill="none" stroke="#1f7a8c" stroke-width="3" />
        <line x1="{pad_l}" y1="{height-pad_b}" x2="{width-pad_r}" y2="{height-pad_b}" stroke="#ccd5d9" />
        <line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height-pad_b}" stroke="#ccd5d9" />
        {''.join(labels)}
      </svg>
    </section>
    """


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel-summary", default=DEFAULT_PANEL_SUMMARY)
    parser.add_argument("--metrics", default=DEFAULT_METRICS)
    parser.add_argument("--importance", default=DEFAULT_IMPORTANCE)
    parser.add_argument("--predictions", default=DEFAULT_PREDICTIONS)
    parser.add_argument("--panel", default=DEFAULT_PANEL)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    summary = read_json(args.panel_summary)
    metrics = read_json(args.metrics)
    importance = read_csv(args.importance)
    predictions = read_csv(args.predictions)
    splits, target_sum, monthly = split_summary(args.panel)

    test_metrics = metrics.get("test", {})
    cards = [
        metric_card("面板样本数", f"{summary['rows']:,}", "商家-月份样本"),
        metric_card("训练集", f"{splits.get('train', 0):,}", "按标签月份切分"),
        metric_card("验证集", f"{splits.get('valid', 0):,}", "2021-01 至 2021-06"),
        metric_card("测试集", f"{splits.get('test', 0):,}", "2021-07 至 2021-12"),
        metric_card("测试 MAE", f"{test_metrics.get('model_mae', 0):.4f}", "log-linear model"),
        metric_card("测试 RMSLE", f"{test_metrics.get('model_rmsle', 0):.4f}", "越低越好"),
    ]

    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Yelp 商家月度热度预测</title>
  <style>
    body {{ margin:0; font-family: Arial, "Microsoft YaHei", sans-serif; background:#f5f7f8; color:#1f2933; }}
    header {{ padding:28px 36px; background:#0f3d4a; color:#fff; }}
    h1 {{ margin:0 0 8px; font-size:28px; }}
    header p {{ margin:0; color:#d8e6ea; }}
    main {{ padding:24px 36px 42px; }}
    .metrics {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:14px; margin-bottom:18px; }}
    .metric, .panel {{ background:#fff; border:1px solid #d8e0e4; border-radius:8px; box-shadow:0 1px 2px rgba(15,61,74,.05); }}
    .metric {{ padding:16px; }}
    .metric-title {{ color:#60717a; font-size:13px; }}
    .metric-value {{ font-size:26px; font-weight:700; margin-top:8px; }}
    .metric-note {{ color:#7a8a91; font-size:12px; margin-top:6px; }}
    .panel {{ padding:18px; margin-top:18px; overflow:auto; }}
    h2 {{ font-size:18px; margin:0 0 14px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ border-bottom:1px solid #e3e8eb; padding:9px 10px; text-align:left; white-space:nowrap; }}
    th {{ background:#edf3f5; color:#344955; }}
    .bar-row {{ display:grid; grid-template-columns: 290px 1fr 90px; gap:10px; align-items:center; margin:9px 0; }}
    .bar-label {{ font-size:13px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .bar-track {{ height:12px; background:#e6edf0; border-radius:999px; overflow:hidden; }}
    .bar-fill {{ height:100%; background:#1f7a8c; }}
    .bar-value {{ font-size:12px; color:#52636b; text-align:right; }}
    .line-chart text {{ font-size:11px; fill:#60717a; }}
    .note {{ color:#52636b; line-height:1.7; }}
  </style>
</head>
<body>
  <header>
    <h1>Yelp 商家未来月度热度预测</h1>
    <p>目标：用商家-月份状态预测下一月新增评论数量。当前模型：标准库 log-linear baseline。</p>
  </header>
  <main>
    <div class="metrics">{''.join(cards)}</div>
    {metrics_table(metrics)}
    {line_chart(monthly, "全量标签月份新增评论总量走势")}
    {bar_chart(importance, "feature", "importance", "特征重要性 Top 12")}
    {prediction_table(predictions)}
    <section class="panel">
      <h2>建模口径说明</h2>
      <p class="note">
        人性指标本身属于用户，不直接属于商家。本模型先通过 <code>review.user_id</code> 和
        <code>review.business_id</code> 将用户行为映射到商家，再在商家-月份粒度上聚合为客群画像。
        因变量为下一月新增评论数量，因此它是商家未来月度热度的代理标签。
      </p>
    </section>
  </main>
</body>
</html>
"""
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(html_text, encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
