from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import CurrentUser, require_permission
from app.patients.schemas import PatientCreate, PatientResponse
from app.patients.service import create_patient

router = APIRouter(prefix='/patients', tags=['Patient Management'])


def require_patient_creator(
    current_user: CurrentUser = Depends(require_permission('PATIENT_CREATE')),
) -> CurrentUser:
    if current_user.role != 'DOCTOR':
        raise HTTPException(403, 'Only doctors can create patients.')
    return current_user


@router.post('', response_model=PatientResponse, status_code=201)
def post_patient(
    request: PatientCreate,
    current_user: CurrentUser = Depends(require_patient_creator),
):
    return create_patient(current_user, request)
