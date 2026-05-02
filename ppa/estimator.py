from __future__ import annotations
from dataclasses import dataclass

from ppa.tech_nodes import TechNodeParams, get_node
from sim.stage import StageMetrics

# Gate equivalent (GE) weights for FPGA resources
LUT_GE = 6
FF_GE = 4
BRAM_GE = 3000  # 18Kbit SRAM array ≈ 3000 NAND2 equivalents

ACTIVITY_FACTOR = 0.15  # typical toggle rate for network routing logic


@dataclass
class StageEstimate:
    stage_name: str
    gate_equivalents: int
    fmax_ghz: float
    die_area_mm2: float
    dynamic_power_mw: float
    leakage_power_mw: float
    total_power_mw: float


@dataclass
class PPAResult:
    tech_node: str
    total_gate_equivalents: int
    fmax_ghz: float
    die_area_mm2: float
    dynamic_power_mw: float
    leakage_power_mw: float
    total_power_mw: float
    per_stage: dict[str, StageEstimate]


class PPAEstimator:
    def __init__(self, tech_node: str = "7nm"):
        self.tech_node = tech_node

    def estimate_stage(self, metrics: StageMetrics, node: TechNodeParams) -> StageEstimate:
        ge = (
            metrics.lut_count * LUT_GE
            + metrics.ff_count * FF_GE
            + metrics.bram_count * BRAM_GE
        )

        logic_depth = max(1, metrics.logic_depth)
        t_cycle_ns = logic_depth * node.gate_delay_ps / 1000.0
        fmax_ghz = min(10.0, 1.0 / t_cycle_ns)

        area = ge / node.gate_density_per_mm2 if node.gate_density_per_mm2 > 0 else 0.0

        p_dyn = (
            ACTIVITY_FACTOR
            * node.c_eff_ff * 1e-15     # fF → F
            * node.vdd ** 2
            * fmax_ghz * 1e9            # GHz → Hz
            * ge
            * 1e3                        # W → mW
        )
        p_leak = node.leakage_nw_per_ge * ge * 1e-6  # nW → mW

        return StageEstimate(
            stage_name=metrics.name,
            gate_equivalents=ge,
            fmax_ghz=round(fmax_ghz, 3),
            die_area_mm2=round(area, 8),
            dynamic_power_mw=round(p_dyn, 4),
            leakage_power_mw=round(p_leak, 4),
            total_power_mw=round(p_dyn + p_leak, 4),
        )

    def estimate(self, stage_metrics: list[StageMetrics]) -> PPAResult:
        node = get_node(self.tech_node)
        per_stage: dict[str, StageEstimate] = {}

        for metrics in stage_metrics:
            per_stage[metrics.name] = self.estimate_stage(metrics, node)

        total_ge = sum(s.gate_equivalents for s in per_stage.values())

        # Overall Fmax = minimum across stages (weakest link)
        fmax = min((s.fmax_ghz for s in per_stage.values()), default=0.0)

        total_area = total_ge / node.gate_density_per_mm2 if node.gate_density_per_mm2 > 0 else 0.0
        total_dyn = sum(s.dynamic_power_mw for s in per_stage.values())
        total_leak = sum(s.leakage_power_mw for s in per_stage.values())

        return PPAResult(
            tech_node=self.tech_node,
            total_gate_equivalents=total_ge,
            fmax_ghz=round(fmax, 3),
            die_area_mm2=round(total_area, 8),
            dynamic_power_mw=round(total_dyn, 4),
            leakage_power_mw=round(total_leak, 4),
            total_power_mw=round(total_dyn + total_leak, 4),
            per_stage=per_stage,
        )
