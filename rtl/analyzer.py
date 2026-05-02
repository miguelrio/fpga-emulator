from __future__ import annotations
from dataclasses import dataclass

try:
    import networkx as nx
    NX_AVAILABLE = True
except ImportError:
    NX_AVAILABLE = False

from rtl.parser import RTLProfile


@dataclass
class CriticalPathResult:
    longest_path_hops: int    # gate hops on critical path
    node_count: int
    edge_count: int


class LogicDepthAnalyzer:
    """
    Builds a signal dependency DAG from an RTLProfile and finds the
    longest combinational path (critical path).

    Since we don't have full netlist connectivity from the AST parser,
    we approximate the DAG using operator_count and max_expression_depth
    from the parser to construct a synthetic path of the right length.
    """

    def analyze(self, profile: RTLProfile) -> CriticalPathResult:
        if not NX_AVAILABLE:
            return CriticalPathResult(
                longest_path_hops=profile.max_expression_depth,
                node_count=profile.wire_count + profile.reg_count,
                edge_count=profile.operator_count,
            )

        G = self._build_dag(profile)
        try:
            longest = nx.dag_longest_path_length(G)
        except Exception:
            longest = profile.max_expression_depth

        return CriticalPathResult(
            longest_path_hops=max(1, longest),
            node_count=G.number_of_nodes(),
            edge_count=G.number_of_edges(),
        )

    def _build_dag(self, profile: RTLProfile) -> "nx.DiGraph":
        G = nx.DiGraph()

        # Add input/output ports as source/sink nodes
        for port in profile.inputs:
            G.add_node(f"in_{port.name}", kind="input")
        for port in profile.outputs:
            G.add_node(f"out_{port.name}", kind="output")

        # Add synthetic wire nodes
        for i in range(profile.wire_count):
            G.add_node(f"wire_{i}", kind="wire")

        # Add synthetic register (FF) nodes
        for i in range(profile.reg_count):
            G.add_node(f"reg_{i}", kind="reg")

        # Build a synthetic chain of operator nodes representing
        # the estimated expression depth
        depth = profile.max_expression_depth
        op_nodes = [f"op_{i}" for i in range(depth)]
        for n in op_nodes:
            G.add_node(n, kind="operator")

        # Chain inputs → operators → outputs to represent critical path
        if profile.inputs and op_nodes:
            G.add_edge(f"in_{profile.inputs[0].name}", op_nodes[0])
        for i in range(len(op_nodes) - 1):
            G.add_edge(op_nodes[i], op_nodes[i + 1])
        if profile.outputs and op_nodes:
            G.add_edge(op_nodes[-1], f"out_{profile.outputs[0].name}")

        # Fan in wires to operator nodes
        for i, wnode in enumerate(list(G.nodes())[:profile.wire_count]):
            if op_nodes:
                target = op_nodes[i % len(op_nodes)]
                if wnode != target:
                    try:
                        G.add_edge(wnode, target)
                    except Exception:
                        pass

        # Remove any cycles (feedback paths / latches)
        while True:
            try:
                cycle_nodes = nx.find_cycle(G)
                u, v = cycle_nodes[0][:2]
                G.remove_edge(u, v)
            except nx.NetworkXNoCycle:
                break

        return G
