import argparse
import json


def main():
    parser = argparse.ArgumentParser(description="CooperBench activity-trail smoke pilot")
    parser.add_argument("command", choices=["prepare", "verify", "pilot", "report"])
    args = parser.parse_args()
    from bench.pilot import ARTIFACTS, prepare, run_pilot, verify

    if args.command == "prepare":
        print(json.dumps([str(path) for path in prepare()], indent=2))
    elif args.command == "verify":
        verify()
    elif args.command == "pilot":
        run_pilot()
    else:
        from bench.report import report

        report(ARTIFACTS / "pilot")
