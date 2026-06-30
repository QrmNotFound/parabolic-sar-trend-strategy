# Parabolic SAR Trend Strategy

独立的 A 股 Parabolic SAR 趋势跟踪回测项目。

本仓库仅包含 SAR 策略相关代码、测试、报告和运行配置，不包含原“科研论文”项目中的其他研究脚手架。

## Scope

- 使用 Parabolic SAR 生成趋势信号。
- 使用动态沪深300历史权重前50股票池。
- 使用 t+1 开盘成交、交易成本和 A 股交易约束。
- 将 2021-2025 年样本外表现与沪深300基准比较。
- 输出可复现的回测指标、图表和项目报告。

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
./scripts/run_checks.sh
```

## Commands

离线夹具验证：

```bash
PYTHONPATH=src python3 -m sar_project.pipeline all --offline-ok
```

真实数据流水线：

```bash
PYTHONPATH=src python3 -m sar_project.pipeline download
PYTHONPATH=src python3 -m sar_project.pipeline run
PYTHONPATH=src python3 -m sar_project.pipeline report
PYTHONPATH=src python3 -m sar_project.pipeline all
```

真实数据需要在本地 `.env` 或环境变量中设置：

```bash
TINYSHARE_TOKEN=...
```

不要把 token 写入代码、报告或提交历史。

## Project Structure

| Path | Purpose |
| --- | --- |
| `src/sar_project/` | SAR 策略、数据、回测、优化和报告生成代码 |
| `tests/test_sar_*.py` | SAR 项目单元测试和流水线测试 |
| `docs/sar_project/` | 回测报告、图表和摘要指标 |
| `docs/sar_project/audit/` | 样本外交易流水、配对交易、净值、参数搜索和 SHA-256 审计附件 |
| `data/raw/`, `data/interim/`, `data/processed/` | 数据目录占位；真实缓存数据默认不提交 |
| `scripts/run_checks.sh` | 本地验证入口 |

## Current Result

当前重做版报告基于最新本地缓存数据生成。样本外区间为 2021-2025 年，策略目标是在计入交易成本后跑赢沪深300，并避免通过长期空仓实现收益曲线优化。

完整中文全过程报告：

- `docs/sar_project/sar_project_full_process_report.md`

快速展示版报告：

- `docs/sar_project/sar_project_report.md`
- `docs/sar_project/sar_project_report.pdf`

审计附件：

- `docs/sar_project/audit/trade_ledger_sample_out.csv`
- `docs/sar_project/audit/round_trip_trades_sample_out.csv`
- `docs/sar_project/audit/portfolio_sample_out.csv`
- `docs/sar_project/audit/optimization_results_sample_in.csv`
- `docs/sar_project/audit/audit_manifest.csv`

本项目仅用于课程/实习展示和研究复现，不构成投资建议。
