from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response

from backend.app.api.auth_utils import (
    clear_auth_cookie,
    get_request_token,
    require_current_user,
    set_auth_cookie,
)
from backend.app.models.schemas import (
    AuthLoginRequest,
    AuthResponse,
    AuthSignupRequest,
    AuthUser,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
)
from backend.app.services.mailer import MailDeliveryError, SmtpMailer


router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)

def normalize_email(email: str) -> str:
    return email.strip().lower()


@router.post("/auth/signup", response_model=AuthResponse)
def signup(payload: AuthSignupRequest, request: Request, response: Response) -> AuthResponse:
    store = request.app.state.session_store
    full_name = payload.full_name.strip()
    email = normalize_email(payload.email)
    password = payload.password.strip()
    state = payload.state.strip() if payload.state and payload.state.strip() else None

    if len(full_name) < 2:
        raise HTTPException(status_code=400, detail="Full name must be at least 2 characters")
    if "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if store.get_user_by_email(email):
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = store.create_user(full_name=full_name, email=email, password=password, state=state)
    token = store.create_auth_session(user["id"], request.app.state.settings.auth_session_duration_days)
    set_auth_cookie(response, request, token)
    return AuthResponse(token=token, user=AuthUser(**user))


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: AuthLoginRequest, request: Request, response: Response) -> AuthResponse:
    store = request.app.state.session_store
    user = store.authenticate_user(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = store.create_auth_session(user["id"], request.app.state.settings.auth_session_duration_days)
    set_auth_cookie(response, request, token)
    return AuthResponse(token=token, user=AuthUser(**user))


@router.get("/auth/me", response_model=AuthUser)
def me(request: Request) -> AuthUser:
    user = require_current_user(request)
    logger.info("/auth/me authenticated user_id=%s email=%s", user.get("id"), user.get("email"))
    return AuthUser(**user)


@router.post("/auth/logout", response_model=MessageResponse)
def logout(request: Request, response: Response) -> MessageResponse:
    token = get_request_token(request)
    if token:
        request.app.state.session_store.delete_auth_session(token)
    clear_auth_cookie(response, request)
    return MessageResponse(message="Logged out successfully.")


@router.post("/auth/password-reset", response_model=MessageResponse)
def password_reset(payload: PasswordResetRequest, request: Request) -> MessageResponse:
    settings = request.app.state.settings
    if not settings.smtp_configured:
        raise HTTPException(status_code=503, detail="Password reset email is not configured yet.")

    email = normalize_email(payload.email)
    user = request.app.state.session_store.get_user_by_email(email)
    if user:
        token = request.app.state.session_store.create_password_reset_token(
            user_id=user["id"],
            ttl_minutes=settings.password_reset_token_ttl_minutes,
        )
        reset_url = SmtpMailer(settings).build_password_reset_url(token)
        try:
            SmtpMailer(settings).send_password_reset_email(recipient_email=user["email"], reset_url=reset_url)
        except MailDeliveryError as exc:
            raise HTTPException(status_code=502, detail="Password reset email could not be sent.") from exc

    return MessageResponse(message="If an account with this email exists, a password reset link has been sent.")


@router.post("/auth/password-reset/confirm", response_model=MessageResponse)
def password_reset_confirm(payload: PasswordResetConfirmRequest, request: Request) -> MessageResponse:
    token = payload.token.strip()
    password = payload.password.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Reset token is required.")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    user = request.app.state.session_store.reset_password_with_token(token=token, new_password=password)
    if not user:
        raise HTTPException(status_code=400, detail="Reset link is invalid or has expired.")
    return MessageResponse(message="Your password has been reset. Please log in with your new password.")
