import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from psycopg.errors import UniqueViolation

from app.core.exceptions import AdminUnauthorizedError, ConfigurationError
from app.schemas.admin import (
    AuthenticatedAdminResponse,
    CurrentAdminResponse,
    LoginAdminRequest,
    RegisterAdminRequest,
)
from app.services.admin_repository import AdminRepository


router = APIRouter(prefix="/api/v1/admins", tags=["administrators"])


def admin_repository_from_request(request: Request) -> AdminRepository:
    return request.app.state.admin_repository


def _token(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AdminUnauthorizedError()
    return token


def require_admin(
    authorization: str | None = Header(default=None),
    repository: AdminRepository = Depends(admin_repository_from_request),
) -> dict:
    return repository.from_token(_token(authorization))


def _public(account: dict) -> dict:
    return {
        "admin_id": account["id"],
        **{
            key: account[key]
            for key in ("username", "display_name", "created_at", "last_active_at")
        },
    }


@router.post("/register", response_model=AuthenticatedAdminResponse, status_code=201)
def register_admin(
    payload: RegisterAdminRequest,
    request: Request,
    repository: AdminRepository = Depends(admin_repository_from_request),
):
    expected = request.app.state.settings.admin_authcode.get_secret_value()
    if not expected.strip():
        raise ConfigurationError("管理员创建尚未启用，请配置 ADMIN_AUTHCODE")
    if not hmac.compare_digest(
        payload.authcode.get_secret_value().encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=403, detail="Authcode 不正确，无法创建管理员")
    try:
        account = repository.register(
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
        )
    except UniqueViolation:
        raise HTTPException(status_code=409, detail="管理员用户名已被使用") from None
    return AuthenticatedAdminResponse(
        **_public(account), access_token=account["access_token"]
    )


@router.post("/login", response_model=AuthenticatedAdminResponse)
def login_admin(
    payload: LoginAdminRequest,
    repository: AdminRepository = Depends(admin_repository_from_request),
):
    account = repository.login(**payload.model_dump())
    if account is None:
        raise HTTPException(status_code=401, detail="管理员用户名或密码错误")
    return AuthenticatedAdminResponse(
        **_public(account), access_token=account["access_token"]
    )


@router.get("/me", response_model=CurrentAdminResponse)
def current_admin(admin: dict = Depends(require_admin)):
    return CurrentAdminResponse(**_public(admin))


@router.post("/logout", status_code=204)
def logout_admin(
    authorization: str | None = Header(default=None),
    admin: dict = Depends(require_admin),
    repository: AdminRepository = Depends(admin_repository_from_request),
):
    repository.logout(_token(authorization))
