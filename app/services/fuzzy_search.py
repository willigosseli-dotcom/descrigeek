"""Recherche floue (tolérante aux fautes) sur marque / ligne / modèle.

Utilise rapidfuzz. Normalisation : minuscules, sans accents, tirets→espaces,
espaces multiples réduits, trim. Fonctionne identiquement sur SQLite et Postgres
(le calcul se fait en Python), sans extension ni migration.
"""
from __future__ import annotations

import unicodedata
from typing import Optional

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Listing

# Seuil de similarité par défaut (0..100 ≈ 0.45). Ajustable.
SEUIL_DEFAUT = 45


def normaliser(s: Optional[str]) -> str:
    if not s:
        return ""
    t = unicodedata.normalize("NFD", str(s))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.lower().replace("-", " ")
    return " ".join(t.split())


def _label(combo: dict) -> str:
    parts = [combo.get("marque"), combo.get("ligne"), combo.get("modele")]
    return " · ".join(p for p in parts if p)


def _texte_combo(combo: dict) -> str:
    return normaliser(" ".join(str(combo.get(k) or "") for k in ("marque", "ligne", "modele")))


def classer(q: str, combos: list[dict], *, champ: Optional[str] = None,
            limit: int = 8, seuil: int = SEUIL_DEFAUT) -> list[tuple]:
    """Classe des combos (marque/ligne/modele) par similarité à `q`.

    Compare toujours au texte combiné ; si `champ` est fourni, prend aussi en
    compte la similarité à ce seul champ (le meilleur des deux).
    """
    qn = normaliser(q)
    if not qn:
        return []
    resultats = []
    for c in combos:
        score = fuzz.WRatio(qn, _texte_combo(c))
        if champ:
            texte_champ = normaliser(c.get(champ))
            if texte_champ:
                score = max(score, fuzz.WRatio(qn, texte_champ))
        if score >= seuil:
            resultats.append((score, c))
    resultats.sort(key=lambda t: t[0], reverse=True)
    return resultats[:limit]


async def combos_distincts(db: AsyncSession, type_unite: Optional[str] = None) -> list[dict]:
    """Combos (marque, ligne, modele) distincts présents dans les annonces."""
    q = select(Listing.type_unite, Listing.marque, Listing.ligne, Listing.modele).where(
        Listing.marque.isnot(None)
    )
    if type_unite:
        q = q.where(Listing.type_unite == type_unite)
    rows = (await db.execute(q)).all()
    vus, out = set(), []
    for tu, marque, ligne, modele in rows:
        key = (normaliser(marque), normaliser(ligne), normaliser(modele))
        if key in vus:
            continue
        vus.add(key)
        out.append({"type_unite": tu, "marque": marque, "ligne": ligne, "modele": modele})
    return out


async def suggestions(db: AsyncSession, q: str, *, champ: Optional[str] = None,
                      type_unite: Optional[str] = None, limit: int = 8) -> list[dict]:
    combos = await combos_distincts(db, type_unite)
    return [
        {**c, "label": _label(c), "score": int(s)}
        for s, c in classer(q, combos, champ=champ, limit=limit)
    ]


async def matches_proches(db: AsyncSession, *, type_unite: Optional[str], marque: str = "",
                          ligne: str = "", modele: str = "", limit: int = 5,
                          seuil: int = SEUIL_DEFAUT) -> list[dict]:
    """Meilleures correspondances canoniques pour des entrées floues (« Vouliez-vous dire… »)."""
    combos = await combos_distincts(db, type_unite)
    q = " ".join(x for x in (marque, ligne, modele) if x and x.strip())
    return [
        {**c, "label": _label(c)}
        for s, c in classer(q, combos, limit=limit, seuil=seuil)
    ]
