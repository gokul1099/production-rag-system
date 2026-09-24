import os
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr
import bcrypt
import jwt
from app.models_auth import User
from app.db import init_db, get_session
from sqlmodel import select

# Initialize DB (idempotent)
init_db()

JWT_SECRET = os.getenv("JWT_SECRET", "change_me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
VALID_JWT_ALGORITHMS = {
    "HS256", "HS384", "HS512",
    "RS256", "RS384", "RS512",
    "ES256", "ES384", "ES512",
    "PS256", "PS384", "PS512",
}
if JWT_ALGORITHM not in VALID_JWT_ALGORITHMS:
    JWT_ALGORITHM = "HS256"
JWT_EXP_SECONDS = int(os.getenv("JWT_EXP_SECONDS", "3600"))

router = APIRouter()


def normalize_password_for_bcrypt(password: str) -> str:
    """Bcrypt rejects passwords longer than 72 bytes.
    Truncate to the safe limit before hashing/verifying.
    """
    return password.encode("utf-8")[:72].decode("utf-8", errors="ignore")


def hash_password(password: str) -> str:
    safe_password = normalize_password_for_bcrypt(password).encode("utf-8")
    return bcrypt.hashpw(safe_password, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    safe_password = normalize_password_for_bcrypt(password).encode("utf-8")
    try:
        return bcrypt.checkpw(safe_password, hashed_password.encode("utf-8"))
    except ValueError:
        return False


class SignupRequest(BaseModel):
    email: EmailStr
    password: str


class SigninRequest(BaseModel):
    email: EmailStr
    password: str


def create_access_token(subject: str, expires_delta: int | None = None) -> str:
    now = datetime.utcnow()
    exp = now + timedelta(seconds=(expires_delta if expires_delta is not None else JWT_EXP_SECONDS))
    payload = {"sub": str(subject), "iat": now.timestamp(), "exp": exp.timestamp()}
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(req: SignupRequest):
    with get_session() as session:
        statement = select(User).where(User.email == req.email)
        existing = session.exec(statement).first()
        if existing:
            raise HTTPException(status_code=400, detail="User already exists")

        hashed = hash_password(req.password)
        user = User(email=req.email, hashed_password=hashed)
        session.add(user)
        session.commit()
        session.refresh(user)

        token = create_access_token(subject=user.id)
        return {"access_token": token, "token_type": "bearer", "user_id": user.id}


@router.post("/signin")
def signin(req: SigninRequest):
    with get_session() as session:
        statement = select(User).where(User.email == req.email)
        user = session.exec(statement).first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if not verify_password(req.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = create_access_token(subject=user.id)
        return {"access_token": token, "token_type": "bearer", "user_id": user.id}
