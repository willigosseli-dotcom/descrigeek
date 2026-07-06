"""Accès aux réglages du moteur d'évaluation (table `eval_settings`, ligne unique)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EvalSetting


DEFAULTS = {
    "fenetre_annees": 2,
    "inclure_projets_bricoleur": False,
    "decote_bricoleur_pct": 40,
    "ponderation_particulier_pct": 15,
    "tolerance_longueur_pi": 2.0,
}


async def get_settings(db: AsyncSession) -> EvalSetting:
    """Retourne la ligne de réglages, en la créant avec les défauts si absente."""
    result = await db.execute(select(EvalSetting).where(EvalSetting.id == 1))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = EvalSetting(id=1, **DEFAULTS)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


async def save_settings(db: AsyncSession, *, fenetre_annees: int,
                        inclure_projets_bricoleur: bool, decote_bricoleur_pct: int,
                        ponderation_particulier_pct: int,
                        tolerance_longueur_pi: float) -> EvalSetting:
    settings = await get_settings(db)
    settings.fenetre_annees = max(0, fenetre_annees)
    settings.inclure_projets_bricoleur = inclure_projets_bricoleur
    settings.decote_bricoleur_pct = max(0, min(100, decote_bricoleur_pct))
    settings.ponderation_particulier_pct = max(0, min(100, ponderation_particulier_pct))
    settings.tolerance_longueur_pi = max(0.0, tolerance_longueur_pi)
    await db.commit()
    await db.refresh(settings)
    return settings
