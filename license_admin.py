#!/usr/bin/env python3
"""Administrative tooling for license key generation and issuance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import licensing


def _load_private_key(path: Path) -> dict[str, Any]:
    private_key = licensing.load_json_file(path)
    for field_name in ("n", "e", "d"):
        if field_name not in private_key:
            raise licensing.LicenseError(f"Private key file is missing '{field_name}': {path}")
    return private_key


def command_generate_keypair(args: argparse.Namespace) -> int:
    public_key, private_key = licensing.generate_keypair(bits=args.bits)
    licensing.write_json_file(Path(args.public_out), public_key)
    licensing.write_json_file(Path(args.private_out), private_key)
    print(f"Public key: {args.public_out}")
    print(f"Private key: {args.private_out}")
    return 0


def command_issue(args: argparse.Namespace) -> int:
    private_key = _load_private_key(Path(args.private_key))
    payload = licensing.build_license_payload(
        customer=args.customer,
        email=args.email,
        expires_at=args.expires_at,
        machine_id=args.machine_id,
        features=args.feature,
    )
    document = {
        "payload": payload,
        "signature": licensing.sign_payload(payload, private_key),
    }
    licensing.write_json_file(Path(args.output), document)
    print(f"License file: {args.output}")
    return 0


def command_inspect(args: argparse.Namespace) -> int:
    script_dir = Path(__file__).resolve().parent
    record = licensing.validate_license_file(
        Path(args.license_file),
        licensing.resolve_public_key_path(args.public_key_file, script_dir),
        machine_id=args.machine_id,
    )
    print(json.dumps(record.payload, indent=2, sort_keys=True))
    return 0


def command_machine_id(_: argparse.Namespace) -> int:
    print(licensing.current_machine_id())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="License administration tools.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    keygen = subparsers.add_parser("generate-keypair", help="Generate an RSA keypair.")
    keygen.add_argument("--bits", type=int, default=2048, help="RSA key size in bits.")
    keygen.add_argument("--public-out", required=True, help="Output path for the public key JSON.")
    keygen.add_argument("--private-out", required=True, help="Output path for the private key JSON.")
    keygen.set_defaults(func=command_generate_keypair)

    issue = subparsers.add_parser("issue", help="Issue a signed license file.")
    issue.add_argument("--private-key", required=True, help="Path to the private key JSON file.")
    issue.add_argument("--output", required=True, help="Where to write the signed license file.")
    issue.add_argument("--customer", required=True, help="Customer or company name.")
    issue.add_argument("--email", required=True, help="Customer email address.")
    issue.add_argument("--expires-at", help="Expiry date in YYYY-MM-DD format.")
    issue.add_argument("--machine-id", help="Optional machine binding. Use the machine-id command to inspect a host.")
    issue.add_argument("--feature", action="append", default=[], help="Feature flag to embed in the license. Repeat for multiple values.")
    issue.set_defaults(func=command_issue)

    inspect_license = subparsers.add_parser("inspect", help="Validate and print a license file.")
    inspect_license.add_argument("--license-file", required=True, help="Path to the license JSON file.")
    inspect_license.add_argument("--public-key-file", help="Override the public key file used for verification.")
    inspect_license.add_argument("--machine-id", help="Override the current machine id during validation.")
    inspect_license.set_defaults(func=command_inspect)

    machine_id = subparsers.add_parser("machine-id", help="Print the current machine id used for bound licenses.")
    machine_id.set_defaults(func=command_machine_id)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except licensing.LicenseError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())