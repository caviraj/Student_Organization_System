from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.authz import require_permission
from app.core.config import settings
from app.core.deps import get_db
from app.models import User
from app.schemas import CheckinIn, CheckinOut
from app.services.checkin import check_in

router = APIRouter(tags=["check-in"])


@router.post(
    "/checkin",
    response_model=CheckinOut,
    summary="Scan a ticket at the door (volunteer+)",
    description=(
        "Always answers 200: VALID, ALREADY_USED, WRONG_EVENT or INVALID. Unknown ids are the "
        "door's 404, not the client's. `checked_in`/`sold` feed the scanner header counter."
    ),
    dependencies=[
        Depends(ratelimit.limit_by_user("checkin", settings.CHECKIN_PER_MINUTE, "Too many scans; slow down"))
    ],
)
def checkin(
    payload: CheckinIn, staff: User = Depends(require_permission("tickets.checkin")), db: Session = Depends(get_db)
):
    return check_in(db, staff, payload.event_id, payload.code)
