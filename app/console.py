from __future__ import annotations

import argparse
import json

from app.admin import audit_window, create_account, load_defaults, set_defaults
from app.config import QueryOptions
from app.main import service


def cmd_query(args: argparse.Namespace) -> None:
    defaults = load_defaults()
    options = QueryOptions(
        include_identifiers=not args.disable_identifiers,
        include_valuation=not args.disable_valuation,
        include_owner=not args.disable_owner,
        include_records=not args.disable_records,
        include_pricing_history=not args.disable_pricing,
        source_census=not args.no_census,
        source_usps=not args.no_usps,
        source_regrid=not args.no_regrid,
        source_official=not args.no_official,
        min_confidence=args.min_confidence if args.min_confidence is not None else defaults.min_confidence,
        max_validation_severity=args.max_severity or defaults.max_validation_severity,
    )
    rec = service.evaluate_address(args.address, options=options, actor=args.actor)
    print(json.dumps(rec, default=lambda o: o.__dict__, indent=2))


def cmd_create_account(args: argparse.Namespace) -> None:
    print(json.dumps(create_account(args.username, args.role, args.account_type), indent=2))


def cmd_audit(args: argparse.Namespace) -> None:
    print(json.dumps(audit_window(args.start_iso, args.end_iso), indent=2))


def cmd_set_defaults(args: argparse.Namespace) -> None:
    opts = QueryOptions(min_confidence=args.min_confidence, max_validation_severity=args.max_severity)
    print(json.dumps(set_defaults(opts), indent=2))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Property Intelligence console interface')
    sub = p.add_subparsers(dest='cmd', required=True)

    q = sub.add_parser('query')
    q.add_argument('address')
    q.add_argument('--actor', default='console_user')
    q.add_argument('--disable-identifiers', action='store_true')
    q.add_argument('--disable-valuation', action='store_true')
    q.add_argument('--disable-owner', action='store_true')
    q.add_argument('--disable-records', action='store_true')
    q.add_argument('--disable-pricing', action='store_true')
    q.add_argument('--no-census', action='store_true')
    q.add_argument('--no-usps', action='store_true')
    q.add_argument('--no-regrid', action='store_true')
    q.add_argument('--no-official', action='store_true')
    q.add_argument('--min-confidence', type=float)
    q.add_argument('--max-severity', choices=['info', 'warning', 'critical'])
    q.set_defaults(func=cmd_query)

    c = sub.add_parser('create-account')
    c.add_argument('username')
    c.add_argument('role')
    c.add_argument('--account-type', default='human')
    c.set_defaults(func=cmd_create_account)

    a = sub.add_parser('audit')
    a.add_argument('start_iso')
    a.add_argument('end_iso')
    a.set_defaults(func=cmd_audit)

    d = sub.add_parser('set-defaults')
    d.add_argument('--min-confidence', type=float, default=0.0)
    d.add_argument('--max-severity', choices=['info', 'warning', 'critical'], default='critical')
    d.set_defaults(func=cmd_set_defaults)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
