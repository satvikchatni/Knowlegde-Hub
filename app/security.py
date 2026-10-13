from pwdlib import PasswordHash
import uuid
from datetime import datetime,timedelta,timezone
import jwt
from app.config import settings
password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)

def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}#str(...) is needed because JSON has no UUID type, and the library requires sub to be a string.
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    return token