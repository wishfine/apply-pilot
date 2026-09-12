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
        content = secret_path.read_bytes()
        if len(content) == 32:
            return content

    secret = os.urandom(32)
    try:
        fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with open(fd, "wb") as f:
            f.write(secret)
    except FileExistsError:
        content = secret_path.read_bytes()
        if len(content) == 32:
            return content
        secret_path.write_bytes(secret)
    except OSError:
        secret_path.write_bytes(secret)
        try:
            os.chmod(secret_path, 0o600)
        except OSError:
            pass
    return secret


class AuditSanitizer:
    """Sanitizes audit events and computes collision-resistant HMAC fingerprints."""

    @staticmethod
    def compute_fingerprint(
        audit_secret: bytes,
        raw: Optional[str] = None,
        raw_value: Optional[str] = None,
    ) -> Optional[str]:
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
        field_policy: Optional[FieldPolicy] = None,
        raw_value: Optional[str] = None,
    ) -> Optional[str]:
        pol = policy if policy is not None else field_policy
        val = raw if raw is not None else raw_value
        if pol is None or val is None:
            return None

        val_str = str(val).strip()
        if not val_str:
            return None

        # Highest privacy levels must NEVER leak into logs or audit snapshots
        if pol.sensitivity in (SensitivityLevel.SENSITIVE, SensitivityLevel.SECRET):
            return None
        if pol.log_strategy == LogStrategy.OMIT:
            return None
        if pol.log_strategy == LogStrategy.MASK:
            if len(val_str) <= 4:
                return "***"
            return f"{val_str[:2]}****{val_str[-2:]}"
        return val_str
