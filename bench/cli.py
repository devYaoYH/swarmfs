import argparse
import json


def main():
    parser = argparse.ArgumentParser(description="CooperBench activity-trail smoke pilot")
    parser.add_argument(
        "command", choices=["prepare", "verify", "pilot", "report", "smoke", "shared-check"]
    )
    parser.add_argument("--config", help="TOML profile (default: pilot.toml)")
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
    else:
        from bench.report import report

        report(experiment_output(cfg))
