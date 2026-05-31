"""
Tests for security utilities — encryption, JWT, and authentication.
"""

import pytest
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    check_permission,
    UserRole,
)


class TestPasswordHashing:
    """Tests for bcrypt password hashing."""

    def test_hash_password(self):
        """Should produce a bcrypt hash."""
        hashed = hash_password("MySecurePassword123!")
        assert hashed != "MySecurePassword123!"
        assert hashed.startswith("$2b$")

    def test_verify_correct_password(self):
        """Should verify correct password."""
        hashed = hash_password("TestPass456!")
        assert verify_password("TestPass456!", hashed) is True

    def test_verify_wrong_password(self):
        """Should reject wrong password."""
        hashed = hash_password("CorrectPassword")
        assert verify_password("WrongPassword", hashed) is False

    def test_different_hashes_same_password(self):
        """Same password should produce different hashes (salt)."""
        hash1 = hash_password("SamePassword")
        hash2 = hash_password("SamePassword")
        assert hash1 != hash2  # Different salts


class TestJWTTokens:
    """Tests for JWT token creation and validation."""

    def test_create_access_token(self):
        """Should create a valid JWT access token."""
        token = create_access_token("user-123", "admin", UserRole.ADMIN)
        assert token is not None
        assert len(token) > 0

    def test_decode_valid_token(self):
        """Should decode a valid token successfully."""
        token = create_access_token("user-456", "testuser", UserRole.OPERATOR)
        payload = decode_token(token)

        assert payload is not None
        assert payload["sub"] == "user-456"
        assert payload["username"] == "testuser"
        assert payload["role"] == "operator"
        assert payload["type"] == "access"

    def test_decode_invalid_token(self):
        """Should return None for invalid token."""
        payload = decode_token("invalid.jwt.token")
        assert payload is None

    def test_decode_tampered_token(self):
        """Should reject a tampered token."""
        token = create_access_token("user-789", "hacker", UserRole.VIEWER)
        tampered = token[:-5] + "XXXXX"
        payload = decode_token(tampered)
        assert payload is None

    def test_refresh_token_type(self):
        """Refresh token should have correct type."""
        token = create_refresh_token("user-123", "admin", UserRole.ADMIN)
        payload = decode_token(token)

        assert payload["type"] == "refresh"

    def test_token_contains_jti(self):
        """Tokens should have unique JTI for revocation."""
        token1 = create_access_token("user-1", "u1", UserRole.ADMIN)
        token2 = create_access_token("user-1", "u1", UserRole.ADMIN)

        payload1 = decode_token(token1)
        payload2 = decode_token(token2)

        assert payload1["jti"] != payload2["jti"]


class TestRBAC:
    """Tests for role-based access control."""

    def test_admin_full_access(self):
        """Admin should have access to everything."""
        assert check_permission(UserRole.ADMIN, "credentials:read") is True
        assert check_permission(UserRole.ADMIN, "credentials:write") is True
        assert check_permission(UserRole.ADMIN, "kill_switch:activate") is True
        assert check_permission(UserRole.ADMIN, "users:write") is True

    def test_operator_limited_access(self):
        """Operator should have limited access."""
        assert check_permission(UserRole.OPERATOR, "metrics:read") is True
        assert check_permission(UserRole.OPERATOR, "kill_switch:activate") is True
        assert check_permission(UserRole.OPERATOR, "credentials:read") is False
        assert check_permission(UserRole.OPERATOR, "users:write") is False

    def test_viewer_readonly(self):
        """Viewer should only have read access to metrics."""
        assert check_permission(UserRole.VIEWER, "metrics:read") is True
        assert check_permission(UserRole.VIEWER, "trades:read") is True
        assert check_permission(UserRole.VIEWER, "credentials:read") is False
        assert check_permission(UserRole.VIEWER, "kill_switch:activate") is False
        assert check_permission(UserRole.VIEWER, "webhooks:write") is False
