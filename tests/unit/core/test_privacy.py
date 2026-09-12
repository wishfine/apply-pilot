"""Unit tests for AuditSanitizer and secret management."""
import stat
from applypilot.core.privacy import AuditSanitizer, get_local_audit_secret
from applypilot.domain.base import FieldPolicy, SensitivityLevel, LogStrategy


def test_audit_fingerprint_hmac():
    secret = b"test_secret_key_12345"
    fp1 = AuditSanitizer.compute_fingerprint(secret, "13800138000")
    fp2 = AuditSanitizer.compute_fingerprint(secret, "13800138000 ")
    assert fp1.startswith("hmac-sha256:")
    assert fp1 == fp2  # normalized whitespace

    fp_diff = AuditSanitizer.compute_fingerprint(secret, "13800138001")
    assert fp1 != fp_diff


def test_audit_fingerprint_none():
    secret = b"test_secret_key_12345"
    assert AuditSanitizer.compute_fingerprint(secret, None) is None


def test_audit_fingerprint_case_insensitive():
    secret = b"test_secret_key_12345"
    fp1 = AuditSanitizer.compute_fingerprint(secret, "User@Example.COM")
    fp2 = AuditSanitizer.compute_fingerprint(secret, "user@example.com")
    assert fp1 == fp2


def test_mask_value_for_sensitive():
    sensitive_policy = FieldPolicy(
        path_pattern="identity.id_number",
        sensitivity=SensitivityLevel.SENSITIVE,
        llm_allowed=False,
        log_strategy=LogStrategy.MASK,
    )
    # SENSITIVE values must be completely omitted from plaintext log / preview
    masked = AuditSanitizer.mask_value(sensitive_policy, "110101200101011234")
    assert masked is None


def test_mask_value_for_secret():
    secret_policy = FieldPolicy(
        path_pattern="credentials.password",
        sensitivity=SensitivityLevel.SECRET,
        llm_allowed=False,
        log_strategy=LogStrategy.PLAIN,
    )
    # SECRET values must never be exposed regardless of log_strategy
    masked = AuditSanitizer.mask_value(secret_policy, "supersecret")
    assert masked is None


def test_mask_value_for_personal():
    personal_policy = FieldPolicy(
        path_pattern="contact.mobile",
        sensitivity=SensitivityLevel.PERSONAL,
        llm_allowed=False,
        log_strategy=LogStrategy.MASK,
    )
    masked = AuditSanitizer.mask_value(personal_policy, "13812345678")
    assert masked == "13****78"


def test_mask_value_for_short_string():
    personal_policy = FieldPolicy(
        path_pattern="contact.code",
        sensitivity=SensitivityLevel.PERSONAL,
        llm_allowed=False,
        log_strategy=LogStrategy.MASK,
    )
    assert AuditSanitizer.mask_value(personal_policy, "1234") == "***"
    assert AuditSanitizer.mask_value(personal_policy, "ab") == "***"


def test_mask_value_for_omit_strategy():
    policy = FieldPolicy(
        path_pattern="profile.hobby",
        sensitivity=SensitivityLevel.NORMAL,
        llm_allowed=True,
        log_strategy=LogStrategy.OMIT,
    )
    assert AuditSanitizer.mask_value(policy, "reading") is None


def test_mask_value_for_plain_strategy():
    policy = FieldPolicy(
        path_pattern="profile.name",
        sensitivity=SensitivityLevel.NORMAL,
        llm_allowed=True,
        log_strategy=LogStrategy.PLAIN,
    )
    assert AuditSanitizer.mask_value(policy, " Alice ") == "Alice"


def test_mask_value_empty_and_none():
    policy = FieldPolicy(
        path_pattern="contact.city",
        sensitivity=SensitivityLevel.NORMAL,
        llm_allowed=True,
        log_strategy=LogStrategy.MASK,
    )
    assert AuditSanitizer.mask_value(policy, "") is None
    assert AuditSanitizer.mask_value(policy, None) is None
    assert AuditSanitizer.mask_value(policy, "   ") is None


def test_get_local_audit_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("APPLYPILOT_HOME", str(tmp_path))
    s1 = get_local_audit_secret()
    assert isinstance(s1, bytes)
    assert len(s1) == 32
    s2 = get_local_audit_secret()
    assert s1 == s2  # persistent

    secret_file = tmp_path / ".audit_secret"
    assert secret_file.exists()
    # Check permissions (0o600 -> stat.S_IRUSR | stat.S_IWUSR)
    file_mode = stat.S_IMODE(secret_file.stat().st_mode)
    assert file_mode == 0o600
