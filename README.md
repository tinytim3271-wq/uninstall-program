# Reliable clean slate uninstall

A cross-platform command-line tool that removes **all traces** of a program
(installation directories, configuration files, caches, logs, desktop/menu
shortcuts, and on Windows, registry entries) so you can perform a clean
reinstall.

## Requirements

- Python 3.9+
- No third-party dependencies — uses the standard library only.

## Licensing

The runtime now expects a signed `license.json` file and a matching `vendor_public_key.json`.
The repository includes a placeholder public key; replace it with your real public key before shipping a production build.

Administrative flows:

```powershell
python .\license_admin.py generate-keypair --public-out .\vendor_public_key.json --private-out .\private_key.json
python .\license_admin.py machine-id
python .\license_admin.py issue --private-key .\private_key.json --output .\license.json --customer "Example Corp" --email ops@example.com --expires-at 2027-07-02
```

Runtime flows:

- Put `license.json` next to `uninstall.py`, next to the installed launcher, or in `%ProgramData%\Reliable clean slate uninstall\license.json`
- Or pass `--license-file <path>` to the runtime and installer
- Machine-bound licenses can be issued with `--machine-id <value>`

## Installation on Windows

Run the installer from this repository:

```powershell
.\install.cmd
```

The Windows wrappers call the Python installer entry point in `install.py`.

Default install location:

- `D:\Reliable clean slate uninstall` if `D:` exists
- Otherwise `%ProgramFiles%\Reliable clean slate uninstall`

Optional flags:

- `-Destination "D:\Apps\Reliable clean slate uninstall"` to install elsewhere
- `-AddToPath` to append the install folder to the current user's `PATH`
- `--license-file <path>` to validate and install a signed license with the app

Example:

```powershell
.\install.cmd -Destination "D:\Apps\Reliable clean slate uninstall" -AddToPath
```

You can also call the Python installer directly:

```powershell
python .\install.py --destination "D:\Apps\Reliable clean slate uninstall" --add-to-path --license-file .\license.json
```

After installation, run the launcher from the install folder:

```powershell
& 'D:\Reliable clean slate uninstall\Reliable clean slate uninstall.cmd' --help
```

## Tests

Run the automated smoke tests with:

```powershell
python -m unittest -v
```

## Production Bundle

Build a distributable installer bundle and zip archive with:

```powershell
python .\build_installer.py --output-dir .\dist --license-file .\license.json
```

That creates a production folder plus a zip archive containing the installer wrappers, runtime files, public key, and optional embedded license.

## Usage

```
Reliable clean slate uninstall <program_name> [--dry-run] [--yes]
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
| `--license-file` | Override the license file used for runtime verification. |

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
