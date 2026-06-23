from email import message_from_bytes
import socket

import pytest
from aiosmtpd.controller import Controller

from app.config import settings
from app.services.user_service import UserManager


class MessageHandler:
    message = None

    async def handle_DATA(self, server, session, envelope):
        self.message = envelope.content
        return "250 OK"


def test_password_reset_email_is_delivered_to_local_smtp_server(monkeypatch):
    handler = MessageHandler()
    try:
        with socket.socket() as socket_:
            socket_.bind(("127.0.0.1", 0))
            port = socket_.getsockname()[1]
    except PermissionError:
        pytest.skip("This environment does not permit binding a local SMTP test server")
    controller = Controller(handler, hostname="127.0.0.1", port=port)
    controller.start()
    try:
        monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
        monkeypatch.setattr(settings, "SMTP_PORT", controller.port)
        monkeypatch.setattr(settings, "SMTP_SENDER", "noreply@example.test")
        monkeypatch.setattr(settings, "SMTP_USE_TLS", False)
        manager = UserManager(user_crud=None, db_context=None)

        manager._send_password_reset_email(
            "user@example.test", "https://example.test/reset?token=test"
        )

        message = message_from_bytes(handler.message)
        assert message["To"] == "user@example.test"
        assert "token=test" in message.get_payload(decode=True).decode()
    finally:
        controller.stop()
