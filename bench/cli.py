import argparse
import json


def main():
    parser = argparse.ArgumentParser(description="CooperBench activity-trail smoke pilot")
    parser.add_argument(
        "command",
        choices=["prepare", "verify", "pilot", "report", "smoke", "shared-check", "compare"],
    )
    parser.add_argument("--config", help="TOML profile (default: pilot.toml)")
    parser.add_argument("--team", help="Saved shared-team experiment directory for compare")
    parser.add_argument("--output", help="Output directory for compare")
    args = parser.parse_args()
    from bench.pilot import config, experiment_output, prepare, run_pilot, verify

    cfg = config(args.config)

    if args.command == "prepare":
        print(json.dumps([str(path) for path in prepare(cfg)], indent=2))
    elif args.command == "verify":
        verify(cfg)
    elif args.command == "pilot":
        run_pilot(cfg)
    elif args.command == "smoke":
        from bench.smoke import smoke

        print(json.dumps(smoke(cfg), indent=2))
    elif args.command == "shared-check":
        from bench.shared_check import shared_check

        print(json.dumps(shared_check(cfg), indent=2))
    elif args.command == "compare":
        from pathlib import Path

        from bench.compare import compare

        if not args.team or not args.output:
            parser.error("compare needs --team and --output; --config selects the solo experiment")
        compare(Path(args.team), experiment_output(cfg), Path(args.output))
    else:
        from bench.report import report

        report(experiment_output(cfg))
