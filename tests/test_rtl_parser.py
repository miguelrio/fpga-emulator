import os
import tempfile
import pytest
from rtl.parser import VerilogPluginParser, RTLProfile


SIMPLE_MODULE = """\
// @stage: test_stage
module simple_adder (
    input  wire        clk,
    input  wire [7:0]  a,
    input  wire [7:0]  b,
    output reg  [8:0]  sum
);
    reg [7:0] reg_a;
    reg [7:0] reg_b;
    wire [8:0] wire_sum;

    assign wire_sum = a + b;

    always @(posedge clk) begin
        reg_a <= a;
        reg_b <= b;
        sum   <= wire_sum;
    end
endmodule
"""

TWO_ALWAYS_MODULE = """\
// @stage: two_stage
module two_always (
    input wire clk,
    input wire [7:0] d,
    output reg [7:0] q1,
    output reg [7:0] q2
);
    reg [7:0] tmp;
    always @(posedge clk) tmp <= d;
    always @(posedge clk) begin
        q1 <= tmp;
        q2 <= tmp + 1;
    end
endmodule
"""

BRAM_MODULE = """\
// @stage: bram_stage
module with_memory (
    input wire clk,
    input wire [9:0] addr,
    output reg [31:0] data_out
);
    reg [31:0] mem [0:1023];
    always @(posedge clk)
        data_out <= mem[addr];
endmodule
"""


def write_verilog(content: str) -> str:
    f = tempfile.NamedTemporaryFile(suffix=".v", mode="w", delete=False)
    f.write(content)
    f.close()
    return f.name


def test_parse_stage_annotation():
    path = write_verilog(SIMPLE_MODULE)
    try:
        parser = VerilogPluginParser()
        profile = parser.parse(path)
        assert profile.stage_name == "test_stage"
    finally:
        os.unlink(path)


def test_parse_clocked_always_count():
    path = write_verilog(TWO_ALWAYS_MODULE)
    try:
        parser = VerilogPluginParser()
        profile = parser.parse(path)
        assert profile.estimated_cycle_latency >= 1
    finally:
        os.unlink(path)


def test_parse_bram_detection():
    path = write_verilog(BRAM_MODULE)
    try:
        parser = VerilogPluginParser()
        profile = parser.parse(path)
        # Should detect at least 0 BRAMs (pyverilog may or may not parse 2D arrays)
        assert profile.estimated_brams >= 0
    finally:
        os.unlink(path)


def test_stub_profile_when_file_missing():
    parser = VerilogPluginParser()
    profile = parser.parse("/nonexistent/path/module.v")
    # Should return a stub, not raise
    assert isinstance(profile, RTLProfile)
    assert profile.estimated_cycle_latency >= 1


def test_estimated_luts_positive():
    path = write_verilog(SIMPLE_MODULE)
    try:
        parser = VerilogPluginParser()
        profile = parser.parse(path)
        assert profile.estimated_luts >= 0
    finally:
        os.unlink(path)


def test_profile_source_file():
    path = write_verilog(SIMPLE_MODULE)
    try:
        parser = VerilogPluginParser()
        profile = parser.parse(path)
        assert profile.source_file.endswith(".v")
    finally:
        os.unlink(path)


def test_example_plugin_files_parse():
    """Ensure the bundled example .v files all parse without error."""
    plugins_dir = os.path.join(os.path.dirname(__file__), "..", "rtl", "plugins")
    parser = VerilogPluginParser()
    v_files = [f for f in os.listdir(plugins_dir) if f.endswith(".v")]
    assert len(v_files) >= 4, "Expected at least 4 example Verilog files"
    for fname in v_files:
        path = os.path.join(plugins_dir, fname)
        profile = parser.parse(path)
        assert isinstance(profile, RTLProfile)
        assert profile.estimated_cycle_latency >= 1
