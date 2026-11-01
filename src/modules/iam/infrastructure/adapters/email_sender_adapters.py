import asyncio
import logging

import resend

from src.modules.iam.application.acl.ports.email_sender import EmailSender

logger = logging.getLogger(__name__)


class LogEmailSender(EmailSender):
    async def send_verification_code(self, email: str, code: str) -> None:
        logger.info("Verification code sent to %s: %s", email, code)

    async def send_password_reset(self, email: str, link: str) -> None:
        logger.info("Password reset link sent to %s: %s", email, link)


class ResendEmailSender(EmailSender):
    def __init__(self, api_key: str, from_email: str) -> None:
        self._api_key = api_key
        self._from_email = from_email

    def _send_sync(self, to_email: str, subject: str, html: str) -> None:
        resend.api_key = self._api_key
        resend.Emails.send(
            {
                "from": self._from_email,
                "to": [to_email],
                "subject": subject,
                "html": html,
            }
        )

    async def send_verification_code(self, email: str, code: str) -> None:
        await asyncio.to_thread(
            self._send_sync,
            email,
            "Tu código de verificación de Navby",
            f"<p>Tu código de verificación es <strong>{code}</strong> (válido por 10 minutos).</p>",
        )

    async def send_password_reset(self, email: str, link: str) -> None:
        await asyncio.to_thread(
            self._send_sync,
            email,
            "Restablecer contraseña en Navby",
            (
                f'<p>Restablece tu contraseña aquí: <a href="{link}">{link}</a> '
                "(válido por 30 minutos).</p>"
            ),
        )
