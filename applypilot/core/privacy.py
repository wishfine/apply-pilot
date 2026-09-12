"""Privacy and audit sanitization barrier using HMAC-SHA256."""

import hashlib
import hmac
import os
from typing import Optional

from applypilot.core.config import get_app_home_dir
from applypilot.domain.base import FieldPolicy, LogStrategy, SensitivityLevel


def get_local_audit_secret() -> bytes:
    """Retrieve or generate local persistent 32-byte audit secret."""
    secret_path = get_app_home_dir() / ".audit_secret"
    if secret_path.exists():
        return secret_path.read_bytes()
    secret = os.urandom(32)
    secret_path.write_bytes(secret)
    try:
        os.chmod(secret_path, 0o600)
    except Exception:
        pass
    return secret


class AuditSanitizer:
    """Sanitizer for audit logs and LLM boundaries."""

    @staticmethod
    def compute_fingerprint(
        audit_secret: bytes,
        raw: Optional[str] = None,
        *,
        raw_value: Optional[str] = None,
    ) -> Optional[str]:
        """Compute an HMAC-SHA256 fingerprint for a raw value with whitespace normalized and lowercased."""
        val = raw if raw is not None else raw_value
        if val is None:
            return None
        normalized = str(val).strip().lower()
        sig = hmac.new(audit_secret, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"hmac-sha256:{sig}"

    @staticmethod
    def mask_value(
        policy: Optional[FieldPolicy] = None,
        raw: Optional[str] = None,
        *,
        field_policy: Optional[FieldPolicy] = None,
        raw_value: Optional[str] = None,
    ) -> Optional[str]:
        """Mask or omit a raw value based on FieldPolicy."""
        pol = policy if policy is not None else field_policy
        val = raw if raw is not None else raw_value
        if pol is None or not val:
            return None
        if pol.sensitivity in (SensitivityLevel.SENSITIVE, SensitivityLevel.SECRET):
            return None
        if pol.log_strategy == LogStrategy.OMIT:
            return None
        if pol.log_strategy == LogStrategy.MASK:
            val_str = str(val).strip()
            if len(val_str) <= 4:
                return "***"
            return f"{val_str[:2]}****{val_str[-2:]}"
        return str(val).strip()
