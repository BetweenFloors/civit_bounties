"""
CLI:  python -m civitai.cli bounty <id> [--html [output.html]]
"""

import argparse
import os
import sys
from pathlib import Path
from . import Civitai
from .client import CivitaiError
from .report import generate_html


def _fmt(label: str, value) -> str:
    return f"  {label:<22} {value}"


def cmd_bounty(args: argparse.Namespace) -> None:
    token = args.token or os.getenv("CIVITAI_TOKEN")
    civ = Civitai(api_token=token, domain=args.domain)

    print(f"Fetching bounty #{args.id} on {args.domain}…")
    try:
        report = civ.bounties.full_report(args.id)
    except CivitaiError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    s = report["stats"]
    entries = report["entries"]
    benefactors = report["benefactors"]

    # --- Console output -----------------------------------------------
    print(f"\n{'='*52}")
    print(f"  {s.name}")
    print(f"{'='*52}")
    print(_fmt("Status:", s.status))
    print(_fmt("Buzz total:", f"{s.total_buzz:,}"))
    print(_fmt("Starts:", s.starts_at[:10]))
    print(_fmt("Expires:", s.expires_at[:10]))

    print(f"\n--- Participation ---")
    print(_fmt("Entries:", s.entries))
    print(_fmt("Participants:", len({e.user for e in entries})))
    print(_fmt("Benefactors:", s.benefactors))
    print(_fmt("Favorites:", s.favorites))
    print(_fmt("Comments:", s.comments))

    if benefactors:
        print(f"\n--- Benefactors ---")
        for b in sorted(benefactors, key=lambda x: -x.unit_amount):
            print(f"  {b.user:<30} {b.unit_amount:>8,} Buzz")

    # Top participants
    from collections import Counter
    counts = Counter(e.user for e in entries)
    print(f"\n--- Top participants ---")
    for user, n in counts.most_common(10):
        print(f"  {user:<30} {n} entr{'ée' if n == 1 else 'ées'}")

    # --- HTML output --------------------------------------------------
    if args.html is not False:
        out = Path(args.html if isinstance(args.html, str) else f"bounty_{args.id}.html")
        generate_html(report, args.id, output_path=out)
        print(f"\nHTML report → {out.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="civitai", description="Civitai CLI")
    parser.add_argument("--token", help="API token (ou var CIVITAI_TOKEN)")
    parser.add_argument("--domain", default="red", choices=["red", "green"],
                        help="Domaine Civitai (default: red)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_bounty = sub.add_parser("bounty", help="Statistiques d'un bounty")
    p_bounty.add_argument("id", type=int, help="Bounty ID")
    p_bounty.add_argument(
        "--html", nargs="?", const=True, default=False, metavar="FILE",
        help="Générer un rapport HTML (optionnel: nom du fichier)"
    )
    p_bounty.set_defaults(func=cmd_bounty)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
