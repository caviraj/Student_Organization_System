"""Email (PRD FR-3.3).

`ConsoleEmailProvider` is the M1 stand-in: it renders the real message and logs it instead of
sending it. A real provider (Resend, SMTP) is one more class behind the same interface, selected
by `EMAIL_PROVIDER` - no other file changes (M2-P2).
"""

import logging
from abc import ABC, abstractmethod
from html import escape

from app.core.config import settings
from app.models import Announcement, User
from app.services.unsubscribe import create_unsubscribe_token

log = logging.getLogger("ssa.mailer")

# Demo hook: a recipient at this domain always fails, so the retry/failure path is demonstrable
# without a broken mail server or a fake bounce API.
FAILURE_DOMAIN = "fail.test"


class EmailSendError(RuntimeError):
    """The provider refused the message. The worker records the text and retries."""


class EmailProvider(ABC):
    @abstractmethod
    def send(self, to_email: str, subject: str, html: str, text: str) -> None:
        """Deliver one message, or raise. Failure is an exception, never a return value - the
        worker needs a reason to store, and there is only one way to say "no"."""


class ConsoleEmailProvider(EmailProvider):
    def send(self, to_email: str, subject: str, html: str, text: str) -> None:
        if to_email.lower().endswith(f"@{FAILURE_DOMAIN}"):
            raise EmailSendError(f"simulated delivery failure for {FAILURE_DOMAIN}")
        log.info("email -> %s | %s\n%s", to_email, subject, text)


_PROVIDERS = {"console": ConsoleEmailProvider}


def get_provider() -> EmailProvider:
    try:
        return _PROVIDERS[settings.EMAIL_PROVIDER]()
    except KeyError:
        raise RuntimeError(
            f"Unknown EMAIL_PROVIDER {settings.EMAIL_PROVIDER!r}; known: {', '.join(sorted(_PROVIDERS))}"
        ) from None


def render(announcement: Announcement, user: User) -> tuple[str, str, str]:
    """(subject, html, text). Both parts carry the same content: some members read mail in a
    terminal, and a text part is what keeps a real provider out of the spam folder."""
    subject = f"[SSA] {announcement.category}: {announcement.title}"
    feed_url = f"{settings.FRONTEND_URL.rstrip('/')}/announcements/{announcement.id}"
    unsubscribe_url = f"{settings.FRONTEND_URL.rstrip('/')}/unsubscribe?token={create_unsubscribe_token(user)}"

    text = (
        f"{announcement.title}\n\n"
        f"{announcement.body}\n\n"
        f"Read it on the website: {feed_url}\n\n"
        f"Don't want these emails? Unsubscribe: {unsubscribe_url}\n"
    )
    body_html = escape(announcement.body).replace("\n", "<br>")
    html = (
        f"<h2>{escape(announcement.title)}</h2>"
        f'<p style="color:#475569;text-transform:uppercase;font-size:12px">{escape(announcement.category)}</p>'
        f"<p>{body_html}</p>"
        f'<p><a href="{feed_url}">Read it on the website</a></p>'
        f'<p style="font-size:12px;color:#64748b">'
        f'<a href="{unsubscribe_url}">Unsubscribe from announcement emails</a></p>'
    )
    return subject, html, text
