from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import CurrentUser, require_permission
from app.doctors import service
from app.doctors.schemas import DoctorCreate, DoctorUpdate, DoctorResponse, DoctorListResponse, DoctorSelfCreate

router = APIRouter(prefix='/doctors', tags=['Doctor Management'])


def require_hospital_admin(
    current_user: CurrentUser = Depends(require_permission('DOCTOR_CREATE')),
) -> CurrentUser:
    if current_user.role != 'HOSPITAL_ADMIN' or current_user.tenant.tenant_type != 'HOSPITAL_ORGANIZATION':
        raise HTTPException(403, 'Only hospital admins can create hospital doctors.')
    return current_user


@router.post('',  response_model=DoctorResponse, status_code=201)
def create_doctor(request: DoctorCreate, current_user: CurrentUser = Depends(require_hospital_admin)):
    return service.create_doctor(current_user.tenant, request)


@router.get('', response_model=DoctorListResponse)
def list_doctors(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), current_user: CurrentUser = Depends(require_permission('DOCTOR_VIEW'))):
    return service.list_doctors(current_user.tenant, limit, offset)


def require_individual_doctor(
    current_user: CurrentUser = Depends(require_permission('PROFILE_UPDATE')),
) -> CurrentUser:
    if current_user.role != 'DOCTOR' or current_user.tenant.tenant_type != 'INDIVIDUAL_DOCTOR':
        raise HTTPException(403, 'Individual doctor account required.')
    return current_user


@router.post('/me', response_model=DoctorResponse, status_code=201)
def create_own_profile(request: DoctorSelfCreate, current_user: CurrentUser = Depends(require_individual_doctor)):
    return service.create_own_profile(current_user, request)


@router.patch('/me', response_model=DoctorResponse)
def update_own_profile(request: DoctorUpdate, current_user: CurrentUser = Depends(require_individual_doctor)):
    if 'status' in request.model_fields_set:
        raise HTTPException(403, 'Account status must be managed by an administrator.')
    doctor = service.get_own_profile(current_user)
    return service.update_doctor(current_user.tenant, doctor['id'], request)


@router.get('/me', response_model=DoctorResponse)
def get_own_profile(current_user: CurrentUser = Depends(require_permission('PROFILE_VIEW'))):
    if current_user.role != 'DOCTOR':
        raise HTTPException(403, 'Doctor account required.')
    return service.get_own_profile(current_user)


@router.get('/{doctor_id}', response_model=DoctorResponse)
def get_doctor(doctor_id: UUID, current_user: CurrentUser = Depends(require_permission('DOCTOR_VIEW'))):
    return service.get_doctor(current_user.tenant, doctor_id)


@router.patch('/{doctor_id}', response_model=DoctorResponse)
def update_doctor(doctor_id: UUID, request: DoctorUpdate, current_user: CurrentUser = Depends(require_permission('DOCTOR_UPDATE'))):
    return service.update_doctor(current_user.tenant, doctor_id, request)
