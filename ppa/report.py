from __future__ import annotations
import csv
import json
from ppa.estimator import PPAResult


def format_report(result: PPAResult) -> str:
    lines = [
        f"╔══ ASIC PPA Estimate ({result.tech_node}) ═══════════════════════╗",
        f"║  Total GE:    {result.total_gate_equivalents:>12,}",
        f"║  Fmax:        {result.fmax_ghz:>11.3f} GHz",
        f"║  Die area:    {result.die_area_mm2:>11.6f} mm²",
        f"║  Dyn power:   {result.dynamic_power_mw:>11.4f} mW",
        f"║  Leakage:     {result.leakage_power_mw:>11.4f} mW",
        f"║  Total power: {result.total_power_mw:>11.4f} mW",
        f"╠══ Per-stage breakdown ════════════════════════════════════╣",
    ]
    for name, est in result.per_stage.items():
        lines.append(
            f"║  {name:<20}  GE={est.gate_equivalents:>6}  "
            f"Fmax={est.fmax_ghz:.2f}GHz  P={est.total_power_mw:.2f}mW"
        )
    lines.append("╚══════════════════════════════════════════════════════════╝")
    return "\n".join(lines)


def to_dict(result: PPAResult) -> dict:
    return {
        "tech_node": result.tech_node,
        "total_gate_equivalents": result.total_gate_equivalents,
        "fmax_ghz": result.fmax_ghz,
        "die_area_mm2": result.die_area_mm2,
        "dynamic_power_mw": result.dynamic_power_mw,
        "leakage_power_mw": result.leakage_power_mw,
        "total_power_mw": result.total_power_mw,
        "per_stage": {
            name: {
                "gate_equivalents": est.gate_equivalents,
                "fmax_ghz": est.fmax_ghz,
                "die_area_mm2": est.die_area_mm2,
                "dynamic_power_mw": est.dynamic_power_mw,
                "leakage_power_mw": est.leakage_power_mw,
                "total_power_mw": est.total_power_mw,
            }
            for name, est in result.per_stage.items()
        },
    }


def export_csv(result: PPAResult, path: str):
    fieldnames = [
        "stage", "gate_equivalents", "fmax_ghz", "die_area_mm2",
        "dynamic_power_mw", "leakage_power_mw", "total_power_mw",
    ]
    rows = [
        {
            "stage": name,
            "gate_equivalents": est.gate_equivalents,
            "fmax_ghz": est.fmax_ghz,
            "die_area_mm2": est.die_area_mm2,
            "dynamic_power_mw": est.dynamic_power_mw,
            "leakage_power_mw": est.leakage_power_mw,
            "total_power_mw": est.total_power_mw,
        }
        for name, est in result.per_stage.items()
    ]
    # Append totals row
    rows.append({
        "stage": "_TOTAL",
        "gate_equivalents": result.total_gate_equivalents,
        "fmax_ghz": result.fmax_ghz,
        "die_area_mm2": result.die_area_mm2,
        "dynamic_power_mw": result.dynamic_power_mw,
        "leakage_power_mw": result.leakage_power_mw,
        "total_power_mw": result.total_power_mw,
    })
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_json(result: PPAResult, path: str):
    with open(path, "w") as f:
        json.dump(to_dict(result), f, indent=2)
