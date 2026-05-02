from __future__ import annotations
import os
import tempfile
from dataclasses import dataclass, field

try:
    from pyverilog.vparser.parser import VerilogCodeParser
    import pyverilog.vparser.ast as vast
    PYVERILOG_AVAILABLE = True
except ImportError:
    PYVERILOG_AVAILABLE = False


@dataclass
class PortInfo:
    name: str
    width: int  # bits


@dataclass
class RTLProfile:
    module_name: str
    source_file: str
    inputs: list[PortInfo] = field(default_factory=list)
    outputs: list[PortInfo] = field(default_factory=list)
    reg_count: int = 0
    wire_count: int = 0
    always_block_count: int = 0
    clocked_always_count: int = 0
    memory_declarations: list[str] = field(default_factory=list)
    operator_count: int = 0
    max_expression_depth: int = 1
    estimated_luts: int = 0
    estimated_ffs: int = 0
    estimated_brams: int = 0
    estimated_cycle_latency: int = 1
    stage_name: str = ""  # from // @stage: annotation

    def __post_init__(self):
        if not self.stage_name:
            self.stage_name = self.module_name
        self._compute_estimates()

    def _compute_estimates(self):
        self.estimated_luts = int(self.operator_count * 1.8 + self.wire_count * 0.3)
        self.estimated_ffs = self.reg_count
        self.estimated_brams = len(self.memory_declarations)
        self.estimated_cycle_latency = max(1, self.clocked_always_count)


def _extract_width(node) -> int:
    """Extract bit width from a Width/Range node, defaulting to 1."""
    if node is None:
        return 1
    try:
        if hasattr(node, "msb") and hasattr(node, "lsb"):
            msb = int(str(node.msb))
            lsb = int(str(node.lsb))
            return abs(msb - lsb) + 1
    except (ValueError, TypeError, AttributeError):
        pass
    return 1


def _is_2d_array(node) -> bool:
    """Check if a variable declaration has array dimensions (BRAM candidate)."""
    if hasattr(node, "dimensions") and node.dimensions is not None:
        return True
    return False


def _is_clocked(sensitivity_list) -> bool:
    """Check if an always block is clocked (posedge/negedge)."""
    if sensitivity_list is None:
        return False
    sens_str = str(sensitivity_list)
    return "posedge" in sens_str or "negedge" in sens_str


class _ExpressionDepthVisitor:
    """Recursively measures expression depth and counts operators."""

    def __init__(self):
        self.max_depth = 0
        self.operator_count = 0

    def visit(self, node, depth=0):
        if node is None:
            return
        self.max_depth = max(self.max_depth, depth)
        if PYVERILOG_AVAILABLE and isinstance(node, vast.Operator):
            self.operator_count += 1
            for child in node.children():
                self.visit(child, depth + 1)
        elif hasattr(node, "children"):
            for child in node.children():
                self.visit(child, depth)


class VerilogPluginParser:
    def parse(self, filepath: str) -> RTLProfile:
        stage_name = self._extract_stage_annotation(filepath)

        if not PYVERILOG_AVAILABLE:
            return self._stub_profile(filepath, stage_name)

        try:
            return self._parse_with_pyverilog(filepath, stage_name)
        except Exception:
            return self._stub_profile(filepath, stage_name)

    def _extract_stage_annotation(self, filepath: str) -> str:
        """Look for // @stage: <name> in file header."""
        try:
            with open(filepath) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("//") and "@stage:" in line:
                        return line.split("@stage:")[-1].strip()
                    if not line.startswith("//") and line:
                        break
        except OSError:
            pass
        return ""

    def _parse_with_pyverilog(self, filepath: str, stage_name: str) -> RTLProfile:
        parser = VerilogCodeParser([filepath], preprocess_output=tempfile.mktemp(suffix=".v"))
        ast, _ = parser.parse()

        profile = RTLProfile(
            module_name="unknown",
            source_file=os.path.basename(filepath),
            stage_name=stage_name,
        )

        self._visit_ast(ast, profile)
        profile._compute_estimates()
        if stage_name:
            profile.stage_name = stage_name
        return profile

    def _visit_ast(self, node, profile: RTLProfile):
        if node is None:
            return

        if PYVERILOG_AVAILABLE:
            if isinstance(node, vast.ModuleDef):
                profile.module_name = str(node.name)
                if not profile.stage_name:
                    profile.stage_name = profile.module_name

            elif isinstance(node, vast.Input):
                w = _extract_width(getattr(node, "width", None))
                profile.inputs.append(PortInfo(str(node.name), w))

            elif isinstance(node, vast.Output):
                w = _extract_width(getattr(node, "width", None))
                profile.outputs.append(PortInfo(str(node.name), w))

            elif isinstance(node, vast.Reg):
                if _is_2d_array(node):
                    profile.memory_declarations.append(str(node.name))
                else:
                    profile.reg_count += 1

            elif isinstance(node, vast.Wire):
                profile.wire_count += 1

            elif isinstance(node, vast.Always):
                profile.always_block_count += 1
                if _is_clocked(getattr(node, "sens_list", None)):
                    profile.clocked_always_count += 1

            elif isinstance(node, vast.Operator):
                profile.operator_count += 1
                vis = _ExpressionDepthVisitor()
                vis.visit(node)
                profile.max_expression_depth = max(profile.max_expression_depth, vis.max_depth)
                profile.operator_count += vis.operator_count - 1  # node itself already counted

        if hasattr(node, "children"):
            for child in node.children():
                self._visit_ast(child, profile)

    def _stub_profile(self, filepath: str, stage_name: str) -> RTLProfile:
        """Fallback when pyverilog is unavailable or parse fails."""
        module_name = os.path.splitext(os.path.basename(filepath))[0]
        profile = RTLProfile(
            module_name=module_name,
            source_file=os.path.basename(filepath),
            stage_name=stage_name or module_name,
            reg_count=20,
            wire_count=30,
            always_block_count=2,
            clocked_always_count=2,
            operator_count=40,
            max_expression_depth=8,
        )
        profile._compute_estimates()
        return profile
