import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


import install
import uninstall


REPO_ROOT = Path(__file__).resolve().parent
SCRIPT_PATH = REPO_ROOT / "uninstall.py"
INSTALLER_PATH = REPO_ROOT / "install.ps1"
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import install
import licensing
import uninstall


REPO_ROOT = Path(__file__).resolve().parent
SCRIPT_PATH = REPO_ROOT / "uninstall.py"
INSTALLER_PATH = REPO_ROOT / "install.ps1"
PYTHON_INSTALLER_PATH = REPO_ROOT / "install.py"
TEST_PUBLIC_KEY, TEST_PRIVATE_KEY = licensing.generate_keypair(bits=1024)


def write_test_license_artifacts(temp_dir: Path, machine_id: str | None = None) -> tuple[Path, Path]:
    public_key_path = temp_dir / licensing.PUBLIC_KEY_FILENAME
    license_path = temp_dir / licensing.LICENSE_FILENAME

    licensing.write_json_file(public_key_path, TEST_PUBLIC_KEY)
    payload = licensing.build_license_payload(
        customer="Test Customer",
        email="test@example.com",
        expires_at="2099-12-31",
        machine_id=machine_id,
        features=["all"],
    )
    document = {
        "payload": payload,
        "signature": licensing.sign_payload(payload, TEST_PRIVATE_KEY),
    }
    licensing.write_json_file(license_path, document)
    return license_path, public_key_path


class UninstallCliSmokeTests(unittest.TestCase):
    def run_cli(
        self,
        *args: str,
        input_text: str = "",
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command_env = os.environ.copy()
        if env:
            command_env.update(env)

        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            input=input_text,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env=command_env,
            check=False,
        )

    def test_help_output_uses_public_program_name(self) -> None:
        result = self.run_cli("--help")

        self.assertEqual(result.returncode, 0)
        self.assertIn("Reliable clean slate uninstall", result.stdout)
        self.assertIn("--dry-run", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_dry_run_with_fake_program_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            license_path, public_key_path = write_test_license_artifacts(temp_path)
            env = {
                "RCSU_LICENSE_FILE": str(license_path),
                "RCSU_PUBLIC_KEY_FILE": str(public_key_path),
            }

            result = self.run_cli("FakeProgramForSmokeTest", "--dry-run", env=env)

        self.assertEqual(result.returncode, 0)
        self.assertIn("No filesystem traces found.", result.stdout)
        self.assertIn("[DRY RUN] Nothing to remove.", result.stdout)
        self.assertIn("Done", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_runtime_returns_license_error_when_license_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            uninstall_copy = temp_path / "uninstall.py"
            licensing_copy = temp_path / "licensing.py"
            uninstall_copy.write_text(SCRIPT_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            licensing_copy.write_text((REPO_ROOT / "licensing.py").read_text(encoding="utf-8"), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(uninstall_copy), "FakeProgramForSmokeTest", "--dry-run"],
                capture_output=True,
                text=True,
                cwd=temp_path,
                env=os.environ.copy(),
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("License error:", result.stderr)

    def test_interactive_abort_keeps_existing_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            program_name = f"CopilotInteractiveAbortSmokeApp-{temp_path.name}"
            target_path = temp_path / program_name
            target_path.mkdir()
            license_path, public_key_path = write_test_license_artifacts(temp_path)
            env = {
                "ProgramFiles": temp_dir,
                "ProgramFiles(x86)": temp_dir,
                "APPDATA": temp_dir,
                "LOCALAPPDATA": temp_dir,
                "ProgramData": temp_dir,
                "USERPROFILE": temp_dir,
                "TEMP": temp_dir,
                "RCSU_LICENSE_FILE": str(license_path),
                "RCSU_PUBLIC_KEY_FILE": str(public_key_path),
            }

            result = self.run_cli(program_name, input_text="n\n", env=env)

            self.assertEqual(result.returncode, 0)
            self.assertIn("Found 1 item(s):", result.stdout)
            self.assertIn("Proceed with removal? [y/N]", result.stdout)
            self.assertIn("Aborted", result.stdout)
            self.assertTrue(target_path.exists())

    def test_interactive_confirm_removes_existing_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            program_name = f"CopilotInteractiveConfirmSmokeApp-{temp_path.name}"
            target_path = temp_path / program_name
            target_path.mkdir()
            license_path, public_key_path = write_test_license_artifacts(temp_path)
            env = {
                "ProgramFiles": temp_dir,
                "ProgramFiles(x86)": temp_dir,
                "APPDATA": temp_dir,
                "LOCALAPPDATA": temp_dir,
                "ProgramData": temp_dir,
                "USERPROFILE": temp_dir,
                "TEMP": temp_dir,
                "RCSU_LICENSE_FILE": str(license_path),
                "RCSU_PUBLIC_KEY_FILE": str(public_key_path),
            }

            result = self.run_cli(program_name, input_text="y\n", env=env)

            self.assertEqual(result.returncode, 0)
            self.assertIn("Found 1 item(s):", result.stdout)
            self.assertIn("Successfully removed:", result.stdout)
            self.assertFalse(target_path.exists())


class InstallUnitTests(unittest.TestCase):
    def test_compute_updated_user_path_appends_missing_destination(self) -> None:
        destination = Path(r"D:\Reliable clean slate uninstall")

        updated_path = install.compute_updated_user_path(destination, r"C:\Windows;C:\Tools")

        self.assertEqual(
            updated_path,
            r"C:\Windows;C:\Tools;D:\Reliable clean slate uninstall",
        )

    def test_compute_updated_user_path_avoids_duplicate_entry(self) -> None:
        destination = Path(r"D:\Reliable clean slate uninstall")

        updated_path = install.compute_updated_user_path(
            destination,
            r"C:\Windows;D:\Reliable clean slate uninstall",
        )

        self.assertIsNone(updated_path)

    def test_install_program_raises_when_source_files_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(FileNotFoundError):
                install.install_program(Path(temp_dir), Path(temp_dir) / "dest")

    def test_install_program_updates_path_via_injected_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            destination = Path(temp_dir) / "dest"
            source_dir.mkdir()
            for file_name in install.RUNTIME_FILES:
                (source_dir / file_name).write_text(file_name, encoding="utf-8")

            writes: list[str] = []
            result = install.install_program(
                source_dir,
                destination,
                add_to_path=True,
                read_user_path=lambda: r"C:\Windows",
                write_user_path=writes.append,
            )

            self.assertTrue((destination / "uninstall.py").exists())
            self.assertEqual(len(writes), 1)
            self.assertIn(str(destination), writes[0])
            self.assertTrue(result["path_added"])
            self.assertFalse(result["path_already_present"])

    def test_install_program_copies_validated_license_and_public_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            destination = temp_path / "dest"
            source_dir.mkdir()
            for file_name in install.RUNTIME_FILES:
                (source_dir / file_name).write_text(file_name, encoding="utf-8")

            license_path, public_key_path = write_test_license_artifacts(temp_path)
            result = install.install_program(
                source_dir,
                destination,
                license_source=license_path,
                public_key_path=str(public_key_path),
            )

            self.assertEqual(result["installed_license_path"], destination / licensing.LICENSE_FILENAME)
            self.assertTrue((destination / licensing.LICENSE_FILENAME).exists())
            self.assertEqual(
                (destination / licensing.PUBLIC_KEY_FILENAME).read_text(encoding="utf-8"),
                public_key_path.read_text(encoding="utf-8"),
            )

    def test_install_program_uses_bundled_license_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            destination = temp_path / "dest"
            source_dir.mkdir()
            for file_name in install.RUNTIME_FILES:
                (source_dir / file_name).write_text(file_name, encoding="utf-8")

            license_path, public_key_path = write_test_license_artifacts(source_dir)
            result = install.install_program(
                source_dir,
                destination,
                public_key_path=str(public_key_path),
            )

            self.assertEqual(result["installed_license_path"], destination / licensing.LICENSE_FILENAME)
            self.assertTrue((destination / licensing.LICENSE_FILENAME).exists())


class UninstallUnitTests(unittest.TestCase):
    def test_windows_candidate_paths_include_expected_locations(self) -> None:
        env = {
            "ProgramFiles": r"D:\Programs",
            "ProgramFiles(x86)": r"D:\ProgramsX86",
            "APPDATA": r"C:\Users\secon\AppData\Roaming",
            "LOCALAPPDATA": r"C:\Users\secon\AppData\Local",
            "ProgramData": r"C:\ProgramData",
            "USERPROFILE": r"C:\Users\secon",
            "TEMP": r"C:\Temp",
        }

        with patch.object(uninstall, "SYSTEM", "Windows"), patch.dict(uninstall.os.environ, env, clear=True):
            paths = uninstall.candidate_paths("DemoApp")

        self.assertIn(r"D:\Programs\DemoApp", paths)
        self.assertIn(r"C:\Users\secon\Desktop\DemoApp.lnk", paths)
        self.assertIn(
            r"C:\Users\secon\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\DemoApp.lnk",
            paths,
        )
        self.assertEqual(len(paths), len(set(paths)))

    def test_linux_candidate_paths_include_lowercase_and_original_name(self) -> None:
        env = {
            "XDG_CONFIG_HOME": "/tmp/config-home",
            "XDG_DATA_HOME": "/tmp/data-home",
            "XDG_CACHE_HOME": "/tmp/cache-home",
        }

        with patch.object(uninstall, "SYSTEM", "Linux"), patch.dict(uninstall.os.environ, env, clear=True):
            paths = uninstall.candidate_paths("DemoApp")

        self.assertIn(uninstall.os.path.join("/tmp/config-home", "demoapp"), paths)
        self.assertIn(uninstall.os.path.join("/tmp/config-home", "DemoApp"), paths)
        self.assertIn("/usr/bin/demoapp", paths)
        self.assertIn("/usr/bin/DemoApp", paths)

    def test_windows_registry_targets_include_uninstall_and_app_paths(self) -> None:
        targets = uninstall.windows_registry_targets("DemoApp")

        self.assertIn(
            (
                "HKEY_LOCAL_MACHINE",
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\DemoApp",
            ),
            targets["keys"],
        )
        self.assertIn(
            (
                "HKEY_LOCAL_MACHINE",
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\DemoApp.exe",
            ),
            targets["keys"],
        )
        self.assertIn(
            (
                "HKEY_CURRENT_USER",
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
            ),
            targets["values"],
        )

    def test_find_existing_returns_only_present_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            existing_file = temp_path / "present.txt"
            existing_dir = temp_path / "present-dir"
            missing_path = temp_path / "missing.txt"

            existing_file.write_text("hello", encoding="utf-8")
            existing_dir.mkdir()

            result = uninstall.find_existing(
                [str(existing_file), str(existing_dir), str(missing_path)]
            )

        self.assertEqual(result, [str(existing_file), str(existing_dir)])

    def test_remove_path_deletes_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "deleteme.txt"
            file_path.write_text("hello", encoding="utf-8")

            uninstall.remove_path(str(file_path))

            self.assertFalse(file_path.exists())

    def test_remove_path_deletes_directory_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir) / "deleteme"
            nested_file = dir_path / "nested.txt"
            dir_path.mkdir()
            nested_file.write_text("hello", encoding="utf-8")

            uninstall.remove_path(str(dir_path))

            self.assertFalse(dir_path.exists())

    def test_remove_path_raises_for_missing_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing.txt"

            with self.assertRaises(OSError):
                uninstall.remove_path(str(missing_path))

    def test_uninstall_dry_run_reports_filesystem_and_registry_matches(self) -> None:
        with patch.object(uninstall, "SYSTEM", "Windows"), \
             patch.object(uninstall, "candidate_paths", return_value=["C:\\found-a", "C:\\found-b"]), \
             patch.object(uninstall, "find_existing", return_value=["C:\\found-a"]), \
             patch.object(
                 uninstall,
                 "windows_registry_targets",
                 return_value={
                     "keys": [("HKEY_LOCAL_MACHINE", r"Software\\DemoApp")],
                     "values": [("HKEY_CURRENT_USER", r"Software\\Run")],
                 },
             ), \
             patch.object(uninstall, "_delete_registry_key", return_value=True), \
             patch.object(uninstall, "_remove_registry_run_value", return_value=True), \
             patch.object(uninstall, "remove_path") as remove_path_mock:
            result = uninstall.uninstall("DemoApp", dry_run=True)

        self.assertEqual(
            result["removed"],
            [
                r"C:\found-a",
                r"[registry key] HKEY_LOCAL_MACHINE\Software\\DemoApp",
                r"[registry value] HKEY_CURRENT_USER\Software\\Run\DemoApp",
            ],
        )
        self.assertEqual(result["skipped"], [])
        self.assertEqual(result["errors"], [])
        remove_path_mock.assert_not_called()

    def test_uninstall_collects_filesystem_and_registry_errors(self) -> None:
        with patch.object(uninstall, "SYSTEM", "Windows"), \
             patch.object(uninstall, "candidate_paths", return_value=["C:\\broken"]), \
             patch.object(uninstall, "find_existing", return_value=["C:\\broken"]), \
             patch.object(
                 uninstall,
                 "windows_registry_targets",
                 return_value={
                     "keys": [("HKEY_LOCAL_MACHINE", r"Software\\BrokenApp")],
                     "values": [("HKEY_CURRENT_USER", r"Software\\Run")],
                 },
             ), \
             patch.object(uninstall, "remove_path", side_effect=OSError("file locked")), \
             patch.object(uninstall, "_delete_registry_key", side_effect=OSError("access denied")), \
             patch.object(uninstall, "_remove_registry_run_value", side_effect=OSError("value locked")):
            result = uninstall.uninstall("BrokenApp", dry_run=False)

        self.assertEqual(result["removed"], [])
        self.assertEqual(result["skipped"], [])
        self.assertEqual(
            result["errors"],
            [
                r"C:\broken: file locked",
                r"[registry key] HKEY_LOCAL_MACHINE\Software\\BrokenApp: access denied",
                r"[registry value] HKEY_CURRENT_USER\Software\\Run\BrokenApp: value locked",
            ],
        )

    def test_uninstall_without_matches_reports_skipped_for_non_dry_run(self) -> None:
        with patch.object(uninstall, "SYSTEM", "Linux"), \
             patch.object(uninstall, "candidate_paths", return_value=[]), \
             patch.object(uninstall, "find_existing", return_value=[]):
            result = uninstall.uninstall("DemoApp", dry_run=False)

        self.assertEqual(result["removed"], [])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["skipped"], ["(no filesystem traces found)"])


class InstallerIntegrationTests(unittest.TestCase):
    def test_installer_copies_runtime_files_and_launcher_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "installed-app"
            install_result = subprocess.run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(INSTALLER_PATH),
                    "-Destination",
                    str(destination),
                ],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                check=False,
            )

            self.assertEqual(install_result.returncode, 0, install_result.stderr)
            self.assertTrue((destination / "uninstall.py").exists())
            self.assertTrue((destination / "README.md").exists())
            self.assertTrue((destination / "LICENSE").exists())
            self.assertTrue((destination / "licensing.py").exists())

            launcher_path = destination / "Reliable clean slate uninstall.cmd"
            self.assertTrue(launcher_path.exists())

            launcher_result = subprocess.run(
                [str(launcher_path), "--help"],
                capture_output=True,
                text=True,
                cwd=destination,
                check=False,
                shell=True,
            )

            self.assertEqual(launcher_result.returncode, 0, launcher_result.stderr)
            self.assertIn("Reliable clean slate uninstall", launcher_result.stdout)

    def test_installer_fails_when_required_source_files_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            installer_copy = temp_path / "install.py"
            licensing_copy = temp_path / "licensing.py"
            installer_copy.write_text(PYTHON_INSTALLER_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            licensing_copy.write_text((REPO_ROOT / "licensing.py").read_text(encoding="utf-8"), encoding="utf-8")

            install_result = subprocess.run(
                [
                    sys.executable,
                    str(installer_copy),
                    "--destination",
                    str(temp_path / "installed-app"),
                ],
                capture_output=True,
                text=True,
                cwd=temp_path,
                check=False,
            )

            self.assertNotEqual(install_result.returncode, 0)
            self.assertIn("Required source file not found", install_result.stderr)

    def test_installer_fails_when_destination_is_an_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination_file = Path(temp_dir) / "not-a-directory.txt"
            destination_file.write_text("occupied", encoding="utf-8")

            install_result = subprocess.run(
                [
                    sys.executable,
                    str(PYTHON_INSTALLER_PATH),
                    "--destination",
                    str(destination_file),
                ],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                check=False,
            )

            self.assertNotEqual(install_result.returncode, 0)
            combined_output = f"{install_result.stdout}\n{install_result.stderr}"
            self.assertIn("Cannot create a file when that file already exists", combined_output)
            self.assertIn("not-a-directory.txt", combined_output)


if __name__ == "__main__":
    unittest.main()