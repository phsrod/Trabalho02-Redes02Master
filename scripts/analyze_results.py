"""
Análise comparativa (Pandas/Matplotlib) a partir do CSV gerado pelo cliente.
Uso: python scripts/analyze_results.py results/metrics_app.csv
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SCENARIO_ORDER = ("A", "B", "C")
MODE_ORDER = ("tcp", "rudp")
MODE_TITLES = {"tcp": "TCP", "rudp": "R-UDP"}


def _ordered_values(values: Iterable[str], preferred_order: tuple[str, ...]) -> list[str]:
    present = list(dict.fromkeys(str(v) for v in values))
    ordered = [value for value in preferred_order if value in present]
    remaining = sorted(value for value in present if value not in preferred_order)
    return ordered + remaining


def _prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    required = {"scenario", "mode", "duration_sec", "throughput_mbps"}
    missing = required.difference(df.columns)
    if missing:
        print(
            "CSV sem as colunas obrigatórias: " + ", ".join(sorted(missing)),
            file=sys.stderr,
        )
        sys.exit(1)

    cleaned = df.copy()
    if "role" in cleaned.columns:
        client_rows = cleaned[cleaned["role"].astype(str).str.lower() == "client"].copy()
        if not client_rows.empty:
            cleaned = client_rows

    return cleaned


def _build_summary(df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        df.groupby(["scenario", "mode"], as_index=False)
        .agg(
            runs=("run_id", "count") if "run_id" in df.columns else ("throughput_mbps", "count"),
            throughput_min=("throughput_mbps", "min"),
            throughput_mean=("throughput_mbps", "mean"),
            throughput_max=("throughput_mbps", "max"),
            throughput_std=("throughput_mbps", "std"),
            duration_min=("duration_sec", "min"),
            duration_mean=("duration_sec", "mean"),
            duration_max=("duration_sec", "max"),
            duration_std=("duration_sec", "std"),
        )
        .reset_index(drop=True)
    )

    summary["throughput_std"] = summary["throughput_std"].fillna(0.0)
    summary["duration_std"] = summary["duration_std"].fillna(0.0)
    summary["runs"] = summary["runs"].astype(int)
    return summary


def _save_metric_csv(summary: pd.DataFrame, metric_prefix: str, out_path: str) -> None:
    columns = [
        "scenario",
        "mode",
        "runs",
        f"{metric_prefix}_min",
        f"{metric_prefix}_mean",
        f"{metric_prefix}_max",
        f"{metric_prefix}_std",
    ]
    summary.loc[:, columns].to_csv(out_path, index=False)


def _annotate_points(axis: plt.Axes, x: np.ndarray, values: list[float], offset_y: int = 6) -> None:
    for x_value, y_value in zip(x, values, strict=True):
        axis.annotate(
            f"{y_value:.3f}",
            (x_value, y_value),
            textcoords="offset points",
            xytext=(0, offset_y),
            ha="center",
            fontsize=8,
            color="#222222",
        )


def _plot_metric_lines_by_protocol(
    summary: pd.DataFrame,
    metric_prefix: str,
    ylabel: str,
    title: str,
    out_path: str,
) -> None:
    scenarios = _ordered_values(summary["scenario"].unique(), SCENARIO_ORDER)
    mode = str(summary["mode"].iloc[0]) if not summary.empty else ""
    mode_title = MODE_TITLES.get(mode, mode.upper() if mode else "")

    fig, axes = plt.subplots(
        2,
        2,
        figsize=(11.5, 8.0),
        sharex=True,
    )
    axes = np.atleast_1d(axes)

    stat_keys = [
        ("min", "Mínimo", "#DD8452"),
        ("mean", "Média", "#4C72B0"),
        ("max", "Máximo", "#55A868"),
        ("std", "Desvio padrão", "#C44E52"),
    ]

    x = np.arange(len(scenarios))

    subset = summary.set_index("scenario")
    for axis, (stat_suffix, stat_label, color) in zip(axes.flat, stat_keys, strict=True):
        values = [
            float(subset.loc[scenario, f"{metric_prefix}_{stat_suffix}"])
            if scenario in subset.index
            else 0.0
            for scenario in scenarios
        ]
        axis.plot(
            x,
            values,
            marker="o",
            linewidth=2.0,
            color=color,
            label=stat_label,
        )
        _annotate_points(axis, x, values)
        axis.set_title(stat_label)
        axis.set_xticks(x)
        axis.set_xticklabels(scenarios)
        axis.grid(True, axis="both", alpha=0.3)
        axis.set_axisbelow(True)
        axis.legend(loc="best")

    for axis in axes.flat:
        axis.set_xlabel("Cenário")
        axis.set_ylabel(ylabel)

    fig.suptitle(f"{title} - {mode_title}" if mode_title else title)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=170)


def _save_protocol_figures(summary: pd.DataFrame, args_out_dir: str) -> None:
    # prepare protocol dirs
    tcp_dir = os.path.join(args_out_dir, "tcp")
    rudp_dir = os.path.join(args_out_dir, "rudp")
    os.makedirs(tcp_dir, exist_ok=True)
    os.makedirs(rudp_dir, exist_ok=True)

    for mode in _ordered_values(summary["mode"].unique(), MODE_ORDER):
        mode_summary = summary[summary["mode"] == mode]
        mode_dir = tcp_dir if mode == "tcp" else rudp_dir
        throughput_out = os.path.join(mode_dir, f"throughput_{mode}_lines.png")
        duration_out = os.path.join(mode_dir, f"duration_{mode}_lines.png")

        _plot_metric_lines_by_protocol(
            mode_summary,
            "throughput",
            "Vazão (Mbps)",
            f"Vazão por cenário - {MODE_TITLES.get(mode, mode.upper())}",
            throughput_out,
        )
        _plot_metric_lines_by_protocol(
            mode_summary,
            "duration",
            "Tempo (s)",
            f"Tempo por cenário - {MODE_TITLES.get(mode, mode.upper())}",
            duration_out,
        )


def _save_individual_stat_figures(summary: pd.DataFrame, args_out_dir: str) -> None:
    """Save one PNG per protocol/metric/statistic (e.g. throughput_tcp_mean.png)."""
    stats = [("min", "Mínimo"), ("mean", "Média"), ("max", "Máximo"), ("std", "Desvio padrão")]
    scenarios = _ordered_values(summary["scenario"].unique(), SCENARIO_ORDER)
    x = np.arange(len(scenarios))
    tcp_dir = os.path.join(args_out_dir, "tcp")
    rudp_dir = os.path.join(args_out_dir, "rudp")
    os.makedirs(tcp_dir, exist_ok=True)
    os.makedirs(rudp_dir, exist_ok=True)

    for mode in _ordered_values(summary["mode"].unique(), MODE_ORDER):
        subset = summary[summary["mode"] == mode].set_index("scenario")
        mode_dir = tcp_dir if mode == "tcp" else rudp_dir
        for metric_prefix, ylabel in (("throughput", "Vazão (Mbps)"), ("duration", "Tempo (s)")):
            for stat_suffix, stat_label in stats:
                values = [
                    float(subset.loc[scenario, f"{metric_prefix}_{stat_suffix}"])
                    if scenario in subset.index
                    else 0.0
                    for scenario in scenarios
                ]
                fig, ax = plt.subplots(figsize=(7, 4))
                ax.plot(x, values, marker="o", linewidth=2.0)
                _annotate_points(ax, x, values)
                ax.set_xticks(x)
                ax.set_xticklabels(scenarios)
                ax.set_xlabel("Cenário")
                ax.set_ylabel(ylabel)
                ax.set_title(f"{MODE_TITLES.get(mode, mode.upper())} — {metric_prefix.capitalize()} ({stat_label})")
                ax.grid(True, alpha=0.3)
                out_png = os.path.join(mode_dir, f"{metric_prefix}_{mode}_{stat_suffix}.png")
                fig.tight_layout()
                fig.savefig(out_png, dpi=150)
                plt.close(fig)


def _save_compare_stat_figures(summary: pd.DataFrame, args_out_dir: str) -> None:
    """Save comparison PNGs per statistic showing both protocols across scenarios."""
    stats = [("min", "Mínimo"), ("mean", "Média"), ("max", "Máximo"), ("std", "Desvio padrão")]
    scenarios = _ordered_values(summary["scenario"].unique(), SCENARIO_ORDER)
    x = np.arange(len(scenarios))
    compare_dir = os.path.join(args_out_dir, "compare")
    os.makedirs(compare_dir, exist_ok=True)

    for metric_prefix, ylabel in (("throughput", "Vazão (Mbps)"), ("duration", "Tempo (s)")):
        for stat_suffix, stat_label in stats:
            fig, ax = plt.subplots(figsize=(8, 4.5))
            for mode in _ordered_values(summary["mode"].unique(), MODE_ORDER):
                subset = summary[summary["mode"] == mode].set_index("scenario")
                values = [
                    float(subset.loc[scenario, f"{metric_prefix}_{stat_suffix}"])
                    if scenario in subset.index
                    else 0.0
                    for scenario in scenarios
                ]
                ax.plot(x, values, marker="o", linewidth=2.0, label=MODE_TITLES.get(mode, mode.upper()))
                # Ajuste de posição dos rótulos:
                # - Duração média: TCP embaixo
                # - Todos os gráficos de vazão: R-UDP embaixo
                if metric_prefix == "duration" and stat_suffix == "mean" and mode == "tcp":
                    _annotate_points(ax, x, values, offset_y=-12)
                elif metric_prefix == "throughput" and mode == "rudp":
                    _annotate_points(ax, x, values, offset_y=-12)
                else:
                    _annotate_points(ax, x, values)
            ax.set_xticks(x)
            ax.set_xticklabels(scenarios)
            ax.set_xlabel("Cenário")
            ax.set_ylabel(ylabel)
            ax.set_title(f"Comparação por cenário — {metric_prefix.capitalize()} ({stat_label})")
            ax.grid(True, alpha=0.3)
            ax.legend()
            out_png = os.path.join(compare_dir, f"{metric_prefix}_{stat_suffix}_compare.png")
            fig.tight_layout()
            fig.savefig(out_png, dpi=150)
            plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser(description="Gera estatísticas e gráficos comparativos por protocolo.")
    p.add_argument("csv_path", help="CSV com colunas: scenario, mode, duration_sec, throughput_mbps, ...")
    p.add_argument("--out-dir", default="results/plots")
    args = p.parse_args()

    if not os.path.isfile(args.csv_path):
        print(f"Arquivo não encontrado: {args.csv_path}", file=sys.stderr)
        sys.exit(1)

    df = _prepare_dataframe(pd.read_csv(args.csv_path))
    os.makedirs(args.out_dir, exist_ok=True)

    summary = _build_summary(df)

    summary_out = os.path.join(args.out_dir, "stats_summary.csv")
    summary.to_csv(summary_out, index=False)
    _save_metric_csv(summary, "throughput", os.path.join(args.out_dir, "stats_throughput.csv"))
    _save_metric_csv(summary, "duration", os.path.join(args.out_dir, "stats_duration.csv"))

    print("Estatísticas agregadas por cenário e modo:\n")
    print(summary.to_string(index=False))

    _save_protocol_figures(summary, args.out_dir)
    # also save individual-stat files per protocol and comparison figures across protocols
    _save_individual_stat_figures(summary, args.out_dir)
    _save_compare_stat_figures(summary, args.out_dir)

    print(f"\nResumo: {summary_out}")
    for mode in _ordered_values(summary["mode"].unique(), MODE_ORDER):
        print(f"Gráfico de vazão ({mode}): {os.path.join(args.out_dir, f'throughput_{mode}_lines.png')}")
        print(f"Gráfico de tempo ({mode}): {os.path.join(args.out_dir, f'duration_{mode}_lines.png')}")


if __name__ == "__main__":
    main()
