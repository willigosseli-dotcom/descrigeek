from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import Session
from app.models import Base, User
import os
import bcrypt

_raw_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/descrigeek.db")

# Railway fournit parfois "postgres://" au lieu de "postgresql+asyncpg://"
if _raw_url.startswith("postgres://"):
    _raw_url = _raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif _raw_url.startswith("postgresql://"):
    _raw_url = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

DATABASE_URL = _raw_url
_is_postgres = DATABASE_URL.startswith("postgresql")

_engine_kwargs = {"echo": False}
_connect_args = {}
if _is_postgres:
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 10
    _engine_kwargs["pool_pre_ping"] = True
    _connect_args = {"ssl": "require"}
    print(f"[DB] PostgreSQL connecté : {DATABASE_URL[:50]}...")
else:
    print(f"[DB] SQLite local : {DATABASE_URL}")

engine = create_async_engine(DATABASE_URL, connect_args=_connect_args, **_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            if _is_postgres:
                from sqlalchemy import text
                await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(500);"))
                await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_data TEXT;"))
        await create_default_admin()
    except Exception as e:
        print(f"[DB] Erreur init_db (non-bloquante) : {e}")


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
