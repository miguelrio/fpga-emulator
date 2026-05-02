#!/usr/bin/env python3
"""
FPGA Network Router Simulator
Entry point. Run with --help for options.
"""
import argparse
import os
import sys


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="FPGA Network Router Simulator — estimates cycles, memory, and ASIC PPA"
    )
    p.add_argument("--headless", action="store_true",
                   help="Run without GUI (batch mode)")
    p.add_argument("--no-gui", action="store_true",
                   help="Alias for --headless")
    p.add_argument("--tech-node", default="7nm", metavar="NODE",
                   help="ASIC tech node for PPA estimation (28nm/16nm/7nm/5nm) [default: 7nm]")
    p.add_argument("--packet-count", type=int, default=16, metavar="N",
                   help="Number of packets to simulate (default: 16 = all permutations)")
    p.add_argument("--output-csv", metavar="PATH",
                   help="Export PPA report to CSV file")
    p.add_argument("--output-json", metavar="PATH",
                   help="Export PPA report to JSON file")
    p.add_argument("--rtl-dir", default=os.path.join("rtl", "plugins"), metavar="DIR",
                   help="Directory containing Verilog plugin files to load")
    p.add_argument("--no-rtl-plugins", action="store_true",
                   help="Skip loading RTL plugins, use built-in stages only")
    return p


def run_headless(args):
    from sim.pipeline import build_default_pipeline
    from sim.packet import PacketFactory
    from ppa.estimator import PPAEstimator
    from ppa.report import format_report, export_csv, export_json
    from rtl.plugin_loader import VerilogPluginLoader

    engine = build_default_pipeline()

    if not args.no_rtl_plugins and os.path.isdir(args.rtl_dir):
        loader = VerilogPluginLoader(args.rtl_dir, pipeline=engine)
        loaded = loader.load_all()
        if loaded:
            print(f"[RTL] Loaded {len(loaded)} plugin(s): {[p.module_name for p in loaded]}")

    packets = PacketFactory.generate_permutations()
    if args.packet_count != 16:
        extra = [PacketFactory.make() for _ in range(max(0, args.packet_count - 16))]
        packets = (packets + extra)[:args.packet_count]

    print(f"[SIM] Running {len(packets)} packets through pipeline...")
    engine.run(packets, max_cycles=args.packet_count * 300)

    completed = len(engine.completed)
    dropped = len(engine.dropped)
    total = len(packets)
    print(f"[SIM] Done. Completed: {completed}/{total}  Dropped: {dropped}/{total}  "
          f"Cycles: {engine.clock.cycle}")

    stage_metrics = [s.metrics for s in engine.get_stages()]
    estimator = PPAEstimator(args.tech_node)
    ppa = estimator.estimate(stage_metrics)

    print()
    from ppa.report import format_report
    print(format_report(ppa))

    if args.output_csv:
        export_csv(ppa, args.output_csv)
        print(f"\n[OUT] CSV written to {args.output_csv}")
    if args.output_json:
        export_json(ppa, args.output_json)
        print(f"[OUT] JSON written to {args.output_json}")


def run_gui(args):
    from sim.pipeline import build_default_pipeline
    from sim.packet import PacketFactory
    from rtl.plugin_loader import VerilogPluginLoader
    from gui.app import FPGASimApp

    engine = build_default_pipeline()

    reload_callback = None

    def on_plugin_reload(profile):
        from sim.events import SimEvent
        ev = SimEvent(
            cycle=engine.clock.cycle,
            packet_id=-1,
            stage_name=profile.stage_name,
            event_type="plugin_reloaded",
            payload={"module": profile.module_name},
        )
        engine.event_queue.put(ev)

    if not args.no_rtl_plugins and os.path.isdir(args.rtl_dir):
        loader = VerilogPluginLoader(args.rtl_dir, pipeline=engine, on_reload=on_plugin_reload)
        loaded = loader.load_all()
        loader.start_watching()
        if loaded:
            print(f"[RTL] Loaded {len(loaded)} plugin(s), watching {args.rtl_dir} for changes")

    app = FPGASimApp(engine)

    # Pre-inject one set of permutation packets
    packets = PacketFactory.generate_permutations()
    for p in packets:
        app._packet_map[p.pkt_id] = p
        engine.enqueue_packet(p)

    print("[GUI] Starting Pygame window. Q to quit, click a stage for details, N to cycle tech node.")
    app.run()

    if not args.no_rtl_plugins and os.path.isdir(args.rtl_dir):
        try:
            loader.stop_watching()
        except Exception:
            pass


def main():
    parser = build_parser()
    args = parser.parse_args()

    headless = args.headless or args.no_gui

    if headless:
        run_headless(args)
    else:
        run_gui(args)


if __name__ == "__main__":
    main()
