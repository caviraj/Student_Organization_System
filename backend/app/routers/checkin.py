from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_role
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
)
def checkin(payload: CheckinIn, staff: User = Depends(require_role("volunteer")), db: Session = Depends(get_db)):
    return check_in(db, staff, payload.event_id, payload.code)
