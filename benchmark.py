#!/usr/bin/env python3
from __future__ import annotations
"""
Benchmark: performance vs packet size.

Runs each packet permutation through the pipeline, collects cycle counts,
and plots throughput (Gbps), latency (cycles), and pipeline efficiency
against packet size for each protocol/IP combination.

Usage:
    python3 benchmark.py                         # display plot
    python3 benchmark.py --save perf.png         # save to file
    python3 benchmark.py --tech-node 28nm        # change ASIC node
    python3 benchmark.py --sizes 64,128,256,512,1024,1500,4096,9000
"""
import argparse
import collections
import sys
from dataclasses import dataclass

# ── optional matplotlib check ──────────────────────────────────────────────
try:
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    import numpy as np
except ImportError:
    sys.exit("matplotlib and numpy are required: pip install matplotlib numpy")

from sim.pipeline import build_default_pipeline
from sim.packet import PacketFactory, IP_VERSIONS, PROTOCOLS
from ppa.estimator import PPAEstimator
from ppa.tech_nodes import get_node, VALID_NODES


# ── data collection ────────────────────────────────────────────────────────

@dataclass
class Result:
    ip_version: int
    proto: str
    size_bytes: int
    total_cycles: int
    completed: bool
    fmax_ghz: float

    @property
    def label(self):
        return f"IPv{self.ip_version}/{self.proto.upper()}"

    @property
    def latency_ns(self):
        return self.total_cycles / self.fmax_ghz

    @property
    def throughput_gbps(self):
        """Goodput: payload bits / time to process one packet."""
        if self.total_cycles == 0 or self.fmax_ghz == 0:
            return 0.0
        time_ns = self.latency_ns
        return (self.size_bytes * 8) / time_ns  # bits / ns = Gbps

    @property
    def bits_per_cycle(self):
        if self.total_cycles == 0:
            return 0.0
        return (self.size_bytes * 8) / self.total_cycles


def run_benchmark(sizes: list[int], tech_node: str) -> list[Result]:
    node = get_node(tech_node)
    estimator = PPAEstimator(tech_node)
    results = []

    for ip_ver in IP_VERSIONS:
        for proto in PROTOCOLS:
            for size in sizes:
                engine = build_default_pipeline()
                pkt = PacketFactory.make(
                    ip_version=ip_ver,
                    proto=proto,
                    size=size,
                    src_ip="10.0.0.1" if ip_ver == 4 else "2001:db8::1",
                    dst_ip="192.168.1.5" if ip_ver == 4 else "2001:db8::2",
                )
                engine.run([pkt], max_cycles=500)

                completed = pkt.pkt_id in {p.pkt_id for p in engine.completed}
                cycles = engine.clock.cycle

                stage_metrics = [s.metrics for s in engine.get_stages()]
                ppa = estimator.estimate(stage_metrics)

                results.append(Result(
                    ip_version=ip_ver,
                    proto=proto,
                    size_bytes=size,
                    total_cycles=cycles,
                    completed=completed,
                    fmax_ghz=ppa.fmax_ghz,
                ))
                status = "OK" if completed else "DROP"
                print(f"  [{status}] IPv{ip_ver}/{proto.upper():3s}  "
                      f"{size:>5}B  "
                      f"{cycles:>4} cycles  "
                      f"{ppa.fmax_ghz:.2f} GHz  "
                      f"→ {results[-1].throughput_gbps:.3f} Gbps")

    return results


# ── plotting ───────────────────────────────────────────────────────────────

SERIES_STYLES = {
    "IPv4/TCP": dict(color="#3CB371", marker="o", linestyle="-",  linewidth=2),
    "IPv4/UDP": dict(color="#2E8B57", marker="s", linestyle="--", linewidth=2),
    "IPv6/TCP": dict(color="#4682B4", marker="^", linestyle="-",  linewidth=2),
    "IPv6/UDP": dict(color="#1E90FF", marker="D", linestyle="--", linewidth=2),
}


def plot(results: list[Result], tech_node: str, save_path: str | None):
    # Group by label
    grouped: dict[str, list[Result]] = collections.defaultdict(list)
    for r in results:
        grouped[r.label].append(r)
    for v in grouped.values():
        v.sort(key=lambda r: r.size_bytes)

    sizes_all = sorted({r.size_bytes for r in results})

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle(
        f"FPGA Router Simulator — Performance vs Packet Size  ({tech_node})",
        fontsize=14, fontweight="bold", y=0.98,
    )
    fig.patch.set_facecolor("#0F141E")
    for ax in axes.flat:
        ax.set_facecolor("#161E2D")
        ax.tick_params(colors="#9BB3CC")
        ax.xaxis.label.set_color("#9BB3CC")
        ax.yaxis.label.set_color("#9BB3CC")
        ax.title.set_color("#D4E6F5")
        for spine in ax.spines.values():
            spine.set_edgecolor("#2A3F5F")
        ax.grid(True, color="#1E2F45", linewidth=0.7, linestyle="--")

    # ── (0,0) Throughput Gbps ─────────────────────────────────────────────
    ax = axes[0, 0]
    for label, series in grouped.items():
        xs = [r.size_bytes for r in series]
        ys = [r.throughput_gbps for r in series]
        ax.plot(xs, ys, label=label, **SERIES_STYLES[label])
    ax.set_title("Throughput (Gbps)")
    ax.set_xlabel("Packet size (bytes)")
    ax.set_ylabel("Gbps")
    ax.set_xscale("log", base=2)
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x)}"))
    ax.set_xticks(sizes_all)
    ax.legend(facecolor="#0D1520", edgecolor="#2A3F5F", labelcolor="#D4E6F5", fontsize=9)

    # ── (0,1) Latency (cycles) ────────────────────────────────────────────
    ax = axes[0, 1]
    for label, series in grouped.items():
        xs = [r.size_bytes for r in series]
        ys = [r.total_cycles for r in series]
        ax.plot(xs, ys, label=label, **SERIES_STYLES[label])
    ax.set_title("Pipeline Latency (clock cycles)")
    ax.set_xlabel("Packet size (bytes)")
    ax.set_ylabel("Cycles")
    ax.set_xscale("log", base=2)
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x)}"))
    ax.set_xticks(sizes_all)
    ax.legend(facecolor="#0D1520", edgecolor="#2A3F5F", labelcolor="#D4E6F5", fontsize=9)

    # ── (1,0) Bits processed per cycle ───────────────────────────────────
    ax = axes[1, 0]
    for label, series in grouped.items():
        xs = [r.size_bytes for r in series]
        ys = [r.bits_per_cycle for r in series]
        ax.plot(xs, ys, label=label, **SERIES_STYLES[label])
    ax.set_title("Pipeline Efficiency (bits/cycle)")
    ax.set_xlabel("Packet size (bytes)")
    ax.set_ylabel("bits / cycle")
    ax.set_xscale("log", base=2)
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x)}"))
    ax.set_xticks(sizes_all)
    ax.legend(facecolor="#0D1520", edgecolor="#2A3F5F", labelcolor="#D4E6F5", fontsize=9)

    # ── (1,1) Latency (ns) at selected tech node ─────────────────────────
    ax = axes[1, 1]
    for label, series in grouped.items():
        xs = [r.size_bytes for r in series]
        ys = [r.latency_ns for r in series]
        ax.plot(xs, ys, label=label, **SERIES_STYLES[label])
    ax.set_title(f"Pipeline Latency (ns)  @{tech_node}")
    ax.set_xlabel("Packet size (bytes)")
    ax.set_ylabel("Latency (ns)")
    ax.set_xscale("log", base=2)
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x)}"))
    ax.set_xticks(sizes_all)
    ax.legend(facecolor="#0D1520", edgecolor="#2A3F5F", labelcolor="#D4E6F5", fontsize=9)

    plt.tight_layout(rect=[0, 0, 1, 0.96])

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        print(f"\nPlot saved to {save_path}")
    else:
        plt.show()


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Benchmark: performance vs packet size")
    p.add_argument("--tech-node", default="7nm", choices=VALID_NODES,
                   help="ASIC tech node for latency/throughput calculation")
    p.add_argument("--sizes", default="64,512,1500,9000",
                   help="Comma-separated packet sizes in bytes")
    p.add_argument("--save", metavar="PATH",
                   help="Save plot to file instead of displaying it (e.g. perf.png)")
    args = p.parse_args()

    sizes = [int(s.strip()) for s in args.sizes.split(",")]
    sizes = sorted(set(sizes))

    print(f"Running benchmark: {len(sizes)} sizes × 4 protocol combos "
          f"= {len(sizes) * 4} simulations  (tech-node: {args.tech_node})\n")

    results = run_benchmark(sizes, args.tech_node)
    plot(results, args.tech_node, args.save)


if __name__ == "__main__":
    main()
