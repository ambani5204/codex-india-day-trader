"""Merge verified paper executions and independent index research for weekly AI review.

Research hypotheses are proposals, never empirical findings without matching tests.
This script never modifies trading rules or submits orders.
"""
import argparse
import datetime as dt
import json
from pathlib import Path


def merge(paper, forward):
    findings = []
    for name, stat in sorted((paper.get("strategy_reviews") or {}).items()):
        count = int(stat.get("verified_trades") or 0)
        if int(stat.get("stop_exceedances") or 0):
            findings.append({
                "strategy": name, "priority": "HIGH", "category": "RISK_EXECUTION",
                "observation": f"{stat['stop_exceedances']} modeled-stop overruns among {count} verified trades",
                "hypothesis": "Option fills, gaps or slippage may exceed the modeled stop budget",
                "proposed_test": "Reconcile tick/quote prices, fees, planned stop, realized exit and slippage per trade; stress-test adverse fills",
                "evidence_level": "OBSERVED_PAPER_EXECUTION",
                "recommendation_status": "TEST_REQUIRED",
            })
        findings.append({
            "strategy": name, "priority": "MEDIUM", "category": "REGIME_AND_ENTRY",
            "observation": f"{count} verified paper trades; win rate {stat.get('win_rate')}",
            "hypothesis": ("Mean reversion may depend on sideways versus trending regimes"
                           if "MEAN" in name.upper() else
                           "Entry performance may depend on trend, volatility and time of day"),
            "proposed_test": "Compare regime buckets (ADX, realized volatility, time of day) using chronological out-of-sample data and realistic option fills",
            "evidence_level": "HYPOTHESIS_NOT_VALIDATED",
            "recommendation_status": "TEST_REQUIRED",
        })
    forward_results = []
    if forward.get("kind") == "FROZEN_PROSPECTIVE_INDEX_RESEARCH_HUMAN_REVIEW_ONLY":
        for row in forward.get("results", []):
            metrics = row.get("forward") or {}
            forward_results.append({
                "playbook": row.get("playbook"),
                "trades": metrics.get("trades"),
                "net_r": metrics.get("net_total_r"),
                "profit_factor": metrics.get("net_profit_factor"),
                "qualified_proxy_only": bool(row.get("qualified_proxy_only_for_human_review")),
                "evidence_level": "INDEX_FUTURES_COST_PROXY_NOT_OPTION_EXECUTION",
            })
    return {
        "kind": "MERGED_PAPER_STRATEGY_AI_REVIEW_V1",
        "report_date": paper.get("report_date"),
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "paper": {
            "sessions": paper.get("sessions"), "verified_trades": paper.get("verified_pnl_trades"),
            "net_pnl": paper.get("net_pnl"), "win_rate": paper.get("win_rate"),
            "risk_rejections": paper.get("risk_rejections"),
            "markets": paper.get("markets"), "strategy_reviews": paper.get("strategy_reviews"),
        },
        "forward_research": {
            "status": forward.get("status", "NOT_AVAILABLE"),
            "data_type": "INDEX_PROXY_NOT_OPTION_PNL",
            "results": forward_results,
        },
        "investigations": findings,
        "limitations": [
            "A single losing trade does not establish strategy failure.",
            "Index proxy backtests cannot be represented as executable option returns.",
            "No automatic code changes, trading-rule changes, or broker orders.",
            "Proposals require out-of-sample validation and human approval.",
        ],
    }


def markdown(report):
    paper = report["paper"]
    lines = [
        "# Weekly ChatGPT strategy research handoff",
        "",
        f"Evaluation date: {report.get('report_date')} | Paper sessions: {paper.get('sessions')}",
        f"Verified trades: {paper.get('verified_trades')} | Net paper P&L: {paper.get('net_pnl')}",
        f"Forward research status: {report['forward_research']['status']}",
        "",
        "## Observations and hypotheses",
    ]
    for finding in report["investigations"]:
        lines += [
            f"### {finding['strategy']} — {finding['category']}",
            f"- Observed: {finding['observation']}",
            f"- Hypothesis (not proven): {finding['hypothesis']}",
            f"- Required test: {finding['proposed_test']}",
            f"- Evidence: {finding['evidence_level']}",
        ]
    lines += ["", "## Independent index-proxy research"]
    for item in report["forward_research"]["results"]:
        lines.append(f"- {item['playbook']}: {item['trades']} trades; net R {item['net_r']}; PF {item['profit_factor']}; proxy-qualified {item['qualified_proxy_only']}")
    lines += [
        "", "## Instructions for ChatGPT weekly review",
        "Analyze the accompanying JSON, identify the highest-risk failure modes, and propose",
        "testable strategy improvements with metrics, data requirements and out-of-sample gates.",
        "Separate facts from hypotheses. Never infer unobserved market regimes or guaranteed returns.",
        "Do not alter the active paper trader without explicit human approval.",
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper", required=True)
    parser.add_argument("--forward", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args()
    paper = json.loads(Path(args.paper).read_text())
    try:
        forward = json.loads(Path(args.forward).read_text())
    except (OSError, ValueError):
        forward = {"status": "NOT_AVAILABLE"}
    report = merge(paper, forward)
    for output, content in ((args.json_out, json.dumps(report, indent=2) + "\n"),
                            (args.markdown_out, markdown(report))):
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print("MERGED_STRATEGY_REVIEW_READY investigations=" + str(len(report["investigations"])))


if __name__ == "__main__":
    main()
