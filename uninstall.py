#!/usr/bin/env python3
"""
uninstall.py — Cross-platform program uninstaller.

Removes all traces of a named program (installation directories,
configuration files, cache, logs, desktop/menu shortcuts, and on
Windows, registry entries) so the program can be cleanly reinstalled.

Usage:
    python uninstall.py <program_name> [--dry-run] [--yes]

Options:
    --dry-run   List everything that would be removed without deleting anything.
    --yes, -y   Skip the confirmation prompt and remove immediately.
"""

import argparse
import os
import platform
import shutil
import sys

SYSTEM = platform.system()  # 'Linux', 'Darwin', or 'Windows'


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _expand(*parts: str) -> str:
    """Join and expand a path, returning an empty string on failure."""
    try:
        return os.path.expandvars(os.path.expanduser(os.path.join(*parts)))
    except Exception:
        return ""


def candidate_paths(program: str) -> list[str]:
    """Return a list of filesystem paths that may contain traces of *program*."""
    name_lower = program.lower()
    candidates: list[str] = []

    if SYSTEM == "Windows":
        pf64 = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        appdata = os.environ.get("APPDATA", "")
        localappdata = os.environ.get("LOCALAPPDATA", "")
        programdata = os.environ.get("ProgramData", r"C:\ProgramData")
        userprofile = os.environ.get("USERPROFILE", "")
        temp = os.environ.get("TEMP", r"C:\Windows\Temp")

        candidates = [
            os.path.join(pf64, program),
            os.path.join(pf86, program),
            os.path.join(appdata, program),
            os.path.join(localappdata, program),
            os.path.join(programdata, program),
            os.path.join(userprofile, "AppData", "Local", program),
            os.path.join(userprofile, "AppData", "Roaming", program),
            os.path.join(userprofile, "AppData", "LocalLow", program),
            os.path.join(temp, program),
            # Desktop shortcut
            os.path.join(userprofile, "Desktop", f"{program}.lnk"),
            # Start-menu shortcut
            os.path.join(
                appdata,
                "Microsoft", "Windows", "Start Menu", "Programs",
                f"{program}.lnk",
            ),
            os.path.join(
                appdata,
                "Microsoft", "Windows", "Start Menu", "Programs", program,
            ),
        ]

    elif SYSTEM == "Darwin":  # macOS
        home = _expand("~")
        candidates = [
            f"/Applications/{program}.app",
            f"/Applications/{program}",
            _expand("~/Applications", f"{program}.app"),
            _expand("~/Applications", program),
            _expand("~/.config", name_lower),
            _expand("~/.config", program),
            _expand("~/Library/Application Support", program),
            _expand("~/Library/Preferences", f"com.{name_lower}.plist"),
            _expand("~/Library/Preferences", f"{program}.plist"),
            _expand("~/Library/Caches", program),
            _expand("~/Library/Caches", name_lower),
            _expand("~/Library/Logs", program),
            _expand("~/Library/Saved Application State", f"com.{name_lower}.savedState"),
            f"/Library/Application Support/{program}",
            f"/Library/Preferences/com.{name_lower}.plist",
            f"/Library/Caches/{program}",
            f"/usr/local/bin/{name_lower}",
            f"/usr/local/bin/{program}",
            f"/opt/homebrew/bin/{name_lower}",
            f"/opt/homebrew/Caskroom/{name_lower}",
        ]

    else:  # Linux (and other POSIX)
        home = _expand("~")
        xdg_config = os.environ.get("XDG_CONFIG_HOME", _expand("~/.config"))
        xdg_data = os.environ.get("XDG_DATA_HOME", _expand("~/.local/share"))
        xdg_cache = os.environ.get("XDG_CACHE_HOME", _expand("~/.cache"))

        candidates = [
            # User-local config / data / cache
            os.path.join(xdg_config, name_lower),
            os.path.join(xdg_config, program),
            os.path.join(xdg_data, name_lower),
            os.path.join(xdg_data, program),
            os.path.join(xdg_cache, name_lower),
            os.path.join(xdg_cache, program),
            # Legacy dot-directories in home
            _expand(f"~/.{name_lower}"),
            _expand(f"~/.{program}"),
            # System-wide
            f"/usr/share/{name_lower}",
            f"/usr/share/{program}",
            f"/usr/local/share/{name_lower}",
            f"/usr/local/share/{program}",
            f"/opt/{name_lower}",
            f"/opt/{program}",
            # Executables
            f"/usr/bin/{name_lower}",
            f"/usr/bin/{program}",
            f"/usr/local/bin/{name_lower}",
            f"/usr/local/bin/{program}",
            # Desktop / menu entries
            _expand("~/.local/share/applications", f"{name_lower}.desktop"),
            _expand("~/.local/share/applications", f"{program}.desktop"),
            f"/usr/share/applications/{name_lower}.desktop",
            f"/usr/share/applications/{program}.desktop",
            # System logs
            f"/var/log/{name_lower}",
            f"/var/log/{program}",
            # Systemd user units
            _expand("~/.config/systemd/user", f"{name_lower}.service"),
            _expand("~/.config/systemd/user", f"{program}.service"),
        ]

    # Remove empty / duplicate entries
    seen: set[str] = set()
    unique: list[str] = []
    for p in candidates:
        if p and p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


# ---------------------------------------------------------------------------
# Windows registry cleanup
# ---------------------------------------------------------------------------

def windows_registry_targets(program: str) -> dict[str, list[tuple[str, str]]]:
    """
    Return a dict with two keys:

    - ``"keys"``   — (hive_name, subkey) pairs whose entire key tree should be
                     deleted.
    - ``"values"`` — (hive_name, subkey) pairs where the *named value*
                     ``program`` should be removed from an existing key (e.g.
                     auto-start Run entries).
    """
    uninstall = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    uninstall_wow = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
    run = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    run_wow = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
    apppath = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"

    return {
        "keys": [
            ("HKEY_LOCAL_MACHINE", f"{uninstall}\\{program}"),
            ("HKEY_LOCAL_MACHINE", f"{uninstall_wow}\\{program}"),
            ("HKEY_CURRENT_USER", f"{uninstall}\\{program}"),
            ("HKEY_LOCAL_MACHINE", f"{apppath}\\{program}.exe"),
            ("HKEY_CURRENT_USER", f"{apppath}\\{program}.exe"),
        ],
        "values": [
            ("HKEY_LOCAL_MACHINE", run),
            ("HKEY_CURRENT_USER", run),
            ("HKEY_LOCAL_MACHINE", run_wow),
        ],
    }


def _registry_hive_map() -> dict:
    """Return a mapping from hive name string to winreg constant."""
    try:
        import winreg  # type: ignore[import]
    except ImportError:
        return {}
    return {
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
        "HKEY_CLASSES_ROOT": winreg.HKEY_CLASSES_ROOT,
        "HKEY_USERS": winreg.HKEY_USERS,
    }


def _delete_registry_key_recursive(hive, subkey: str) -> None:
    """Recursively delete *subkey* and all of its children."""
    import winreg  # type: ignore[import]

    try:
        key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ)
    except OSError:
        return

    # Collect child key names before deletion to avoid iterator invalidation
    child_names: list[str] = []
    try:
        idx = 0
        while True:
            child_names.append(winreg.EnumKey(key, idx))
            idx += 1
    except OSError:
        pass
    key.Close()

    for child in child_names:
        _delete_registry_key_recursive(hive, f"{subkey}\\{child}")

    winreg.DeleteKey(hive, subkey)


def _delete_registry_key(hive_name: str, subkey: str, dry_run: bool) -> bool:
    """Recursively delete a registry key tree. Returns True if the key existed."""
    hive_map = _registry_hive_map()
    hive = hive_map.get(hive_name)
    if hive is None:
        return False

    try:
        import winreg  # type: ignore[import]
    except ImportError:
        return False

    # Check existence
    try:
        with winreg.OpenKey(hive, subkey):
            pass
    except OSError:
        return False

    if dry_run:
        return True

    try:
        _delete_registry_key_recursive(hive, subkey)
    except OSError as exc:
        print(f"  [warning] Could not delete registry key {hive_name}\\{subkey}: {exc}",
              file=sys.stderr)
        return False
    return True


def _remove_registry_run_value(hive_name: str, subkey: str, value_name: str,
                                dry_run: bool) -> bool:
    """Remove a named value from a Run-style registry key."""
    try:
        import winreg  # type: ignore[import]
    except ImportError:
        return False

    hive_map = _registry_hive_map()
    hive = hive_map.get(hive_name)
    if hive is None:
        return False

    try:
        key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ | winreg.KEY_WRITE)
    except OSError:
        return False

    try:
        winreg.QueryValueEx(key, value_name)
    except OSError:
        key.Close()
        return False

    if dry_run:
        key.Close()
        return True

    try:
        winreg.DeleteValue(key, value_name)
    except OSError as exc:
        print(f"  [warning] Could not remove registry value {value_name} "
              f"from {hive_name}\\{subkey}: {exc}", file=sys.stderr)
        key.Close()
        return False
    key.Close()
    return True


# ---------------------------------------------------------------------------
# Core removal logic
# ---------------------------------------------------------------------------

def find_existing(paths: list[str]) -> list[str]:
    """Return only the paths that currently exist on the filesystem."""
    return [p for p in paths if os.path.exists(p)]


def remove_path(path: str) -> None:
    """Remove a file or directory tree."""
    if os.path.islink(path) or os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)


def uninstall(program: str, dry_run: bool = False) -> dict[str, list[str]]:
    """
    Remove all traces of *program*.

    Returns a dict with keys 'removed', 'skipped', and 'errors' containing
    lists of path/key strings.
    """
    results: dict[str, list[str]] = {"removed": [], "skipped": [], "errors": []}

    # --- Filesystem ---
    all_paths = candidate_paths(program)
    existing = find_existing(all_paths)

    if not existing:
        results["skipped"].append("(no filesystem traces found)")
    else:
        for path in existing:
            if dry_run:
                results["removed"].append(path)
            else:
                try:
                    remove_path(path)
                    results["removed"].append(path)
                except OSError as exc:
                    results["errors"].append(f"{path}: {exc}")

    # --- Windows registry ---
    if SYSTEM == "Windows":
        targets = windows_registry_targets(program)
        for hive_name, subkey in targets["keys"]:
            if _delete_registry_key(hive_name, subkey, dry_run):
                results["removed"].append(f"[registry key] {hive_name}\\{subkey}")
        for hive_name, subkey in targets["values"]:
            if _remove_registry_run_value(hive_name, subkey, program, dry_run):
                results["removed"].append(
                    f"[registry value] {hive_name}\\{subkey}\\{program}"
                )

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="uninstall",
        description=(
            "Remove all traces of a program to allow for a clean reinstall."
        ),
    )
    parser.add_argument(
        "program",
        help="Name of the program to uninstall (case-sensitive on Linux/macOS).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without actually deleting anything.",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip the confirmation prompt.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    program: str = args.program
    dry_run: bool = args.dry_run

    print(f"\nUninstaller — searching for traces of '{program}' on {SYSTEM}...\n")

    # Preview what exists
    all_paths = candidate_paths(program)
    existing = find_existing(all_paths)

    if not existing:
        print("No filesystem traces found.")
        if SYSTEM != "Windows":
            print("Nothing to remove.")
            return 0
    else:
        label = "[DRY RUN] Would remove" if dry_run else "Found"
        print(f"{label} {len(existing)} item(s):")
        for p in existing:
            print(f"  {p}")

    # Confirm (unless --yes or --dry-run)
    if not dry_run and not args.yes and existing:
        print()
        try:
            answer = input("Proceed with removal? [y/N] ").strip().lower()
        except EOFError:
            answer = "n"
        if answer not in ("y", "yes"):
            print("Aborted — nothing was removed.")
            return 0

    results = uninstall(program, dry_run=dry_run)

    print()
    if dry_run:
        if results["removed"]:
            print("[DRY RUN] The following would be removed:")
            for item in results["removed"]:
                print(f"  ✓ {item}")
        else:
            print("[DRY RUN] Nothing to remove.")
    else:
        if results["removed"]:
            print("Successfully removed:")
            for item in results["removed"]:
                print(f"  ✓ {item}")
        if results["skipped"]:
            for msg in results["skipped"]:
                print(f"  (skipped) {msg}")
        if results["errors"]:
            print("\nErrors (items could not be removed):")
            for err in results["errors"]:
                print(f"  ✗ {err}", file=sys.stderr)

    if results["removed"]:
        noun = "would be removed" if dry_run else "removed"
        print(f"\nDone — {len(results['removed'])} item(s) {noun}.")
    else:
        print("\nDone — nothing was removed.")

    return 1 if results["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
