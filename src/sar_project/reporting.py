"""Report and chart generation for SAR project outputs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping, Optional

import markdown as markdown_lib
import pandas as pd

from sar_project.metrics import max_drawdown_series


def generate_report(
    processed_root: Path,
    docs_root: Path,
    offline: bool = False,
    coverage: Optional[Mapping[str, object]] = None,
) -> None:
    """Generate charts, Markdown report, and PDF from processed outputs."""

    docs_root.mkdir(parents=True, exist_ok=True)
    figures = docs_root / "figures"
    figures.mkdir(parents=True, exist_ok=True)

    portfolio = pd.read_csv(processed_root / "portfolio_test.csv", dtype={"trade_date": str})
    trades = _read_csv_or_empty(processed_root / "trades_test.csv")
    metrics = json.loads((processed_root / "metrics_test.json").read_text(encoding="utf-8"))
    train_metrics = json.loads((processed_root / "metrics_train.json").read_text(encoding="utf-8"))
    best_params = json.loads((processed_root / "best_params.json").read_text(encoding="utf-8"))
    optimization = pd.read_csv(processed_root / "optimization_results.csv")

    _plot_nav(portfolio, figures / "nav_curve.png")
    _plot_drawdown(portfolio, figures / "drawdown.png")
    _plot_parameter_heatmap(optimization, figures / "parameter_heatmap.png")
    _plot_monthly_returns(portfolio, figures / "monthly_returns.png")
    _plot_trade_returns(trades, figures / "trade_returns.png")
    _write_metrics_table(metrics, train_metrics, docs_root / "summary_metrics.csv")

    comparison = _benchmark_comparison(portfolio)
    report_md = _build_markdown(metrics, train_metrics, best_params, comparison, offline, coverage or {})
    markdown_path = docs_root / "sar_project_report.md"
    markdown_path.write_text(report_md, encoding="utf-8")
    _write_pdf(markdown_path, docs_root / "sar_project_report.pdf")


def _plot_nav(portfolio: pd.DataFrame, path: Path) -> None:
    import matplotlib.pyplot as plt

    x = pd.to_datetime(portfolio["trade_date"])
    plt.figure(figsize=(10, 5))
    plt.plot(x, portfolio["portfolio_value"], label="SAR strategy", linewidth=2)
    if "benchmark_value" in portfolio:
        plt.plot(x, portfolio["benchmark_value"], label="CSI 300", linewidth=1.5)
    if "equal_weight_value" in portfolio:
        plt.plot(x, portfolio["equal_weight_value"], label="Dynamic top-50 equal weight", linewidth=1.5)
    plt.title("Historical validation net value comparison")
    plt.xlabel("Date")
    plt.ylabel("Portfolio value")
    plt.legend()
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def _read_csv_or_empty(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path) if path.exists() else pd.DataFrame()
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _plot_drawdown(portfolio: pd.DataFrame, path: Path) -> None:
    import matplotlib.pyplot as plt

    x = pd.to_datetime(portfolio["trade_date"])
    plt.figure(figsize=(10, 4))
    plt.plot(x, max_drawdown_series(portfolio["portfolio_value"]), label="Strategy drawdown", color="#b91c1c")
    plt.title("Historical validation drawdown")
    plt.xlabel("Date")
    plt.ylabel("Drawdown")
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def _plot_parameter_heatmap(optimization: pd.DataFrame, path: Path) -> None:
    import matplotlib.pyplot as plt

    pivot = optimization.pivot_table(index="acceleration", columns="maximum", values="sharpe_ratio", aggfunc="mean")
    plt.figure(figsize=(6, 4))
    image = plt.imshow(pivot.values, aspect="auto", cmap="RdYlGn")
    plt.xticks(range(len(pivot.columns)), [str(value) for value in pivot.columns])
    plt.yticks(range(len(pivot.index)), [str(value) for value in pivot.index])
    plt.colorbar(image, label="Sample-in Sharpe")
    plt.xlabel("SAR maximum")
    plt.ylabel("SAR acceleration")
    plt.title("Sample-in parameter heatmap")
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def _plot_monthly_returns(portfolio: pd.DataFrame, path: Path) -> None:
    import matplotlib.pyplot as plt

    frame = portfolio.copy()
    frame["date"] = pd.to_datetime(frame["trade_date"])
    monthly = frame.set_index("date")["portfolio_value"].resample("ME").last().pct_change().dropna()
    plt.figure(figsize=(10, 4))
    colors = ["#166534" if value >= 0 else "#b91c1c" for value in monthly]
    plt.bar(monthly.index, monthly.values, width=20, color=colors)
    plt.title("Historical validation monthly returns")
    plt.xlabel("Month")
    plt.ylabel("Return")
    plt.grid(axis="y", alpha=0.25)
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def _plot_trade_returns(trades: pd.DataFrame, path: Path) -> None:
    import matplotlib.pyplot as plt

    sells = trades[trades.get("action", pd.Series(dtype=str)) == "sell"]
    returns = sells.get("return_pct", pd.Series(dtype=float)).dropna().astype(float)
    plt.figure(figsize=(8, 4))
    if len(returns):
        plt.hist(returns, bins=20, color="#2563eb", alpha=0.8)
        plt.axvline(0, color="#111827", linestyle="--", linewidth=1)
    plt.title("Trade return distribution")
    plt.xlabel("Round-trip return")
    plt.ylabel("Count")
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def _write_metrics_table(test_metrics: Mapping[str, float], train_metrics: Mapping[str, float], path: Path) -> None:
    rows = []
    for key in sorted(set(train_metrics) | set(test_metrics)):
        rows.append(
            {
                "metric": key,
                "sample_in": train_metrics.get(key),
                "historical_validation": test_metrics.get(key),
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def _benchmark_comparison(portfolio: pd.DataFrame) -> Mapping[str, float]:
    result = {}
    for column, key in [
        ("portfolio_value", "strategy_total_return"),
        ("benchmark_value", "benchmark_total_return"),
        ("equal_weight_value", "equal_weight_total_return"),
    ]:
        if column in portfolio:
            values = portfolio[column].dropna().astype(float)
            result[key] = float(values.iloc[-1] / values.iloc[0] - 1) if len(values) and values.iloc[0] else 0.0
    return result


def _build_markdown(
    test_metrics: Mapping[str, float],
    train_metrics: Mapping[str, float],
    best_params: Mapping[str, float],
    comparison: Mapping[str, float],
    offline: bool,
    coverage: Mapping[str, object],
) -> str:
    data_note = "本报告使用离线示例数据生成，用于验证流水线。" if offline else "本报告使用 tinyshare/Tushare 接口下载的历史行情与指数成分数据生成。"
    coverage_note = ""
    if coverage:
        missing = coverage.get("missing_list") or []
        missing_text = ", ".join(missing) if missing else "无"
        coverage_note = (
            f"\n- 数据覆盖：历史前50联合股票 {coverage.get('expected_symbols', 0)} 只，"
            f"成功缓存 {coverage.get('downloaded_symbols', 0)} 只，"
            f"缺失 {coverage.get('missing_symbols', 0)} 只；缺失列表：{missing_text}。"
        )
    take_profit = float(best_params.get("take_profit", 0))
    take_profit_text = "不主动止盈" if take_profit >= 1 else f"{take_profit:.2%}"
    stop_loss = float(best_params.get("stop_loss", 0))
    stop_loss_text = "不主动止损" if stop_loss >= 1 else f"{stop_loss:.2%}"
    return f"""# SAR 抛物线趋势跟踪策略重做报告

## 项目摘要

本项目重做原本科 SAR 策略报告，重点展示数据获取、回测偏差修正、交易约束建模、样本内参数选择、历史验证和结果解释能力。{data_note}

## 原报告主要问题

- 样本外收益和夏普比率为硬编码结果，并非真实回测。
- 参数优化使用随机夏普，不能支持“最优参数稳定”的结论。
- 使用当前成分股回测历史，存在生存者偏差。
- 胜率混淆了正收益交易日比例和逐笔交易胜率。
- 未纳入 t+1 成交、交易成本、印花税、滑点、100 股约束和涨跌停限制。

## 数据与样本

- 区间：2016-01-01 至 2025-12-31。
- 股票池：每月沪深300历史权重前 50 只股票，并在每日使用最近可得成分。
- 样本内：2016-2020；历史验证：2021-2025。
- 基准：沪深300价格指数、动态前50等权毛收益组合。
{coverage_note}

## 策略规则

买入候选要求 `close_adj > SAR`、`volume_ratio` 高于阈值且 RSI 低于上限；卖出条件包括价格跌破 SAR、RSI 超买、止损、止盈或离开候选池。所有信号在 t 日收盘后确认，交易在 t+1 日开盘执行。

交易成本包括双边佣金 0.03%，单笔最低佣金 5 元，卖出印花税 0.10%，以及单边滑点 0.05%。

本版策略不允许通过长期空仓来制造超额收益。样本内参数选择先要求平均股票仓位、平均持仓数量和低仓位天数比例满足约束，再检查样本内收益、超额收益和最大回撤训练底线。排序时优先比较样本内累计超额收益、夏普、最大回撤和总收益，最后再比较平均持仓数量和换手率，避免用“持仓更多”替代样本内表现。

## 参数选择

样本内最优参数：

| 参数 | 数值 |
| --- | ---: |
| SAR acceleration | {best_params.get("acceleration", 0):.4f} |
| SAR maximum | {best_params.get("maximum", 0):.4f} |
| Volume threshold | {best_params.get("volume_threshold", 0):.4f} |
| RSI ceiling | {best_params.get("rsi_ceiling", 0):.2f} |
| Max positions | {best_params.get("max_positions", 0):.0f} |
| Rebalance interval | {best_params.get("rebalance_interval", 0):.0f} |
| Stop loss | {stop_loss_text} |
| Take profit | {take_profit_text} |

## 历史验证核心结果

| 指标 | 样本内 | 历史验证 |
| --- | ---: | ---: |
| 总收益率 | {train_metrics.get("total_return", 0):.2%} | {test_metrics.get("total_return", 0):.2%} |
| 年化收益率 | {train_metrics.get("annual_return", 0):.2%} | {test_metrics.get("annual_return", 0):.2%} |
| 年化波动率 | {train_metrics.get("annual_volatility", 0):.2%} | {test_metrics.get("annual_volatility", 0):.2%} |
| 夏普比率 | {train_metrics.get("sharpe_ratio", 0):.2f} | {test_metrics.get("sharpe_ratio", 0):.2f} |
| 最大回撤 | {train_metrics.get("max_drawdown", 0):.2%} | {test_metrics.get("max_drawdown", 0):.2%} |
| 沪深300累计收益率 | {train_metrics.get("benchmark_total_return", 0):.2%} | {test_metrics.get("benchmark_total_return", 0):.2%} |
| 累计超额收益率 | {train_metrics.get("excess_total_return", 0):.2%} | {test_metrics.get("excess_total_return", 0):.2%} |
| 平均股票仓位 | {train_metrics.get("average_exposure", 0):.2%} | {test_metrics.get("average_exposure", 0):.2%} |
| 低仓位天数比例 | {train_metrics.get("low_exposure_day_ratio", 0):.2%} | {test_metrics.get("low_exposure_day_ratio", 0):.2%} |
| 平均持仓数量 | {train_metrics.get("average_positions", 0):.2f} | {test_metrics.get("average_positions", 0):.2f} |
| 总换手率 | {train_metrics.get("turnover", 0):.2f} | {test_metrics.get("turnover", 0):.2f} |
| 逐笔交易胜率 | {train_metrics.get("trade_win_rate", 0):.2%} | {test_metrics.get("trade_win_rate", 0):.2%} |
| 交易股票数 | {train_metrics.get("unique_symbols_traded", 0):.0f} | {test_metrics.get("unique_symbols_traded", 0):.0f} |
| 单一股票成交额占比上限 | {train_metrics.get("top_symbol_trade_value_share", 0):.2%} | {test_metrics.get("top_symbol_trade_value_share", 0):.2%} |

历史验证累计收益对比：策略 {comparison.get("strategy_total_return", 0):.2%}，沪深300 {comparison.get("benchmark_total_return", 0):.2%}，动态前50等权毛收益组合 {comparison.get("equal_weight_total_return", 0):.2%}。本版策略在扣除交易成本后相对沪深300取得正累计超额，但绝对收益仍为负，不能被表述为稳定盈利策略。该结果属于课程级历史回测，不等同于可实盘收益承诺。

## 图表

![Net value](figures/nav_curve.png)

![Drawdown](figures/drawdown.png)

![Parameter heatmap](figures/parameter_heatmap.png)

![Monthly returns](figures/monthly_returns.png)

![Trade returns](figures/trade_returns.png)

## 审计附件

报告目录下的 `audit/` 提供可复核附件：

| 文件 | 用途 |
| --- | --- |
| `trade_ledger_sample_out.csv` | 历史验证区间全部成交与未成交阻断记录，附信号日 SAR、RSI、成交量比例和推断触发原因 |
| `round_trip_trades_sample_out.csv` | 历史验证区间买入与卖出配对后的完整交易回合 |
| `portfolio_sample_out.csv` | 历史验证区间每日组合净值、现金、持仓数量和基准净值 |
| `optimization_results_sample_in.csv` | 样本内全部参数组合真实回测结果 |
| `market_data_used.csv.gz` | 历史验证区间回测使用的行情、复权字段和信号字段 |
| `source_data_inventory.csv` | 本地缓存数据文件行数、日期范围和 SHA-256 |
| `raw_snapshot_manifest.csv` | 原始 tinyshare/Tushare 快照清单，不包含 token |
| `audit_manifest.csv` | 审计附件文件大小、生成时间和 SHA-256 |

这些附件用于复核报告核心数字和历史验证交易，不提交 `.env`、token 或原始大体量 API 响应。

## 结论与边界

本项目不能被表述为“成熟稳定盈利策略”或“可直接实盘部署系统”。更准确的表述是：使用 Python 完成了 A 股日频技术指标策略的数据获取、动态股票池构建、交易约束回测、样本内参数选择、历史验证和绩效分析。策略结果应作为课程级研究练习与实习能力展示，而非投资建议。

还需要说明：本次重做过程根据原报告问题和中间回测诊断调整了规则，因此 2021-2025 更适合称为历史验证区间或开发后回测，不应包装成完全盲测。若要进一步提高可信度，应在固定代码和参数后，使用 2026-07-01 之后的新数据做真正盲测。

## 简历可表述

可写：使用 Python 与 tinyshare/Tushare 构建 A 股 SAR 趋势跟踪回测框架，完成历史成分股股票池、复权行情处理、t+1 成交、交易成本、样本内参数选择、历史验证绩效评估和报告生成。

不建议写：独立开发稳定盈利量化策略、策略显著长期跑赢沪深300、完成可实盘交易系统。
"""


def _write_pdf(markdown_path: Path, pdf_path: Path) -> None:
    body = markdown_lib.markdown(markdown_path.read_text(encoding="utf-8"), extensions=["tables"])
    html = f"""
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: Arial, "PingFang SC", "Microsoft YaHei", sans-serif; line-height: 1.55; margin: 32px; }}
        h1, h2 {{ color: #111827; }}
        table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
        th, td {{ border: 1px solid #d1d5db; padding: 6px 8px; }}
        th {{ background: #f3f4f6; }}
        img {{ max-width: 100%; margin: 12px 0 20px; }}
      </style>
    </head>
    <body>{body}</body>
    </html>
    """
    if os.environ.get("SAR_USE_WEASYPRINT") != "1":
        _write_pdf_with_reportlab(markdown_path, pdf_path)
        return
    try:
        from weasyprint import HTML

        HTML(string=html, base_url=str(markdown_path.parent)).write_pdf(str(pdf_path))
    except Exception:
        _write_pdf_with_reportlab(markdown_path, pdf_path)


def _write_pdf_with_reportlab(markdown_path: Path, pdf_path: Path) -> None:
    """Fallback PDF writer that avoids WeasyPrint system-library requirements."""

    import html

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.pdfmetrics import registerFont
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    registerFont(UnicodeCIDFont("STSong-Light"))
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("SarNormal", parent=styles["Normal"], fontName="STSong-Light", fontSize=10.5, leading=15)
    h1 = ParagraphStyle("SarH1", parent=styles["Heading1"], fontName="STSong-Light", fontSize=18, leading=24, spaceAfter=12)
    h2 = ParagraphStyle("SarH2", parent=styles["Heading2"], fontName="STSong-Light", fontSize=14, leading=19, spaceBefore=10, spaceAfter=8)
    bullet = ParagraphStyle("SarBullet", parent=normal, leftIndent=14, firstLineIndent=-8)

    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, rightMargin=0.65 * inch, leftMargin=0.65 * inch)
    story = []
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("# "):
            story.append(Paragraph(html.escape(line[2:]), h1))
        elif line.startswith("## "):
            story.append(Paragraph(html.escape(line[3:]), h2))
        elif line.startswith("![") and "](" in line and line.endswith(")"):
            image_path = markdown_path.parent / line.split("](", 1)[1][:-1]
            if image_path.exists():
                story.append(Image(str(image_path), width=6.6 * inch, height=3.2 * inch, kind="proportional"))
                story.append(Spacer(1, 8))
        elif line.startswith("|"):
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            index -= 1
            rows = []
            for table_line in table_lines:
                cells = [cell.strip() for cell in table_line.strip("|").split("|")]
                if all(set(cell) <= {"-", ":", " "} for cell in cells):
                    continue
                rows.append([Paragraph(html.escape(cell), normal) for cell in cells])
            if rows:
                table = Table(rows, repeatRows=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                            ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ]
                    )
                )
                story.append(table)
                story.append(Spacer(1, 8))
        elif line.startswith("- "):
            story.append(Paragraph("- " + html.escape(line[2:]), bullet))
        else:
            story.append(Paragraph(html.escape(line), normal))
            story.append(Spacer(1, 5))
        index += 1

    doc.build(story)
