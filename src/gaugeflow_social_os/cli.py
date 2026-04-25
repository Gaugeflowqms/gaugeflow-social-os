import argparse
from pathlib import Path

from gaugeflow_social_os.data import INITIATIVES, RITUAL_SLOTS, SIGNALS, TEAM_MEMBERS
from gaugeflow_social_os.engine import (
    ValidationError,
    build_weekly_plan,
    critical_chain_points,
    member_health_scores,
    validate_inputs,
)
from gaugeflow_social_os.exporters import export_initiatives_csv, export_plan_json, export_summary_markdown


def cmd_validate() -> int:
    try:
        validate_inputs(TEAM_MEMBERS, INITIATIVES)
    except ValidationError as exc:
        print(f"INVALID: {exc}")
        return 1
    print("VALID: team ownership and initiative dependency graph are consistent")
    return 0


def cmd_health() -> int:
    try:
        scores = member_health_scores(TEAM_MEMBERS, SIGNALS)
    except ValidationError as exc:
        print(f"INVALID: {exc}")
        return 1
    print("Member health scores:")
    for member_id, score in scores.items():
        print(f"  {member_id}: {score}")
    return 0


def cmd_plan() -> int:
    try:
        plan = build_weekly_plan(TEAM_MEMBERS, INITIATIVES, RITUAL_SLOTS)
    except ValidationError as exc:
        print(f"INVALID: {exc}")
        return 1

    print("Weekly plan allocations:")
    for item in plan.items:
        print(f"  {item.ritual_slot_id}: {item.initiative_id} ({item.owner_id}) {item.allocated_points} pts")
    if plan.unplanned_initiatives:
        print("Unplanned initiatives: " + ", ".join(plan.unplanned_initiatives))
    return 0


def cmd_critical_chain() -> int:
    try:
        chain, points = critical_chain_points(INITIATIVES)
    except ValidationError as exc:
        print(f"INVALID: {exc}")
        return 1
    print(f"Critical chain ({points} pts): {' -> '.join(chain)}")
    return 0


def cmd_export(outdir: str) -> int:
    out_path = Path(outdir)
    csv_path = out_path / "gaua17_initiatives.csv"
    md_path = out_path / "gaua17_social_os_summary.md"
    json_path = out_path / "gaua17_weekly_plan.json"

    export_initiatives_csv(INITIATIVES, csv_path)
    export_summary_markdown(TEAM_MEMBERS, INITIATIVES, SIGNALS, RITUAL_SLOTS, md_path)
    export_plan_json(TEAM_MEMBERS, INITIATIVES, RITUAL_SLOTS, json_path)

    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gaugeflow-social-os", description="GaugeFlow Social OS toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate", help="Validate initiative ownership and dependencies")
    sub.add_parser("health", help="Show member health scores")
    sub.add_parser("plan", help="Build weekly ritual plan")
    sub.add_parser("critical-chain", help="Compute critical dependency chain")

    export_parser = sub.add_parser("export", help="Export CSV/Markdown/JSON artifacts")
    export_parser.add_argument("--outdir", default="outputs", help="Output directory")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "validate":
        return cmd_validate()
    if args.command == "health":
        return cmd_health()
    if args.command == "plan":
        return cmd_plan()
    if args.command == "critical-chain":
        return cmd_critical_chain()
    if args.command == "export":
        return cmd_export(args.outdir)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
