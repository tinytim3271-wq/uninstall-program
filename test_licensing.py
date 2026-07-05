import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import build_installer
import licensing


REPO_ROOT = Path(__file__).resolve().parent
LICENSE_ADMIN_PATH = REPO_ROOT / "license_admin.py"
TEST_PUBLIC_KEY, TEST_PRIVATE_KEY = licensing.generate_keypair(bits=1024)


def make_signed_license(temp_dir: Path, machine_id: str | None = None) -> tuple[Path, Path, dict]:
    public_key_path = temp_dir / "custom_public_key.json"
    private_key_path = temp_dir / "custom_private_key.json"
    license_path = temp_dir / licensing.LICENSE_FILENAME

    licensing.write_json_file(public_key_path, TEST_PUBLIC_KEY)
    licensing.write_json_file(private_key_path, TEST_PRIVATE_KEY)
    payload = licensing.build_license_payload(
        customer="Acme Corp",
        email="ops@acme.test",
        expires_at="2099-12-31",
        machine_id=machine_id,
        features=["all", "prod"],
    )
    document = {
        "payload": payload,
        "signature": licensing.sign_payload(payload, TEST_PRIVATE_KEY),
    }
    licensing.write_json_file(license_path, document)
    return license_path, public_key_path, payload


class LicensingTests(unittest.TestCase):
    def test_validate_license_file_accepts_signed_license(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            license_path, public_key_path, payload = make_signed_license(temp_path)

            record = licensing.validate_license_file(license_path, public_key_path)

        self.assertEqual(record.payload["customer"], payload["customer"])
        self.assertEqual(record.path, license_path)

    def test_validate_license_file_rejects_machine_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            license_path, public_key_path, _ = make_signed_license(temp_path, machine_id="bound-machine")

            with self.assertRaises(licensing.LicenseError):
                licensing.validate_license_file(license_path, public_key_path, machine_id="other-machine")

    def test_require_valid_license_uses_environment_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            license_path, public_key_path, _ = make_signed_license(temp_path)
            env = {
                "RCSU_LICENSE_FILE": str(license_path),
                "RCSU_PUBLIC_KEY_FILE": str(public_key_path),
            }

            with mock.patch.dict(licensing.os.environ, env, clear=False):
                record = licensing.require_valid_license(script_dir=temp_path)

        self.assertEqual(record.path, license_path)

    def test_license_admin_generates_and_issues_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            public_key_path = temp_path / "vendor_public_key.json"
            private_key_path = temp_path / "private_key.json"
            license_path = temp_path / licensing.LICENSE_FILENAME

            keygen = subprocess.run(
                [
                    sys.executable,
                    str(LICENSE_ADMIN_PATH),
                    "generate-keypair",
                    "--bits",
                    "1024",
                    "--public-out",
                    str(public_key_path),
                    "--private-out",
                    str(private_key_path),
                ],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                check=False,
            )
            self.assertEqual(keygen.returncode, 0, keygen.stderr)

            issue = subprocess.run(
                [
                    sys.executable,
                    str(LICENSE_ADMIN_PATH),
                    "issue",
                    "--private-key",
                    str(private_key_path),
                    "--output",
                    str(license_path),
                    "--customer",
                    "Acme Corp",
                    "--email",
                    "ops@acme.test",
                    "--expires-at",
                    "2099-12-31",
                ],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                check=False,
            )
            self.assertEqual(issue.returncode, 0, issue.stderr)

            record = licensing.validate_license_file(license_path, public_key_path)

        self.assertEqual(record.payload["customer"], "Acme Corp")


class BuildBundleTests(unittest.TestCase):
    def test_build_bundle_creates_archive_and_embeds_matching_license(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_dir = temp_path / "dist"
            license_path, public_key_path, _ = make_signed_license(temp_path)

            result = build_installer.build_bundle(
                source_dir=REPO_ROOT,
                output_dir=output_dir,
                license_file=license_path,
                public_key_file=public_key_path,
            )

            bundle_dir = result["bundle_dir"]
            archive_path = result["archive_path"]

            self.assertTrue((bundle_dir / "install.py").exists())
            self.assertTrue((bundle_dir / licensing.LICENSE_FILENAME).exists())
            self.assertTrue(archive_path.exists())
            self.assertEqual(
                (bundle_dir / licensing.PUBLIC_KEY_FILENAME).read_text(encoding="utf-8"),
                public_key_path.read_text(encoding="utf-8"),
            )

    def test_build_bundle_without_license_still_creates_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_dir = temp_path / "dist"

            result = build_installer.build_bundle(REPO_ROOT, output_dir)

            self.assertTrue(result["bundle_dir"].exists())
            self.assertTrue(result["archive_path"].exists())
            self.assertFalse((result["bundle_dir"] / licensing.LICENSE_FILENAME).exists())


if __name__ == "__main__":
    unittest.main()