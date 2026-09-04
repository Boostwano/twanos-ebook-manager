"""Windows-account-protected storage for plugin API keys."""

from __future__ import annotations

import base64
import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path


class PluginCredentialError(RuntimeError):
    """A plugin credential could not be stored or recovered safely."""


class _DataBlob(ctypes.Structure):
    _fields_ = (
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    )


class PluginCredentialStore:
    """Encrypt API keys with Windows DPAPI before writing them to disk."""

    _ENTROPY = b"Twano plugin credentials v1"
    _NO_UI = 0x01

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def save(self, plugin_id: str, value: str) -> None:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Enter an API key before choosing Save.")
        payload = self._load_payload()
        payload[plugin_id] = base64.b64encode(
            self._protect(cleaned.encode("utf-8"))
        ).decode("ascii")
        self._save_payload(payload)
        if self.load(plugin_id) != cleaned:
            self.delete(plugin_id)
            raise PluginCredentialError(
                "Windows saved the API key but could not unlock it again. "
                "The unusable entry was removed; please try saving it once "
                "more under your normal Windows account."
            )

    def load(self, plugin_id: str) -> str:
        encoded = self._load_payload().get(plugin_id, "")
        if not encoded:
            return ""
        try:
            encrypted = base64.b64decode(encoded, validate=True)
            return self._unprotect(encrypted).decode("utf-8")
        except (
            ValueError,
            UnicodeDecodeError,
            PluginCredentialError,
        ):
            return ""

    def has(self, plugin_id: str) -> bool:
        return bool(self.load(plugin_id))

    def entry_exists(self, plugin_id: str) -> bool:
        """Return whether encrypted data exists without exposing it."""
        return bool(self._load_payload().get(plugin_id, ""))

    def is_unreadable(self, plugin_id: str) -> bool:
        """Identify an entry Windows can no longer unlock for this account."""
        return self.entry_exists(plugin_id) and not self.has(plugin_id)

    def delete(self, plugin_id: str) -> None:
        payload = self._load_payload()
        if plugin_id not in payload:
            return
        del payload[plugin_id]
        self._save_payload(payload)

    def _load_payload(self) -> dict[str, str]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {
            str(key): str(value)
            for key, value in raw.items()
            if isinstance(value, str)
        }

    def _save_payload(self, payload: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".partial")
        try:
            temporary.write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temporary.replace(self.path)
        finally:
            if temporary.exists():
                temporary.unlink()

    @classmethod
    def _protect(cls, value: bytes) -> bytes:
        return cls._crypt(value, protect=True)

    @classmethod
    def _unprotect(cls, value: bytes) -> bytes:
        return cls._crypt(value, protect=False)

    @classmethod
    def _crypt(cls, value: bytes, *, protect: bool) -> bytes:
        if os.name != "nt":
            raise PluginCredentialError(
                "Secure API key storage is available in the Windows build."
            )
        data_blob, data_buffer = cls._blob(value)
        entropy_blob, entropy_buffer = cls._blob(cls._ENTROPY)
        output_blob = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        if protect:
            succeeded = crypt32.CryptProtectData(
                ctypes.byref(data_blob),
                "Twano plugin API key",
                ctypes.byref(entropy_blob),
                None,
                None,
                cls._NO_UI,
                ctypes.byref(output_blob),
            )
        else:
            succeeded = crypt32.CryptUnprotectData(
                ctypes.byref(data_blob),
                None,
                ctypes.byref(entropy_blob),
                None,
                None,
                cls._NO_UI,
                ctypes.byref(output_blob),
            )
        # Keep these buffers alive until the Windows call has completed.
        _ = data_buffer, entropy_buffer
        if not succeeded:
            raise PluginCredentialError(
                "Windows could not protect this API key."
                if protect
                else "Windows could not unlock this API key."
            )
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            kernel32.LocalFree(output_blob.pbData)

    @staticmethod
    def _blob(value: bytes) -> tuple[_DataBlob, ctypes.Array]:
        buffer = ctypes.create_string_buffer(value)
        blob = _DataBlob(
            len(value),
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
        )
        return blob, buffer
