import os
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional

from api.auth import create_jwt_token

router = APIRouter()


class TokenRequest(BaseModel):
    token: str = Field(..., description="Master API token (SENTINEL_API_TOKEN) to exchange for a JWT session")
    subject: Optional[str] = Field("sentinel_user", description="Subject/username for the JWT token")
    expires_hours: Optional[int] = Field(720, description="Token expiration window in hours (default: 30 days)")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_hours: int
    subject: str


@router.post("/token", response_model=TokenResponse)
async def exchange_token(body: TokenRequest):
    """
    Exchanges the master API token for a signed JWT session token.
    Allows clients to authenticate securely without storing the root master secret in headers indefinitely.
    """
    master_token = os.getenv("SENTINEL_API_TOKEN", "")
    if not master_token or master_token == "change_me_generate_a_real_token":
        # Auth not configured or disabled in development
        jwt_token = create_jwt_token(subject=body.subject, expires_delta_hours=body.expires_hours)
        return TokenResponse(
            access_token=jwt_token,
            token_type="bearer",
            expires_in_hours=body.expires_hours,
            subject=body.subject,
        )

    if body.token != master_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid master token",
        )

    jwt_token = create_jwt_token(subject=body.subject, expires_delta_hours=body.expires_hours)
    return TokenResponse(
        access_token=jwt_token,
        token_type="bearer",
        expires_in_hours=body.expires_hours,
        subject=body.subject,
    )
