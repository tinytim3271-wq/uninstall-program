#!/usr/bin/env python3
"""Windows installer for Reliable clean slate uninstall."""

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Callable, Dict, Optional

import licensing


PROGRAM_NAME = "Reliable clean slate uninstall"
RUNTIME_FILES = ("uninstall.py", "licensing.py", "vendor_public_key.json", "README.md", "LICENSE")


def resolve_default_destination() -> Path:
    """Return the default installation directory."""
    d_drive = Path("D:/")
    if d_drive.exists():
        return d_drive / PROGRAM_NAME
    return Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / PROGRAM_NAME


def ensure_runtime_files(source_dir: Path) -> None:
    """Ensure the installer source directory contains all required files."""
    for file_name in RUNTIME_FILES:
        source_path = source_dir / file_name
        if not source_path.exists():
            raise FileNotFoundError(f"Required source file not found: {source_path}")


def build_launcher_contents() -> str:
    """Return the batch launcher content for the installed program."""
    return (
        "@echo off\n"
        "set \"SCRIPT_DIR=%~dp0\"\n"
        "where py >nul 2>nul\n"
        "if %errorlevel%==0 (\n"
        "   py -3 \"%SCRIPT_DIR%uninstall.py\" %*\n"
        ") else (\n"
        "   python \"%SCRIPT_DIR%uninstall.py\" %*\n"
        ")\n"
    )


def write_launcher(destination: Path) -> Path:
    """Write the installed batch launcher and return its path."""
    launcher_path = destination / f"{PROGRAM_NAME}.cmd"
    with launcher_path.open("w", encoding="ascii", newline="\r\n") as launcher_file:
        launcher_file.write(build_launcher_contents())
    return launcher_path


def read_user_path_from_registry() -> str:
    """Return the current user PATH value on Windows."""
    try:
        import winreg  # type: ignore[import]
    except ImportError:
        return os.environ.get("PATH", "")

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as key:
            return winreg.QueryValueEx(key, "Path")[0]
    except OSError:
        return ""


def write_user_path_to_registry(path_value: str) -> None:
    """Persist the user PATH value on Windows."""
    try:
        import winreg  # type: ignore[import]
    except ImportError as exc:
        raise OSError("Windows registry support is unavailable for PATH updates.") from exc

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        "Environment",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, path_value)


def compute_updated_user_path(destination: Path, current_path: str) -> Optional[str]:
    """Return an updated PATH string, or None when *destination* is already present."""
    destination_str = str(destination)
    normalized_destination = os.path.normcase(os.path.normpath(destination_str))
    entries = [entry for entry in current_path.split(";") if entry]

    for entry in entries:
        if os.path.normcase(os.path.normpath(entry)) == normalized_destination:
            return None

    if not current_path:
        return destination_str
    return f"{current_path};{destination_str}"


def install_program(
    source_dir: Path,
    destination: Optional[Path] = None,
    add_to_path: bool = False,
    license_source: Optional[Path] = None,
    public_key_path: Optional[Path] = None,
    machine_id: Optional[str] = None,
    read_user_path: Optional[Callable[[], str]] = None,
    write_user_path: Optional[Callable[[str], None]] = None,
) -> Dict[str, object]:
    """Install the program into *destination* and optionally add it to PATH."""
    source_dir = source_dir.resolve()
    ensure_runtime_files(source_dir)

    if license_source is None:
        bundled_license = source_dir / licensing.LICENSE_FILENAME
        if bundled_license.exists():
            license_source = bundled_license

    if license_source is not None:
        key_path = licensing.resolve_public_key_path(public_key_path, source_dir)
        licensing.validate_license_file(license_source, key_path, machine_id)
    else:
        key_path = licensing.resolve_public_key_path(public_key_path, source_dir)

    install_destination = destination or resolve_default_destination()
    install_destination.mkdir(parents=True, exist_ok=True)

    for file_name in RUNTIME_FILES:
        shutil.copy2(source_dir / file_name, install_destination / file_name)

    if key_path != source_dir / licensing.PUBLIC_KEY_FILENAME:
        shutil.copy2(key_path, install_destination / licensing.PUBLIC_KEY_FILENAME)

    launcher_path = write_launcher(install_destination)
    installed_license_path: Optional[Path] = None

    if license_source is not None:
        installed_license_path = licensing.install_license_file(license_source, install_destination)

    path_added = False
    path_already_present = False

    if add_to_path:
        read_user_path = read_user_path or read_user_path_from_registry
        write_user_path = write_user_path or write_user_path_to_registry
        current_path = read_user_path()
        updated_path = compute_updated_user_path(install_destination, current_path)
        if updated_path is None:
            path_already_present = True
        else:
            write_user_path(updated_path)
            path_added = True

    return {
        "destination": install_destination,
        "launcher_path": launcher_path,
        "installed_license_path": installed_license_path,
        "path_added": path_added,
        "path_already_present": path_already_present,
    }


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install Reliable clean slate uninstall on Windows."
    )
    parser.add_argument(
        "-Destination",
        "--destination",
        dest="destination",
        help="Directory where the program should be installed.",
    )
    parser.add_argument(
        "-AddToPath",
        "--add-to-path",
        dest="add_to_path",
        action="store_true",
        help="Append the install directory to the current user's PATH.",
    )
    parser.add_argument(
        "--license-file",
        help="Optional signed license file to validate and install with the product.",
    )
    parser.add_argument(
        "--public-key-file",
        help="Optional public key file override used to validate the license.",
    )
    parser.add_argument(
        "--machine-id",
        help="Optional machine id override used to validate a bound license.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    source_dir = Path(__file__).resolve().parent
    destination = Path(args.destination) if args.destination else None

    try:
        result = install_program(
            source_dir,
            destination,
            args.add_to_path,
            license_source=Path(args.license_file) if args.license_file else None,
            public_key_path=args.public_key_file,
            machine_id=args.machine_id,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if result["path_added"]:
        print(f"Added to user PATH: {result['destination']}")
    elif result["path_already_present"]:
        print(f"Already present in user PATH: {result['destination']}")

    print(f"Installed {PROGRAM_NAME} to {result['destination']}")
    print(f"Launcher: {result['launcher_path']}")
    if result["installed_license_path"]:
        print(f"License: {result['installed_license_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())