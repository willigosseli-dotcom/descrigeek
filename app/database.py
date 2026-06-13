from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import Session
from app.models import Base, User
import os
import bcrypt

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/descrigeek.db")

# PostgreSQL en production : désactiver les pool settings SQLite-incompatibles
_is_postgres = DATABASE_URL.startswith("postgresql")
_engine_kwargs = {"echo": False}
if _is_postgres:
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 10
    _engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await create_default_admin()


async def create_default_admin():
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.username == "admin"))
        existing = result.scalar_one_or_none()
        if not existing:
            hashed = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
            admin = User(
                username="admin",
                full_name="Administrateur",
                hashed_password=hashed,
                role="admin",
                email="admin@vrthetford.com",
            )
            session.add(admin)
            await session.commit()
            print("[OK] Compte admin cree : admin / admin123 (changez ce mot de passe!)")
