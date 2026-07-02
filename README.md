# uninstall-program

A cross-platform command-line tool that removes **all traces** of a program
(installation directories, configuration files, caches, logs, desktop/menu
shortcuts, and on Windows, registry entries) so you can perform a clean
reinstall.

## Requirements

- Python 3.9+
- No third-party dependencies — uses the standard library only.

## Usage

```
python uninstall.py <program_name> [--dry-run] [--yes]
```

### Positional arguments

| Argument | Description |
|---|---|
| `program_name` | Name of the program to uninstall. Case-sensitive on Linux/macOS. |

### Options

| Flag | Description |
|---|---|
| `--dry-run` | List everything that *would* be removed without deleting anything. |
| `--yes`, `-y` | Skip the confirmation prompt and remove immediately. |

## Examples

Preview what would be removed (safe — nothing is deleted):

```bash
python uninstall.py myapp --dry-run
```

Remove all traces interactively (asks for confirmation):

```bash
python uninstall.py myapp
```

Remove all traces without prompting:

```bash
python uninstall.py myapp --yes
```

## What gets removed

### Linux

- XDG config directory (`$XDG_CONFIG_HOME/<program>`)
- XDG data directory (`$XDG_DATA_HOME/<program>`)
- XDG cache directory (`$XDG_CACHE_HOME/<program>`)
- Legacy dot-directory in home (`~/.<program>`)
- System-wide directories under `/usr/share`, `/usr/local/share`, `/opt`
- Executables in `/usr/bin` and `/usr/local/bin`
- Desktop and application menu entries (`.desktop` files)
- Log directories under `/var/log`
- Systemd user unit files

### macOS

- Application bundle (`/Applications/<program>.app`)
- User Application Support (`~/Library/Application Support/<program>`)
- User Preferences (`~/Library/Preferences/com.<program>.plist`)
- User Caches (`~/Library/Caches/<program>`)
- User Logs (`~/Library/Logs/<program>`)
- Saved Application State
- Homebrew Cask installation if present

### Windows

- `Program Files` and `Program Files (x86)` installation directories
- `%APPDATA%`, `%LOCALAPPDATA%`, and `%PROGRAMDATA%` directories
- Temporary files
- Desktop and Start Menu shortcuts (`.lnk` files)
- Registry keys under `HKLM\SOFTWARE\…\Uninstall\<program>`
- Registry keys under `HKCU\SOFTWARE\…\Uninstall\<program>`
- `App Paths` registry entries
