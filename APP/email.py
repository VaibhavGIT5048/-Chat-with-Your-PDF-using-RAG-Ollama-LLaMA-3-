"""Azure Communication Services Email client for OTP delivery."""

from __future__ import annotations

import os

from azure.communication.email import EmailClient

from APP.email_templates import OTP_SUBJECT, otp_html, otp_plaintext

# NOTE: the "From" display name recipients see (currently the bare
# "DoNotReply") is NOT settable per-message — ACS rejects the RFC 5322
# "Name <addr>" form on senderAddress with a 400 (verified). It's domain
# configuration on the sender username instead:
#   az communication email domain sender-username update \
#     --email-service-name <acs-email-resource> -g rag-api-rg \
#     --domain-name <domain> --sender-username DoNotReply \
#     --display-name "Grounded-RAG"
# (or Portal: Email Communication Service -> Provision domains -> <domain>
#  -> MailFrom addresses -> edit Display name).
OTP_EXPIRY_MINUTES = 10

_client: EmailClient | None = None


def _get_client() -> EmailClient:
    global _client
    if _client is None:
        connection_string = os.getenv("ACS_PRIMARY_CONNECTION_STRING")
        if not connection_string:
            raise RuntimeError("ACS_PRIMARY_CONNECTION_STRING is not set")
        _client = EmailClient.from_connection_string(connection_string)
    return _client


def send_otp_email(to_address: str, code: str) -> None:
    sender_address = os.getenv("ACS_SENDER_ADDRESS")
    if not sender_address:
        raise RuntimeError("ACS_SENDER_ADDRESS is not set")

    message = {
        "senderAddress": sender_address,
        "recipients": {"to": [{"address": to_address}]},
        "content": {
            "subject": OTP_SUBJECT,
            "plainText": otp_plaintext(code, OTP_EXPIRY_MINUTES),
            "html": otp_html(code, OTP_EXPIRY_MINUTES),
        },
    }
    poller = _get_client().begin_send(message)
    poller.result()
