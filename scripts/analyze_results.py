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
FILE_SIZE_ORDER = ("100k", "500k", "1m")
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


def _group_keys(df: pd.DataFrame) -> list[str]:
    keys = ["scenario", "mode"]
    if "file_size" in df.columns and df["file_size"].astype(str).str.strip().ne("").any():
        keys.append("file_size")
    return keys


def _build_summary(df: pd.DataFrame) -> pd.DataFrame:
    group_keys = _group_keys(df)
    agg: dict[str, tuple[str, str]] = {
        "runs": ("run_id", "count") if "run_id" in df.columns else ("throughput_mbps", "count"),
        "throughput_min": ("throughput_mbps", "min"),
        "throughput_mean": ("throughput_mbps", "mean"),
        "throughput_max": ("throughput_mbps", "max"),
        "throughput_std": ("throughput_mbps", "std"),
        "duration_min": ("duration_sec", "min"),
        "duration_mean": ("duration_sec", "mean"),
        "duration_max": ("duration_sec", "max"),
        "duration_std": ("duration_sec", "std"),
    }
    if "dns_duration_sec" in df.columns:
        agg.update(
            {
                "dns_duration_mean": ("dns_duration_sec", "mean"),
                "dns_duration_std": ("dns_duration_sec", "std"),
                "http_duration_mean": ("http_duration_sec", "mean"),
                "http_duration_std": ("http_duration_sec", "std"),
            }
        )
    if "success" in df.columns:
        agg["success_count"] = ("success", "sum")

    summary = df.groupby(group_keys, as_index=False).agg(**agg).reset_index(drop=True)

    summary["throughput_std"] = summary["throughput_std"].fillna(0.0)
    summary["duration_std"] = summary["duration_std"].fillna(0.0)
    if "dns_duration_std" in summary.columns:
        summary["dns_duration_std"] = summary["dns_duration_std"].fillna(0.0)
        summary["http_duration_std"] = summary["http_duration_std"].fillna(0.0)
    summary["runs"] = summary["runs"].astype(int)

    if "success_count" in summary.columns:
        summary["success_count"] = summary["success_count"].astype(int)
        summary["success_rate"] = (summary["success_count"] / summary["runs"] * 100).round(2)
        summary["error_rate"] = (100.0 - summary["success_rate"]).round(2)

    return summary


def _save_metric_csv(summary: pd.DataFrame, metric_prefix: str, out_path: str) -> None:
    columns = ["scenario", "mode"]
    if "file_size" in summary.columns:
        columns.append("file_size")
    columns.extend(
        [
            "runs",
            f"{metric_prefix}_min",
            f"{metric_prefix}_mean",
            f"{metric_prefix}_max",
            f"{metric_prefix}_std",
        ]
    )
    summary.loc[:, columns].to_csv(out_path, index=False)





def _save_dns_http_breakdown(summary: pd.DataFrame, out_dir: str) -> None:
    if "dns_duration_mean" not in summary.columns:
        return
    compare_dir = os.path.join(out_dir, "compare")
    os.makedirs(compare_dir, exist_ok=True)
    scenarios = _ordered_values(summary["scenario"].unique(), SCENARIO_ORDER)
    x = np.arange(len(scenarios))
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for mode in _ordered_values(summary["mode"].unique(), MODE_ORDER):
        subset = summary[summary["mode"] == mode].groupby("scenario", as_index=False).agg(
            dns_duration_mean=("dns_duration_mean", "mean"),
            http_duration_mean=("http_duration_mean", "mean"),
        )
        subset = subset.set_index("scenario")
        dns_vals = [float(subset.loc[s, "dns_duration_mean"]) if s in subset.index else 0.0 for s in scenarios]
        http_vals = [float(subset.loc[s, "http_duration_mean"]) if s in subset.index else 0.0 for s in scenarios]
        ax.plot(x, dns_vals, marker="s", linestyle="--", label=f"DNS ({MODE_TITLES.get(mode, mode)})")
        ax.plot(x, http_vals, marker="o", label=f"HTTP ({MODE_TITLES.get(mode, mode)})")
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios)
    ax.set_xlabel("Cenário")
    ax.set_ylabel("Tempo médio (s)")
    ax.set_title("DNS (UDP) vs HTTP — tempo médio por cenário")
    ax.grid(True, alpha=0.3)
    ax.legend()
    out_png = os.path.join(compare_dir, "dns_vs_http_duration.png")
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


# ── Combined comparison graphs (side-by-side TCP | R-UDP) ────────────────

_COMBINED_SIZE_STYLES = {
    "100k": {"color": "#1f77b4", "marker": "o"},
    "500k": {"color": "#ff7f0e", "marker": "s"},
    "1m":   {"color": "#2ca02c", "marker": "^"},
}


def _plot_mode_subplot(
    ax: plt.Axes,
    summary: pd.DataFrame,
    mode: str,
    metric_col: str,
    scenarios: list[str],
    file_sizes: list[str],
    fmt_pct: bool = False,
) -> None:
    """Draw 3 lines (one per file_size) for a single protocol on a subplot axis."""
    x = np.arange(len(scenarios))

    for size in file_sizes:
        subset = summary[
            (summary["mode"] == mode) & (summary["file_size"] == size)
        ].set_index("scenario")

        values = [
            float(subset.loc[sc, metric_col]) if sc in subset.index else 0.0
            for sc in scenarios
        ]

        style = _COMBINED_SIZE_STYLES.get(size, {"color": "#333333", "marker": "o"})

        ax.plot(
            x, values,
            marker=style["marker"],
            linestyle="solid",
            color=style["color"],
            linewidth=2.0,
            label=size,
        )

        annot_fmt = ".1f" if fmt_pct else ".3f"
        for xi, yi in zip(x, values):
            ax.annotate(
                f"{yi:{annot_fmt}}{'%' if fmt_pct else ''}",
                (xi, yi),
                textcoords="offset points",
                xytext=(0, 6),
                ha="center",
                fontsize=7,
                color=style["color"],
            )

    ax.set_xticks(x)
    ax.set_xticklabels(scenarios)
    ax.set_xlabel("Cenário")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="best", title="Tamanho")


def _save_combined_compare_figures(summary: pd.DataFrame, out_dir: str) -> None:
    """Generate 6 side-by-side comparison PNGs in compare/ (TCP | R-UDP)."""
    compare_dir = os.path.join(out_dir, "compare")
    os.makedirs(compare_dir, exist_ok=True)

    if "file_size" not in summary.columns:
        return

    scenarios = _ordered_values(summary["scenario"].unique(), SCENARIO_ORDER)
    file_sizes = _ordered_values(summary["file_size"].unique(), FILE_SIZE_ORDER)
    modes = _ordered_values(summary["mode"].unique(), MODE_ORDER)

    if not scenarios or not file_sizes or not modes:
        return

    # 1) Duration mean
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=False)
    for ax, mode in zip(axes, modes):
        _plot_mode_subplot(ax, summary, mode, "duration_mean", scenarios, file_sizes)
        ax.set_title(MODE_TITLES.get(mode, mode.upper()))
    axes[0].set_ylabel("Tempo médio (s)")
    fig.suptitle("Duração média total (DNS + HTTP)", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(os.path.join(compare_dir, "duration_combined.png"), dpi=150)
    plt.close(fig)

    # 2-5) Throughput stats
    for stat, label in [("min", "Mínima"), ("mean", "Média"), ("max", "Máxima"), ("std", "Desvio Padrão")]:
        fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=False)
        for ax, mode in zip(axes, modes):
            _plot_mode_subplot(
                ax, summary, mode, f"throughput_{stat}", scenarios, file_sizes
            )
            ax.set_title(MODE_TITLES.get(mode, mode.upper()))
        axes[0].set_ylabel(f"Vazão {label.lower()} (Mbps)")
        fig.suptitle(f"Vazão {label}", fontsize=13)
        fig.tight_layout(rect=(0, 0, 1, 0.94))
        fig.savefig(os.path.join(compare_dir, f"throughput_{stat}_combined.png"), dpi=150)
        plt.close(fig)

    # 6) Error rate
    if "error_rate" in summary.columns:
        fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=False)
        for ax, mode in zip(axes, modes):
            _plot_mode_subplot(
                ax, summary, mode, "error_rate", scenarios, file_sizes, fmt_pct=True
            )
            ax.set_title(MODE_TITLES.get(mode, mode.upper()))
        axes[0].set_ylabel("Taxa de erro (%)")
        fig.suptitle("Taxa de erro", fontsize=13)
        fig.tight_layout(rect=(0, 0, 1, 0.94))
        fig.savefig(os.path.join(compare_dir, "error_rate_combined.png"), dpi=150)
        plt.close(fig)


def _merge_retransmission_rate(summary: pd.DataFrame, retrans_csv_path: str) -> pd.DataFrame:
    """Carrega o CSV de retransmissão e mescla a taxa de erro real no summary.

    A coluna ``error_rate`` do summary é substituída pela média das taxas de
    retransmissão agregadas por (scenario, mode, file_size).
    """
    if not os.path.isfile(retrans_csv_path):
        print(f"Aviso: arquivo de retransmissão não encontrado: {retrans_csv_path}", file=sys.stderr)
        return summary

    retrans_df = pd.read_csv(retrans_csv_path)

    group_keys = _group_keys(summary)
    # Agrega a taxa de erro média por grupo
    retrans_agg = (
        retrans_df.groupby(
            [k for k in group_keys if k in retrans_df.columns],
            as_index=False,
        )["error_rate_pct"]
        .mean()
        .round(2)
        .rename(columns={"error_rate_pct": "error_rate_retrans"})
    )

    merged = summary.merge(
        retrans_agg,
        on=[k for k in group_keys if k in retrans_agg.columns],
        how="left",
    )

    # Substitui error_rate onde houver dado de retransmissão
    if "error_rate_retrans" in merged.columns:
        has_retrans = merged["error_rate_retrans"].notna()
        merged.loc[has_retrans, "error_rate"] = merged.loc[has_retrans, "error_rate_retrans"]
        merged = merged.drop(columns=["error_rate_retrans"])
        print(f"  → Taxa de erro real (retransmissões) mesclada de: {retrans_csv_path}")

    return merged


def main() -> None:
    p = argparse.ArgumentParser(description="Gera estatísticas e gráficos comparativos por protocolo.")
    p.add_argument("csv_path", help="CSV com colunas: scenario, mode, duration_sec, throughput_mbps, ...")
    p.add_argument("--out-dir", default="results/plots")
    p.add_argument(
        "--retransmission-csv",
        default="",
        help="CSV gerado por calculate_error_rate.py com taxas de retransmissão (opcional)",
    )
    args = p.parse_args()

    if not os.path.isfile(args.csv_path):
        print(f"Arquivo não encontrado: {args.csv_path}", file=sys.stderr)
        sys.exit(1)

    df = _prepare_dataframe(pd.read_csv(args.csv_path))
    os.makedirs(args.out_dir, exist_ok=True)

    summary = _build_summary(df)

    # Mescla taxa de erro baseada em retransmissões (se fornecido)
    if args.retransmission_csv:
        summary = _merge_retransmission_rate(summary, args.retransmission_csv)

    summary_out = os.path.join(args.out_dir, "stats_summary.csv")
    summary.to_csv(summary_out, index=False)
    _save_metric_csv(summary, "throughput", os.path.join(args.out_dir, "stats_throughput.csv"))
    _save_metric_csv(summary, "duration", os.path.join(args.out_dir, "stats_duration.csv"))

    print("Estatísticas agregadas por cenário e modo:\n")
    print(summary.to_string(index=False))

    _save_dns_http_breakdown(summary, args.out_dir)
    _save_combined_compare_figures(summary, args.out_dir)

    print(f"\nResumo: {summary_out}")
    print(f"Gráficos combinados gerados em: {os.path.join(args.out_dir, 'compare/')}")
    print("  - duration_combined.png")
    print("  - throughput_min_combined.png")
    print("  - throughput_mean_combined.png")
    print("  - throughput_max_combined.png")
    print("  - throughput_std_combined.png")
    if "error_rate" in summary.columns:
        print("  - error_rate_combined.png")
    print("  - dns_vs_http_duration.png")
    print(f"CSV de estatísticas: {summary_out}")


if __name__ == "__main__":
    main()