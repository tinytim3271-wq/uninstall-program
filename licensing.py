#!/usr/bin/env python3
"""License validation utilities for Reliable clean slate uninstall."""

from __future__ import annotations

import base64
import json
import os
import platform
import secrets
import shutil
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Optional


PRODUCT_NAME = "Reliable clean slate uninstall"
LICENSE_FILENAME = "license.json"
PUBLIC_KEY_FILENAME = "vendor_public_key.json"
SHA256_DER_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


class LicenseError(Exception):
    """Raised when a license file is missing, invalid, or unusable."""


@dataclass(frozen=True)
class LicenseRecord:
    """Validated license metadata."""

    payload: dict[str, Any]
    path: Path
    machine_id: str


def canonicalize_payload(payload: dict[str, Any]) -> bytes:
    """Return canonical JSON bytes for *payload*."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def b64url_encode(data: bytes) -> str:
    """Return URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(value: str) -> bytes:
    """Decode URL-safe base64 with optional missing padding."""
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _bytes_to_int(data: bytes) -> int:
    return int.from_bytes(data, "big")


def _int_to_bytes(value: int, length: int) -> bytes:
    return value.to_bytes(length, "big")


def _extended_gcd(a: int, b: int) -> tuple[int, int, int]:
    if b == 0:
        return a, 1, 0
    gcd, x1, y1 = _extended_gcd(b, a % b)
    return gcd, y1, x1 - (a // b) * y1


def _mod_inverse(value: int, modulus: int) -> int:
    gcd, x_value, _ = _extended_gcd(value, modulus)
    if gcd != 1:
        raise ValueError("Value is not invertible for the chosen modulus.")
    return x_value % modulus


def _is_probable_prime(candidate: int, rounds: int = 24) -> bool:
    if candidate in (2, 3):
        return True
    if candidate < 2 or candidate % 2 == 0:
        return False

    exponent = candidate - 1
    power_of_two = 0
    while exponent % 2 == 0:
        exponent //= 2
        power_of_two += 1

    for _ in range(rounds):
        witness = secrets.randbelow(candidate - 3) + 2
        value = pow(witness, exponent, candidate)
        if value in (1, candidate - 1):
            continue
        for _ in range(power_of_two - 1):
            value = pow(value, 2, candidate)
            if value == candidate - 1:
                break
        else:
            return False
    return True


def _generate_prime(bits: int) -> int:
    if bits < 256:
        raise ValueError("Prime size must be at least 256 bits.")

    while True:
        candidate = secrets.randbits(bits)
        candidate |= (1 << (bits - 1)) | 1
        if _is_probable_prime(candidate):
            return candidate


def generate_keypair(bits: int = 2048, exponent: int = 65537) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate an RSA keypair suitable for signing license files."""
    if bits < 1024:
        raise ValueError("Key size must be at least 1024 bits.")

    half_bits = bits // 2
    while True:
        prime_p = _generate_prime(half_bits)
        prime_q = _generate_prime(bits - half_bits)
        if prime_p == prime_q:
            continue
        totient = (prime_p - 1) * (prime_q - 1)
        if totient % exponent != 0:
            break

    modulus = prime_p * prime_q
    private_exponent = _mod_inverse(exponent, totient)
    key_id = str(uuid.uuid4())

    public_key = {
        "kid": key_id,
        "algorithm": "RSA-SHA256",
        "n": str(modulus),
        "e": str(exponent),
    }
    private_key = {
        **public_key,
        "d": str(private_exponent),
        "p": str(prime_p),
        "q": str(prime_q),
    }
    return public_key, private_key


def _emsa_pkcs1_v1_5_encode(payload_bytes: bytes, encoded_length: int) -> bytes:
    digest = sha256(payload_bytes).digest()
    digest_info = SHA256_DER_PREFIX + digest
    if encoded_length < len(digest_info) + 11:
        raise LicenseError("Public key is too small for SHA-256 signatures.")
    padding = b"\xff" * (encoded_length - len(digest_info) - 3)
    return b"\x00\x01" + padding + b"\x00" + digest_info


def sign_payload(payload: dict[str, Any], private_key: dict[str, Any]) -> str:
    """Sign *payload* with *private_key* and return a base64url signature."""
    modulus = int(private_key["n"])
    private_exponent = int(private_key["d"])
    payload_bytes = canonicalize_payload(payload)
    key_length = (modulus.bit_length() + 7) // 8
    encoded_message = _emsa_pkcs1_v1_5_encode(payload_bytes, key_length)
    signature_int = pow(_bytes_to_int(encoded_message), private_exponent, modulus)
    return b64url_encode(_int_to_bytes(signature_int, key_length))


def verify_signature(payload: dict[str, Any], signature: str, public_key: dict[str, Any]) -> bool:
    """Return True when *signature* is valid for *payload* and *public_key*."""
    try:
        modulus = int(public_key["n"])
        exponent = int(public_key["e"])
        signature_bytes = b64url_decode(signature)
    except (KeyError, ValueError, TypeError):
        return False

    key_length = (modulus.bit_length() + 7) // 8
    if len(signature_bytes) != key_length:
        return False

    signature_int = _bytes_to_int(signature_bytes)
    recovered = pow(signature_int, exponent, modulus)
    recovered_bytes = _int_to_bytes(recovered, key_length)
    expected = _emsa_pkcs1_v1_5_encode(canonicalize_payload(payload), key_length)
    return recovered_bytes == expected


def current_machine_id() -> str:
    """Return a stable machine identifier for optional license binding."""
    raw = "|".join(
        [
            platform.system(),
            platform.machine(),
            platform.node(),
            os.environ.get("USERNAME") or os.environ.get("USER") or "",
        ]
    )
    return sha256(raw.encode("utf-8")).hexdigest()


def _parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise LicenseError(f"License field '{field_name}' must use YYYY-MM-DD format.") from exc


def default_license_store_dir() -> Path:
    """Return the per-machine license directory."""
    if os.name == "nt":
        program_data = os.environ.get("ProgramData", r"C:\ProgramData")
        return Path(program_data) / PRODUCT_NAME
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / PRODUCT_NAME
    return Path.home() / ".config" / PRODUCT_NAME


def resolve_license_path(explicit_path: str | None = None, script_dir: Path | None = None) -> Optional[Path]:
    """Return the first existing license path from explicit, env, or default locations."""
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))

    env_path = os.environ.get("RCSU_LICENSE_FILE")
    if env_path:
        candidates.append(Path(env_path))

    if script_dir is not None:
        candidates.append(script_dir / LICENSE_FILENAME)

    candidates.append(default_license_store_dir() / LICENSE_FILENAME)

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def resolve_public_key_path(explicit_path: str | None = None, script_dir: Path | None = None) -> Path:
    """Resolve the public-key file path used to verify licenses."""
    if explicit_path:
        return Path(explicit_path)

    env_path = os.environ.get("RCSU_PUBLIC_KEY_FILE")
    if env_path:
        return Path(env_path)

    if script_dir is None:
        raise LicenseError("Public key location could not be resolved.")
    return script_dir / PUBLIC_KEY_FILENAME


def load_json_file(path: Path) -> dict[str, Any]:
    """Load a JSON object from *path*."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise LicenseError(f"Required file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LicenseError(f"Invalid JSON in file: {path}") from exc

    if not isinstance(value, dict):
        raise LicenseError(f"JSON document must be an object: {path}")
    return value


def load_public_key(path: Path) -> dict[str, Any]:
    """Load and validate the public-key document."""
    public_key = load_json_file(path)
    for field_name in ("n", "e"):
        if field_name not in public_key:
            raise LicenseError(f"Public key file is missing '{field_name}': {path}")
    try:
        modulus = int(public_key["n"])
        exponent = int(public_key["e"])
    except (TypeError, ValueError) as exc:
        raise LicenseError(f"Public key file contains non-numeric RSA fields: {path}") from exc

    if modulus <= 1 or exponent <= 1:
        raise LicenseError(f"Public key file contains invalid RSA values: {path}")
    return public_key


def validate_license_document(
    document: dict[str, Any],
    public_key: dict[str, Any],
    machine_id: str | None = None,
    product_name: str = PRODUCT_NAME,
) -> LicenseRecord:
    """Validate an in-memory license *document*."""
    payload = document.get("payload")
    signature = document.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, str):
        raise LicenseError("License file must contain 'payload' and 'signature' fields.")

    if payload.get("product") != product_name:
        raise LicenseError("License does not apply to this product.")

    if not verify_signature(payload, signature, public_key):
        raise LicenseError("License signature verification failed.")

    today = datetime.now(timezone.utc).date()

    issued_at_value = payload.get("issued_at")
    if not isinstance(issued_at_value, str):
        raise LicenseError("License field 'issued_at' is required.")
    issued_at = _parse_date(issued_at_value, "issued_at")
    if issued_at > today:
        raise LicenseError("License is not valid yet.")

    expires_at_value = payload.get("expires_at")
    if expires_at_value is not None:
        if not isinstance(expires_at_value, str):
            raise LicenseError("License field 'expires_at' must be a string or null.")
        expires_at = _parse_date(expires_at_value, "expires_at")
        if expires_at < today:
            raise LicenseError("License has expired.")

    resolved_machine_id = machine_id or current_machine_id()
    bound_machine = payload.get("machine_id")
    if bound_machine and bound_machine != resolved_machine_id:
        raise LicenseError("License is bound to a different machine.")

    return LicenseRecord(payload=payload, path=Path("<memory>"), machine_id=resolved_machine_id)


def validate_license_file(
    license_path: Path,
    public_key_path: Path,
    machine_id: str | None = None,
    product_name: str = PRODUCT_NAME,
) -> LicenseRecord:
    """Validate a license file on disk and return the parsed record."""
    document = load_json_file(license_path)
    public_key = load_public_key(public_key_path)
    record = validate_license_document(document, public_key, machine_id, product_name)
    return LicenseRecord(payload=record.payload, path=license_path, machine_id=record.machine_id)


def require_valid_license(
    explicit_license_path: str | None = None,
    script_dir: Path | None = None,
    public_key_path: str | None = None,
    machine_id: str | None = None,
) -> LicenseRecord:
    """Resolve and validate the active license or raise LicenseError."""
    script_dir = script_dir or Path.cwd()
    license_path = resolve_license_path(explicit_license_path, script_dir)
    if license_path is None:
        raise LicenseError(
            "No license file was found. Provide one with --license-file or install license.json into the product directory."
        )

    key_path = resolve_public_key_path(public_key_path, script_dir)
    return validate_license_file(license_path, key_path, machine_id)


def install_license_file(source_path: Path, destination_dir: Path) -> Path:
    """Copy *source_path* into *destination_dir* as the active license file."""
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / LICENSE_FILENAME
    shutil.copy2(source_path, destination)
    return destination


def build_license_payload(
    customer: str,
    email: str,
    expires_at: str | None = None,
    machine_id: str | None = None,
    features: list[str] | None = None,
    product_name: str = PRODUCT_NAME,
) -> dict[str, Any]:
    """Return a normalized payload dictionary for a license document."""
    issued_at = datetime.now(timezone.utc).date().isoformat()
    if expires_at is not None:
        _parse_date(expires_at, "expires_at")
    payload = {
        "product": product_name,
        "customer": customer,
        "email": email,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "machine_id": machine_id,
        "features": sorted(set(features or [])),
        "license_id": str(uuid.uuid4()),
    }
    return payload


def write_json_file(path: Path, value: dict[str, Any]) -> None:
    """Write *value* as pretty JSON to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")