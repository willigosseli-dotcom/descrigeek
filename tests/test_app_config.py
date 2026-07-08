"""Tests du mot de passe général de l'application (app_config)."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.services import app_config


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Maker = async_sessionmaker(engine, expire_on_commit=False)
    async with Maker() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_defaut_1984_seede_automatiquement(session):
    # get_config crée la ligne avec le mot de passe par défaut
    await app_config.get_config(session)
    assert await app_config.verify_general_password(session, "1984") is True
    assert await app_config.verify_general_password(session, "mauvais") is False


@pytest.mark.asyncio
async def test_changement_mot_de_passe_general(session):
    await app_config.set_general_password(session, "nouveau2025")
    assert await app_config.verify_general_password(session, "nouveau2025") is True
    assert await app_config.verify_general_password(session, "1984") is False
