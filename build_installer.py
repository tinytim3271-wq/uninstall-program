#!/usr/bin/env python3
"""Build a distributable Windows installer bundle."""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import licensing


BUNDLE_FILES = (
    "install.cmd",
    "install.ps1",
    "install.py",
    "licensing.py",
    "uninstall.py",
    "README.md",
    "LICENSE",
    "vendor_public_key.json",
)


def build_bundle(
    source_dir: Path,
    output_dir: Path,
    bundle_name: str = "Reliable-clean-slate-uninstall-windows",
    license_file: Optional[Path] = None,
    public_key_file: Optional[Path] = None,
    machine_id: Optional[str] = None,
) -> dict[str, Any]:
    """Create a production bundle directory and zip archive."""
    source_dir = source_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = output_dir / bundle_name

    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True)

    copied_files: list[str] = []
    resolved_public_key_path = licensing.resolve_public_key_path(
        str(public_key_file) if public_key_file else None,
        source_dir,
    )

    for file_name in BUNDLE_FILES:
        source_path = source_dir / file_name
        if not source_path.exists():
            raise FileNotFoundError(f"Bundle source file not found: {source_path}")
        shutil.copy2(source_path, bundle_dir / file_name)
        copied_files.append(file_name)

    if resolved_public_key_path != source_dir / licensing.PUBLIC_KEY_FILENAME:
        shutil.copy2(resolved_public_key_path, bundle_dir / licensing.PUBLIC_KEY_FILENAME)

    included_license_path: Optional[Path] = None
    if license_file is not None:
        licensing.validate_license_file(license_file, resolved_public_key_path, machine_id)
        included_license_path = licensing.install_license_file(license_file, bundle_dir)
        copied_files.append(included_license_path.name)

    manifest = {
        "product": licensing.PRODUCT_NAME,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "bundle_name": bundle_name,
        "license_included": included_license_path is not None,
        "files": copied_files,
    }
    licensing.write_json_file(bundle_dir / "bundle_manifest.json", manifest)

    archive_path = Path(shutil.make_archive(str(output_dir / bundle_name), "zip", output_dir, bundle_name))
    return {
        "bundle_dir": bundle_dir,
        "archive_path": archive_path,
        "included_license_path": included_license_path,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a production installer bundle.")
    parser.add_argument("--output-dir", default="dist", help="Directory where the bundle and zip should be created.")
    parser.add_argument("--bundle-name", default="Reliable-clean-slate-uninstall-windows", help="Bundle directory and zip file name.")
    parser.add_argument("--license-file", help="Optional license file to validate and embed into the bundle.")
    parser.add_argument("--public-key-file", help="Optional public key file override for license validation.")
    parser.add_argument("--machine-id", help="Optional machine id override for validating a bound license.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    source_dir = Path(__file__).resolve().parent

    try:
        result = build_bundle(
            source_dir=source_dir,
            output_dir=Path(args.output_dir),
            bundle_name=args.bundle_name,
            license_file=Path(args.license_file) if args.license_file else None,
            public_key_file=Path(args.public_key_file) if args.public_key_file else None,
            machine_id=args.machine_id,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Bundle directory: {result['bundle_dir']}")
    print(f"Archive: {result['archive_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())