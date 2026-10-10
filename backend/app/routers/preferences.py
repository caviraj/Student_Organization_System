"""Email preferences and unsubscribe (PRD FR-3.3)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models import User
from app.schemas import EmailPreferencesIn, EmailPreferencesOut, UnsubscribeOut
from app.services.unsubscribe import apply_unsubscribe, mask_email

router = APIRouter(tags=["Preferences"])


@router.get(
    "/users/me/email-preferences",
    response_model=EmailPreferencesOut,
    summary="My announcement-email preference",
)
def get_email_preferences(user: User = Depends(get_current_user)):
    return {"email": user.email, "email_opt_in": user.email_opt_in}


@router.post(
    "/users/me/email-preferences",
    response_model=EmailPreferencesOut,
    summary="Turn announcement emails on or off",
)
def set_email_preferences(
    payload: EmailPreferencesIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Off means off immediately: mail already queued for this member is dropped, not sent."""
    user.email_opt_in = payload.email_opt_in
    db.commit()
    return {"email": user.email, "email_opt_in": user.email_opt_in}


@router.get(
    "/unsubscribe",
    response_model=UnsubscribeOut,
    summary="Unsubscribe with the link from an email (public)",
)
def unsubscribe(
    token: str = Query(description="Signed token from the email footer", examples=["eyJhbGciOi..."]),
    db: Session = Depends(get_db),
):
    """Public by design: it has to work from a mail client, where there is no session. The token
    is what proves which inbox is being unsubscribed."""
    return {"unsubscribed": True, "email": mask_email(apply_unsubscribe(db, token))}
