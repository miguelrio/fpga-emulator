# FPGA Network Router Simulator

A Python application that simulates a TCP/IP packet processing pipeline on an FPGA, estimating clock cycles, memory usage, and full ASIC Power/Performance/Area (PPA) at multiple technology nodes. A Pygame GUI animates packets flowing through the pipeline in real time.

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Quick Start](#quick-start)
3. [Architecture Overview](#architecture-overview)
4. [The Packet Processing Pipeline](#the-packet-processing-pipeline)
5. [Inserting New Verilog Modules](#inserting-new-verilog-modules)
6. [Using the GUI](#using-the-gui)
7. [ASIC PPA Estimation](#asic-ppa-estimation)
8. [Running in Headless Mode](#running-in-headless-mode)
9. [Running Tests](#running-tests)
10. [Project Structure](#project-structure)

---

## What It Does

The simulator models the journey of a network packet from the moment it arrives at an Ethernet interface to the moment it leaves through an outgoing one. At each stage of the pipeline it tracks:

- **Clock cycles** consumed (latency)
- **Memory** used (buffers, routing tables, BRAMs)
- **FPGA resources** estimated (LUTs, Flip-Flops, BRAMs)

It also estimates how the same design would perform as a custom silicon chip (ASIC) at 28 nm, 16 nm, 7 nm, or 5 nm, computing maximum clock frequency (Fmax), die area in mm², and power consumption in mW.

You can swap any pipeline stage for your own Verilog RTL simply by dropping a `.v` file into a folder — the simulator parses it, extracts resource estimates, and hot-replaces the stage while the GUI is running.

---

## Quick Start

**Requirements:** Python 3.10+

```bash
# 1. Clone the repo
git clone https://github.com/miguelrio/fpga-emulator.git
cd fpga-emulator

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch the GUI
python3 main.py

# 4. Or run headless and get a PPA report
python3 main.py --headless --tech-node 7nm --output-csv report.csv
```

---

## Architecture Overview

The simulator is split into four independent subsystems that communicate through well-defined interfaces:

```
┌─────────────────────────────────────────────────────────────────┐
│                        main.py (CLI)                            │
└───────┬─────────────────┬──────────────────┬────────────────────┘
        │                 │                  │
        ▼                 ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐
│   sim/       │  │   rtl/       │  │   ppa/                   │
│  Pipeline    │◄─│  RTL Plugin  │  │  ASIC Estimator          │
│  Engine      │  │  Loader      │  │  (Fmax, area, power)     │
│  (thread)    │  │  (watchdog)  │  └──────────────────────────┘
└──────┬───────┘  └──────────────┘
       │ queue.Queue (SimEvents)
       ▼
┌──────────────────────────────────────────────────────────────┐
│   gui/  (Pygame, 60 fps, main thread)                        │
│   Packet token animation · Metrics sidebar · Scrub timeline  │
└──────────────────────────────────────────────────────────────┘
```

**Threading model:** The simulation engine runs on a background thread and communicates with the GUI exclusively through a thread-safe `queue.Queue`. The GUI never touches simulation state directly; it reads a lock-protected snapshot once per frame.

---

## The Packet Processing Pipeline

The default pipeline has four stages executed in order. Each stage is a Python class that inherits from `PipelineStage`.

```
Ethernet frame
      │
      ▼
┌─────────────┐     ┌────────────────┐     ┌─────────────┐     ┌──────────┐
│  MAC RX     │────►│ Header Parser  │────►│ FIB Lookup  │────►│  MAC TX  │
│  (CRC, IFG) │     │ (IPv4/v6 dispatch)   │ (LPM route) │     │ (cksum,  │
│  12 cycles  │     │  4 cycles      │     │  8 cycles   │     │ serialize│
│  2 KB buf   │     │  256 B buf     │     │  64 KB table│     │  6 cycles│
└─────────────┘     └────────────────┘     └─────────────┘     └──────────┘
```

### Stage descriptions

| Stage | Class | Latency | Memory | What it does |
|---|---|---|---|---|
| MAC RX | `MACRxStage` | 12 cycles | 2 KB | Ethernet frame reception, CRC-32 check, inter-frame gap enforcement. Drops runt frames (< 64 B). |
| Header Parser | `HeaderParserStage` | 4 cycles | 256 B | Parses Ethernet/IP/TCP/UDP headers, dispatches by EtherType. Drops frames that are too short to contain a valid IP header. |
| FIB Lookup | `FIBLookupStage` | 8 cycles | ~64 KB | Longest-prefix-match (LPM) against a routing table. Drops packets with no matching route. Attaches `next_hop` and `interface` to the packet metadata. |
| MAC TX | `MACTxStage` | 6 cycles | 4 KB | Recalculates IPv4 checksum, serializes the frame, and places it on the outgoing interface. |

### Packet representation

Every packet is an immutable `Packet` dataclass defined in `sim/packet.py`:

```python
@dataclass(frozen=True)
class Packet:
    pkt_id: int
    timestamp_cycle: int
    src_ip: str
    dst_ip: str
    ip_version: int      # 4 or 6
    proto: str           # 'tcp' | 'udp'
    size_bytes: int
    raw_bytes: bytes
    metadata: dict       # extended by FIB stage (next_hop, interface)
```

The `PacketFactory` generates packets using [scapy](https://scapy.net/) and covers all 16 combinations of `{IPv4, IPv6} × {TCP, UDP} × {64 B, 512 B, 1500 B, 9000 B}`.

### Event log and scrubbing

Every time a packet enters or exits a stage, the engine records a `SimEvent`:

```python
@dataclass
class SimEvent:
    cycle: int
    packet_id: int
    stage_name: str
    event_type: str    # 'enter' | 'exit' | 'drop' | 'lookup_hit' | 'complete'
    payload: dict
```

The full event log is stored in `SimClock.event_log`. The GUI timeline bar lets you drag backward in time — dragging calls `engine.scrub_to(cycle)`, which replays all events up to that cycle and reconstructs the visual state.

---

## Inserting New Verilog Modules

This is the primary extension mechanism. You can replace any built-in pipeline stage (or add a new one) by writing a Verilog file and dropping it into the `rtl/plugins/` directory.

### Step 1 — Add the stage annotation

Add a comment at the top of your Verilog file that tells the simulator which pipeline stage to replace:

```verilog
// @stage: fib_lookup
module my_fib_v2 ( ... );
```

The `@stage:` value must match the `name` field of the stage you want to replace. The built-in stage names are:

| `@stage:` value | Stage it replaces |
|---|---|
| `mac_rx` | MAC RX ingress |
| `header_parser` | Header parser |
| `fib_lookup` | FIB / routing table lookup |
| `mac_tx` | MAC TX egress |

If the `@stage:` annotation is absent, the simulator uses the Verilog `module` name instead. If no existing stage matches, the new stage is appended at the end of the pipeline.

### Step 2 — Write the Verilog module

The simulator does **not** simulate the Verilog at gate level. It parses the RTL to extract structural information and derives resource estimates. What it reads from your file:

| What the parser looks for | Maps to |
|---|---|
| `always @(posedge clk)` blocks | **Cycle latency** (one clocked always = one pipeline register stage) |
| `reg` declarations | **Flip-flop count** |
| `wire` declarations | **LUT input count** |
| 2-D `reg` arrays (e.g. `reg [31:0] mem [0:1023]`) | **BRAM count** |
| Arithmetic/logic operators in expressions | **LUT count** (via expression depth) |

A well-annotated example with comments:

```verilog
// @stage: fib_lookup
//
// Custom FIB lookup — 3-stage pipeline
// Latency: 3 cycles (3 clocked always blocks)
// Resources: ~4 BRAMs for the prefix/mask/nexthop tables
module my_fib_v2 (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [127:0] dst_ip,     // supports IPv6
    input  wire        in_valid,
    output reg  [31:0] next_hop,
    output reg  [7:0]  out_port,
    output reg         hit,
    output reg         out_valid
);
    // BRAMs — 2-D arrays are detected and counted
    reg [127:0] prefix_table [0:1023];
    reg [127:0] mask_table   [0:1023];
    reg [31:0]  nexthop_table[0:1023];
    reg [7:0]   port_table   [0:1023];

    reg [127:0] stage1_ip;
    reg         stage1_valid;

    // Pipeline stage 1 — latch input
    always @(posedge clk) begin
        stage1_ip    <= dst_ip;
        stage1_valid <= in_valid;
    end

    // Pipeline stage 2 — masked comparison
    reg [127:0] stage2_masked;
    always @(posedge clk)
        stage2_masked <= stage1_ip & mask_table[0];

    // Pipeline stage 3 — output
    always @(posedge clk) begin
        next_hop  <= nexthop_table[0];
        out_port  <= port_table[0];
        hit       <= stage1_valid;
        out_valid <= stage1_valid;
    end

endmodule
```

With 3 clocked `always` blocks and 4 two-dimensional arrays, the simulator will estimate:
- **Cycle latency:** 3
- **BRAM count:** 4
- **Resources:** derived from reg/wire/operator counts

### Step 3 — Drop the file into `rtl/plugins/`

```bash
cp my_fib_v2.v rtl/plugins/
```

**If the GUI is running:** the `watchdog` file-system watcher detects the new file within a second, parses it, and hot-replaces the stage. The affected stage box flashes **orange** for 2 seconds to confirm the reload. No restart required.

**If running headless:** the loader scans `rtl/plugins/` at startup before any packets are injected.

### Step 4 — Verify in the GUI

Click the stage box to open the detail popup. You will see:

- **Source:** `rtl_plugin:my_fib_v2.v` (purple badge)
- **Cycle latency** derived from clocked `always` count
- **BRAM / LUT / FF** estimates
- **PPA values** at the currently selected tech node
- A **"View Verilog source"** button that opens the `.v` file in your system text editor

### Resource estimation formulas

These are order-of-magnitude estimates, not synthesis-accurate values:

```
estimated_LUTs  = operator_count × 1.8 + wire_count × 0.3
estimated_FFs   = reg_count
estimated_BRAMs = count of 2-D reg arrays
cycle_latency   = count of clocked always blocks  (minimum 1)
```

### Tips for getting good estimates

- **Use clocked `always` blocks** (not combinational `always @(*)`) to represent pipeline stages — each one increments the latency count.
- **Use 2-D `reg` arrays** for any memory structure (lookup tables, FIFOs, packet buffers) — each is counted as one BRAM.
- **More operators = more LUTs.** Complex arithmetic in a single expression reads as high LUT usage, which is correct.
- The `@stage:` annotation is matched to the stage's Python `metrics.name`. If you want to create a brand-new stage rather than replace one, omit the annotation or use a name that doesn't match any existing stage.

---

## Using the GUI

```
python3 main.py
```

### Controls

| Action | Effect |
|---|---|
| **Click a stage box** | Opens the detail popup: full RTL profile, resource bars, PPA estimate, "View Verilog" button |
| **Click outside popup / Esc** | Closes the popup |
| **▶ Resume / ⏸ Pause button** | Starts or pauses the simulation |
| **+ Inject button** | Injects 16 new packets (all permutations) |
| **Speed slider** | 0.1× (slow) → 10× (fast) |
| **N key** | Cycles the ASIC tech node: 28 nm → 16 nm → 7 nm → 5 nm |
| **Drag timeline bar** | Scrubs to any past cycle and replays the animation |
| **Q / window close** | Quit |

### Visual language

| Visual | Meaning |
|---|---|
| **Green token** | IPv4 packet |
| **Blue token** | IPv6 packet |
| **Solid fill** | TCP |
| **Dashed outline** | UDP |
| **Wider token** | Larger packet (width ∝ log(size)) |
| **Glowing stage box** | Packet currently inside this stage |
| **Orange flash** | RTL plugin just hot-reloaded |
| **Red flash** | Packet dropped at this stage |
| **Green flash** | FIB lookup hit |
| **Purple border** | Stage driven by an RTL plugin (not built-in) |

### Metrics sidebar (right panel)

- **Simulation** — current cycle, packets completed, packets dropped
- **Pipeline stages** — packets in-flight and queued per stage
- **FPGA Resources** — LUT bar charts per stage
- **ASIC PPA** — Fmax, die area, dynamic power, leakage, total power at the selected tech node

---

## ASIC PPA Estimation

The estimator in `ppa/estimator.py` converts FPGA resource estimates to ASIC metrics using published parameters for each technology node.

### Gate Equivalent (GE) mapping

| Resource | GE weight |
|---|---|
| 1 LUT6 | 6 GE |
| 1 Flip-Flop | 4 GE |
| 1 BRAM (18 Kbit) | 3,000 GE |

### Tech-node parameters

| Node | Gate delay | Density | Vdd | Ceff (fF/GE) | Leakage (nW/GE) |
|---|---|---|---|---|---|
| 28 nm | 50 ps/level | 200 K GE/mm² | 0.90 V | 2.0 | 5.0 |
| 16 nm | 35 ps/level | 350 K GE/mm² | 0.80 V | 1.4 | 8.0 |
| 7 nm  | 20 ps/level | 100 M GE/mm² | 0.70 V | 0.9 | 15.0 |
| 5 nm  | 15 ps/level | 170 M GE/mm² | 0.65 V | 0.7 | 22.0 |

Parameters are sourced from published TSMC data and ISSCC proceedings.

### Formulas

**Performance (Fmax):**
```
t_cycle [ns] = logic_depth [levels] × gate_delay [ps] / 1000
Fmax [GHz]   = 1.0 / t_cycle
```

**Area:**
```
total_GE     = Σ (lut × 6 + ff × 4 + bram × 3000)  across all stages
die_area     = total_GE / gate_density [GE/mm²]
```

**Power:**
```
P_dynamic [mW] = 0.15 × Ceff [F] × Vdd² × Fmax [Hz] × total_GE × 1e3
P_leakage [mW] = leakage [nW/GE] × total_GE × 1e-6
P_total        = P_dynamic + P_leakage
```

The activity factor of 0.15 is typical for network routing logic.

---

## Running in Headless Mode

Headless mode skips the GUI, runs the full packet set through the pipeline, prints a PPA report, and optionally exports it.

```bash
# Basic run — prints PPA report to stdout
python3 main.py --headless

# Select tech node
python3 main.py --headless --tech-node 28nm

# Export to CSV and JSON
python3 main.py --headless --tech-node 7nm \
    --output-csv report.csv \
    --output-json report.json

# Run with a custom number of packets
python3 main.py --headless --packet-count 64

# Skip RTL plugin loading (use only built-in stages)
python3 main.py --headless --no-rtl-plugins

# Use a different RTL plugin directory
python3 main.py --headless --rtl-dir /path/to/my/verilog
```

The headless output looks like:

```
[RTL] Loaded 4 plugin(s): ['fib_lookup', 'header_parser', 'mac_rx', 'mac_tx']
[SIM] Running 16 packets through pipeline...
[SIM] Done. Completed: 16/16  Dropped: 0/16  Cycles: 24

╔══ ASIC PPA Estimate (7nm) ═══════════════════════╗
║  Total GE:           2,264
║  Fmax:              6.250 GHz
║  Die area:       0.000023 mm²
║  Dyn power:        0.9360 mW
║  Leakage:          0.0340 mW
║  Total power:      0.9700 mW
╠══ Per-stage breakdown ════════════════════════════════════╣
║  mac_rx                GE=   566  Fmax=6.25GHz  P=0.24mW
║  header_parser         GE=   566  Fmax=6.25GHz  P=0.24mW
║  fib_lookup            GE=   566  Fmax=6.25GHz  P=0.24mW
║  mac_tx                GE=   566  Fmax=6.25GHz  P=0.24mW
╚══════════════════════════════════════════════════════════╝
```

---

## Running Tests

```bash
# Run all 74 tests
python3 -m pytest tests/

# Run with coverage report
python3 -m pytest tests/ --cov=. --cov-report=term-missing

# Run a specific test file
python3 -m pytest tests/test_rtl_parser.py -v

# Run the packet permutation matrix only
python3 -m pytest tests/test_packet.py -v
```

The test suite covers:

| File | What is tested |
|---|---|
| `test_packet.py` | All 16 packet permutations, unique IDs, frozen dataclass, custom IPs |
| `test_fib.py` | LPM correctness, IPv6 routing, specific > default route, add route, loopback |
| `test_pipeline.py` | All 16 permutations through full pipeline, runt frame drop, FIB miss drop, stage replace/insert, event log growth, snapshot keys |
| `test_ppa.py` | 7 nm faster than 28 nm, smaller area at smaller node, power positive, Fmax in physical bounds, CSV export, tech-node interpolation |
| `test_rtl_parser.py` | `@stage:` annotation extraction, clocked always count, BRAM detection, stub fallback, all four example `.v` files parse cleanly |

---

## Project Structure

```
fpga-emulator/
│
├── main.py                    # CLI entry point
├── requirements.txt
│
├── sim/                       # Simulation engine (no GUI dependencies)
│   ├── events.py              # SimEvent dataclass
│   ├── clock.py               # SimClock: cycle counter, pause/resume, scrub
│   ├── packet.py              # Packet dataclass + PacketFactory (scapy)
│   ├── fib.py                 # ForwardingTable with LPM lookup
│   ├── stage.py               # PipelineStage ABC + 4 built-in stages + RTLPluginStage
│   └── pipeline.py            # PipelineEngine: tick loop, threading, event queue
│
├── rtl/                       # Verilog RTL integration
│   ├── parser.py              # VerilogPluginParser → RTLProfile (pyverilog AST)
│   ├── analyzer.py            # LogicDepthAnalyzer: critical path via networkx DAG
│   ├── plugin_loader.py       # VerilogPluginLoader: watchdog hot-reload
│   └── plugins/               # Drop .v files here
│       ├── mac_rx.v
│       ├── header_parser.v
│       ├── fib_lookup.v
│       └── mac_tx.v
│
├── ppa/                       # ASIC PPA estimation
│   ├── tech_nodes.py          # TechNodeParams for 28/16/7/5 nm
│   ├── estimator.py           # PPAEstimator: Fmax, area, power
│   └── report.py              # format_report(), export_csv(), export_json()
│
├── gui/                       # Pygame GUI (main thread only)
│   ├── app.py                 # FPGASimApp: 60 fps event loop, state machine
│   ├── renderer.py            # PipelineRenderer: layout, z-order draw, event→visual
│   ├── widgets.py             # StageBox, WireSegment, PacketToken, Button, Slider
│   ├── metrics_panel.py       # Right sidebar with live cycle/resource/PPA numbers
│   ├── timeline.py            # Scrub bar: drag → replay event log
│   ├── stage_detail.py        # Click-stage popup with RTL stats and PPA breakdown
│   └── colors.py              # Color palette constants
│
└── tests/
    ├── conftest.py
    ├── test_packet.py
    ├── test_fib.py
    ├── test_pipeline.py
    ├── test_ppa.py
    └── test_rtl_parser.py
```
