"""The `expkit` command line. Phase 0 ships `version`, `doctor` and `spike-report`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from expkit import __version__, doctor, spike


def _cmd_version(_args) -> int:
    print(__version__)
    return 0


def _cmd_doctor(args) -> int:
    checks = doctor.run(hosts=not args.offline)
    for c in checks:
        print(f"{'ok ' if c.ok else 'BAD'}  {c.name:<24} {c.detail}")
    return 0 if all(c.ok for c in checks) else 1


def _cmd_spike_report(args) -> int:
    for path in args.files:
        raw = json.loads(Path(path).read_text())
        env = raw.get("env") or Path(path).stem
        vs = spike.verdicts(raw, interval_s=args.interval, planned_s=args.planned_minutes * 60)
        print(spike.to_markdown(env, raw, vs))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="expkit", description=__doc__)
    p.add_argument("--version", action="version", version=f"expkit {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("version", help="print the expkit version").set_defaults(func=_cmd_version)

    d = sub.add_parser("doctor", help="check this control machine is ready")
    d.add_argument("--offline", action="store_true", help="skip the outbound HTTPS checks")
    d.set_defaults(func=_cmd_doctor)

    s = sub.add_parser("spike-report", help="turn spike results JSON into verdicts (markdown)")
    s.add_argument(
        "files", nargs="+", help="spike-results/<env>.json written by the spike playbook"
    )
    s.add_argument("--interval", type=int, default=60, help="heartbeat interval, seconds")
    s.add_argument("--planned-minutes", type=int, default=120, help="heartbeat planned lifetime")
    s.set_defaults(func=_cmd_spike_report)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
