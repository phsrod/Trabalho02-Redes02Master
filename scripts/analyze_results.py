#!/usr/bin/env python3
"""Generate statistics table and plots from client metrics CSV."""
from __future__ import annotations
 
import argparse
import os
import sys
 
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
 
SCENARIO_ORDER = ("A", "B", "C")
MODE_ORDER = ("tcp", "rudp")
 
 
def _ordered_values(values, preferred_order):
    present = list(dict.fromkeys(str(v) for v in values))
    ordered = [v for v in preferred_order if v in present]
    remaining = sorted(v for v in present if v not in preferred_order)
    return ordered + remaining
 
 
def _prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    required = {"scenario", "mode", "duration_sec", "throughput_mbps"}
    missing = required.difference(df.columns)
    if missing:
        print("CSV missing required columns: " + ", ".join(sorted(missing)), file=sys.stderr)
        sys.exit(1)
    cleaned = df.copy()
    if "role" in cleaned.columns:
        client_rows = cleaned[cleaned["role"].astype(str).str.lower() == "client"].copy()
        if not client_rows.empty:
            cleaned = client_rows
    return cleaned
 
 
def _build_summary(df: pd.DataFrame) -> pd.DataFrame:
    agg = {}
    if "run_id" in df.columns:
        agg["runs"] = ("run_id", "count")
    agg["throughput_min"] = ("throughput_mbps", "min")
    agg["throughput_mean"] = ("throughput_mbps", "mean")
    agg["throughput_max"] = ("throughput_mbps", "max")
    agg["throughput_std"] = ("throughput_mbps", "std")
    agg["duration_min"] = ("duration_sec", "min")
    agg["duration_mean"] = ("duration_sec", "mean")
    agg["duration_max"] = ("duration_sec", "max")
    agg["duration_std"] = ("duration_sec", "std")
 
    summary = df.groupby(["scenario", "mode"], as_index=False).agg(**agg).reset_index(drop=True)
    summary["throughput_std"] = summary["throughput_std"].fillna(0.0)
    summary["duration_std"] = summary["duration_std"].fillna(0.0)
    if "runs" in summary.columns:
        summary["runs"] = summary["runs"].astype(int)
    return summary
 
 
def _plot_throughput_bars(df: pd.DataFrame, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    summary = _build_summary(df)
    scenarios = _ordered_values(summary["scenario"].unique(), SCENARIO_ORDER)
    modes = _ordered_values(summary["mode"].unique(), MODE_ORDER)
 
    for mode in modes:
        subset = summary[summary["mode"] == mode].copy()
        if subset.empty:
            continue
        means = [subset.loc[subset["scenario"] == s, "throughput_mean"].values[0] if not subset.loc[subset["scenario"] == s].empty else 0 for s in scenarios]
        stds = [subset.loc[subset["scenario"] == s, "throughput_std"].values[0] if not subset.loc[subset["scenario"] == s].empty else 0 for s in scenarios]
        fig, ax = plt.subplots(figsize=(8, 5))
        bars = ax.bar(scenarios, means, yerr=stds, capsize=6, color="#2196F3" if mode == "tcp" else "#FF9800")
        for bar, val in zip(bars, means):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5, f"{val:.2f}", ha="center", va="bottom", fontsize=9)
        ax.set_xlabel("Scenario")
        ax.set_ylabel("Throughput (Mbps)")
        ax.set_title(f"Throughput per Scenario - {mode.upper()}")
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        fname = os.path.join(out_dir, f"throughput_{mode}.png")
        fig.savefig(fname, dpi=150)
        plt.close(fig)
        print(f"Saved: {fname}")
 
    # comparison plot
    fig, ax = plt.subplots(figsize=(10, 6))
    width = 0.35
    x = range(len(scenarios))
    for i, mode in enumerate(modes):
        subset = summary[summary["mode"] == mode]
        means = [subset.loc[subset["scenario"] == s, "throughput_mean"].values[0] if not subset.loc[subset["scenario"] == s].empty else 0 for s in scenarios]
        stds = [subset.loc[subset["scenario"] == s, "throughput_std"].values[0] if not subset.loc[subset["scenario"] == s].empty else 0 for s in scenarios]
        offset = (i - 0.5) * width
        bars = ax.bar([p + offset for p in x], means, width, yerr=stds, capsize=4, label=mode.upper(), color=["#2196F3", "#FF9800"][i])
    ax.set_xlabel("Scenario")
    ax.set_ylabel("Throughput (Mbps)")
    ax.set_title("TCP vs R-UDP Throughput Comparison")
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    fname = os.path.join(out_dir, "throughput_comparison.png")
    fig.savefig(fname, dpi=150)
    plt.close(fig)
    print(f"Saved: {fname}")
 
 
def main() -> None:
    p = argparse.ArgumentParser(description="Generate statistics and plots from metrics CSV.")
    p.add_argument("csv_path", help="CSV with columns: scenario, mode, duration_sec, throughput_mbps")
    p.add_argument("--out-dir", default="results/plots")
    args = p.parse_args()
 
    if not os.path.isfile(args.csv_path):
        print(f"File not found: {args.csv_path}", file=sys.stderr)
        sys.exit(1)
 
    df = _prepare_dataframe(pd.read_csv(args.csv_path))
    os.makedirs(args.out_dir, exist_ok=True)
 
    summary = _build_summary(df)
    summary.to_csv(os.path.join(args.out_dir, "stats_summary.csv"), index=False)
 
    print("Aggregated statistics per scenario and mode:\n")
    print(summary.to_string(index=False))
    print(f"\nSummary saved to: {os.path.join(args.out_dir, 'stats_summary.csv')}")
 
    _plot_throughput_bars(df, args.out_dir)
 
 
if __name__ == "__main__":
    main()