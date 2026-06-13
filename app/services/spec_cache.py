"""Gestion du cache des specs trouvées en ligne."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import SpecsCache
from datetime import datetime


async def get_cached_specs(db: AsyncSession, year: int, make: str, model: str) -> SpecsCache | None:
    result = await db.execute(
        select(SpecsCache).where(
            SpecsCache.vehicle_year == year,
            SpecsCache.vehicle_make.ilike(make),
            SpecsCache.vehicle_model.ilike(model),
        )
    )
    return result.scalar_one_or_none()


async def save_specs_to_cache(
    db: AsyncSession,
    year: int, make: str, model: str, vehicle_type: str,
    specs_data: dict,
    source_url: str = "",
    source_name: str = "",
    source_type: str = "web",
) -> SpecsCache:
    # Vérifier si déjà en cache
    existing = await get_cached_specs(db, year, make, model)
    if existing:
        existing.specs_data = specs_data
        existing.source_url = source_url
        existing.source_name = source_name
        existing.source_type = source_type
        existing.cached_at = datetime.utcnow()
        await db.commit()
        return existing

    entry = SpecsCache(
        vehicle_year=year,
        vehicle_make=make,
        vehicle_model=model,
        vehicle_type=vehicle_type,
        specs_data=specs_data,
        source_url=source_url,
        source_name=source_name,
        source_type=source_type,
    )
    db.add(entry)
    await db.commit()
    return entry
