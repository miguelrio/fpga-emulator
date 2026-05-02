from dataclasses import dataclass


@dataclass(frozen=True)
class TechNodeParams:
    node: str
    gate_delay_ps: float        # ps per logic level
    gate_density_per_mm2: float # gate equivalents per mm²
    vdd: float                  # supply voltage (V)
    c_eff_ff: float             # effective capacitance per GE (fF)
    leakage_nw_per_ge: float    # leakage power per GE (nW)


TECH_NODES: dict[str, TechNodeParams] = {
    "28nm": TechNodeParams(
        node="28nm",
        gate_delay_ps=50.0,
        gate_density_per_mm2=200_000,
        vdd=0.9,
        c_eff_ff=2.0,
        leakage_nw_per_ge=5.0,
    ),
    "16nm": TechNodeParams(
        node="16nm",
        gate_delay_ps=35.0,
        gate_density_per_mm2=350_000,
        vdd=0.8,
        c_eff_ff=1.4,
        leakage_nw_per_ge=8.0,
    ),
    "7nm": TechNodeParams(
        node="7nm",
        gate_delay_ps=20.0,
        gate_density_per_mm2=100_000_000,
        vdd=0.7,
        c_eff_ff=0.9,
        leakage_nw_per_ge=15.0,
    ),
    "5nm": TechNodeParams(
        node="5nm",
        gate_delay_ps=15.0,
        gate_density_per_mm2=170_000_000,
        vdd=0.65,
        c_eff_ff=0.7,
        leakage_nw_per_ge=22.0,
    ),
}

VALID_NODES = list(TECH_NODES.keys())


def get_node(name: str) -> TechNodeParams:
    if name not in TECH_NODES:
        raise ValueError(f"Unknown tech node '{name}'. Valid: {VALID_NODES}")
    return TECH_NODES[name]


def interpolate(node_a: str, node_b: str, alpha: float) -> TechNodeParams:
    """Linear interpolation between two tech nodes (alpha=0 → node_a, alpha=1 → node_b)."""
    a = get_node(node_a)
    b = get_node(node_b)
    alpha = max(0.0, min(1.0, alpha))

    def lerp(x, y):
        return x + (y - x) * alpha

    return TechNodeParams(
        node=f"{node_a}-{node_b}@{alpha:.2f}",
        gate_delay_ps=lerp(a.gate_delay_ps, b.gate_delay_ps),
        gate_density_per_mm2=lerp(a.gate_density_per_mm2, b.gate_density_per_mm2),
        vdd=lerp(a.vdd, b.vdd),
        c_eff_ff=lerp(a.c_eff_ff, b.c_eff_ff),
        leakage_nw_per_ge=lerp(a.leakage_nw_per_ge, b.leakage_nw_per_ge),
    )
