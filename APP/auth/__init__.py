"""Authentication: OAuth exchange, password/OTP handling, JWT issuance.

Re-exports the service surface so callers import from APP.auth rather than
reaching into submodules.
"""

from APP.auth.service import (
    JWT_ALGORITHM,
    JWT_EXPIRY_DAYS,
    OAuthError,
    create_access_token,
    decode_access_token,
    exchange_github_code,
    exchange_google_code,
    generate_otp_code,
    get_current_user,
    hash_otp_code,
    hash_password,
    is_otp_expired,
    verify_otp_code,
    verify_password,
)

__all__ = [
    "JWT_ALGORITHM",
    "JWT_EXPIRY_DAYS",
    "OAuthError",
    "create_access_token",
    "decode_access_token",
    "exchange_github_code",
    "exchange_google_code",
    "generate_otp_code",
    "get_current_user",
    "hash_otp_code",
    "hash_password",
    "is_otp_expired",
    "verify_otp_code",
    "verify_password",
]
