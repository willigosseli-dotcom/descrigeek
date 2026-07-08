"""Configuration globale de l'app : mot de passe général partagé."""
from __future__ import annotations

from datetime import datetime

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppConfig

# Mot de passe général par défaut (modifiable ensuite par un admin dans l'app).
DEFAULT_GENERAL_PASSWORD = "1984"


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


async def get_config(db: AsyncSession) -> AppConfig:
    """Retourne la ligne de config, en la créant avec le défaut si absente."""
    result = await db.execute(select(AppConfig).where(AppConfig.id == 1))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = AppConfig(id=1, general_password_hash=_hash(DEFAULT_GENERAL_PASSWORD))
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


async def verify_general_password(db: AsyncSession, password: str) -> bool:
    cfg = await get_config(db)
    if not cfg.general_password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode(), cfg.general_password_hash.encode())
    except ValueError:
        return False


async def set_general_password(db: AsyncSession, password: str) -> None:
    cfg = await get_config(db)
    cfg.general_password_hash = _hash(password)
    cfg.general_password_updated_at = datetime.utcnow()
    await db.commit()
