"""Classification de la gamme de qualité de fabrication d'un modèle de VR.

Au niveau marque + ligne. Classée automatiquement (IA Anthropic) avec repli
heuristique en mode démo / sans clé API, puis corrigeable à la main.
Résultats mis en cache dans la table `gammes_modeles`.
"""
from __future__ import annotations

import os
import json
import unicodedata
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GammeModele, Listing

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

GAMMES = ["entrée", "milieu", "haut"]


def norm(value: Optional[str]) -> str:
    if value is None:
        return ""
    txt = unicodedata.normalize("NFD", str(value))
    txt = "".join(c for c in txt if unicodedata.category(c) != "Mn")
    return txt.strip().lower()


def cle(marque: Optional[str], ligne: Optional[str]) -> tuple:
    return (norm(marque), norm(ligne))


# --------------------------------------------------------------------------- #
# Repli heuristique (mode démo / sans clé API)
# --------------------------------------------------------------------------- #

# Indices de gamme par mots-clés de marque/ligne (marché québécois courant).
_HEURISTIQUE = {
    "haut": ["rockwood", "flagstaff", "grand design", "imagine", "reflection",
             "arctic fox", "outdoors rv", "northwood", "lance", "escape",
             "bigfoot", "oliver", "airstream", "montana", "alliance", "brinkley"],
    "milieu": ["jayco", "jay feather", "jay flight", "eagle", "coachmen",
               "keystone", "cougar", "sprinter", "bullet", "micro minnie",
               "winnebago", "gulf stream", "prime time"],
    "entrée": ["salem", "wildwood", "coleman", "springdale", "passport",
               "catalina", "shasta", "conquest", "kodiak", "aspen trail",
               "avenger", "della terra", "trail runner"],
}


def _classer_heuristique(marque: Optional[str], ligne: Optional[str]) -> dict:
    texte = norm(marque) + " " + norm(ligne)
    for gamme, motifs in _HEURISTIQUE.items():
        if any(m in texte for m in motifs):
            return {
                "gamme": gamme, "murs": None, "substrat": None, "plancher": None,
                "justification": "Classement approximatif (mode démo, sans IA).",
                "source": "démo",
            }
    return {
        "gamme": None, "murs": None, "substrat": None, "plancher": None,
        "justification": "Non déterminé en mode démo — à classer par IA ou à la main.",
        "source": "démo",
    }


# --------------------------------------------------------------------------- #
# Classification par IA (Anthropic)
# --------------------------------------------------------------------------- #

def _classer_ia(type_unite: Optional[str], marque: str, ligne: Optional[str]) -> dict:
    prompt = f"""Tu es un expert en véhicules récréatifs (VR) pour le marché québécois.
Classe la GAMME DE QUALITÉ DE FABRICATION de ce modèle de VR :

Type : {type_unite or 'roulotte'}
Marque : {marque}
Ligne / gamme : {ligne or '(non précisée)'}

Base-toi sur la qualité de construction réelle : type de murs (fibre de verre
lamellée vs aluminium « stick-and-tin »), substrat des murs (Azdel vs bois/Luan),
plancher (contreplaqué vs OSB), robustesse générale, isolation 4 saisons.

Réponds UNIQUEMENT en JSON avec exactement ces clés :
{{
  "gamme": "entrée" | "milieu" | "haut",
  "murs": "ex. fibre de verre lamellée / aluminium",
  "substrat": "ex. Azdel / bois (Luan)",
  "plancher": "ex. contreplaqué / OSB",
  "justification": "une phrase courte expliquant le classement"
}}
Si tu ne connais pas ce modèle précis, base-toi sur la réputation de la marque/ligne
et indique-le dans la justification."""

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    content = message.content[0].text.strip()
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()
    data = json.loads(content)

    gamme = norm(data.get("gamme"))
    if gamme not in [norm(g) for g in GAMMES]:
        gamme_valide = None
    else:
        gamme_valide = {norm(g): g for g in GAMMES}[gamme]
    return {
        "gamme": gamme_valide,
        "murs": data.get("murs"),
        "substrat": data.get("substrat"),
        "plancher": data.get("plancher"),
        "justification": data.get("justification"),
        "source": "IA",
    }


def classer(type_unite: Optional[str], marque: str, ligne: Optional[str]) -> dict:
    """Classe un modèle. Utilise l'IA si disponible, sinon l'heuristique de démo."""
    if DEMO_MODE or not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "your_anthropic_key_here":
        return _classer_heuristique(marque, ligne)
    try:
        return _classer_ia(type_unite, marque, ligne)
    except Exception as e:
        res = _classer_heuristique(marque, ligne)
        res["justification"] = f"IA indisponible ({e}); repli heuristique."
        return res


# --------------------------------------------------------------------------- #
# Accès base
# --------------------------------------------------------------------------- #

async def charger_map(db: AsyncSession) -> dict:
    """Retourne un dict {(marque_norm, ligne_norm): GammeModele}."""
    result = await db.execute(select(GammeModele))
    return {cle(g.marque, g.ligne): g for g in result.scalars().all()}


async def lignes_distinctes(db: AsyncSession) -> list[dict]:
    """Marque + ligne distinctes présentes dans les annonces (non vides)."""
    result = await db.execute(
        select(Listing.type_unite, Listing.marque, Listing.ligne).where(Listing.marque.isnot(None))
    )
    vues, sorties = set(), []
    for type_unite, marque, ligne in result.all():
        k = cle(marque, ligne)
        if k in vues:
            continue
        vues.add(k)
        sorties.append({"type_unite": type_unite, "marque": marque, "ligne": ligne})
    sorties.sort(key=lambda d: (norm(d["marque"]), norm(d["ligne"])))
    return sorties


async def classer_manquantes(db: AsyncSession) -> dict:
    """Classe automatiquement les marque+ligne pas encore classées. Ne touche pas
    les entrées corrigées à la main (`is_manuel`)."""
    existantes = await charger_map(db)
    a_faire = [
        d for d in await lignes_distinctes(db)
        if cle(d["marque"], d["ligne"]) not in existantes
        or (existantes[cle(d["marque"], d["ligne"])].gamme is None
            and not existantes[cle(d["marque"], d["ligne"])].is_manuel)
    ]
    nb = 0
    for d in a_faire:
        res = classer(d["type_unite"], d["marque"], d["ligne"])
        await upsert(db, d["type_unite"], d["marque"], d["ligne"], res, is_manuel=False)
        nb += 1
    return {"classees": nb, "total_lignes": len(await lignes_distinctes(db))}


async def upsert(db: AsyncSession, type_unite, marque, ligne, data: dict,
                 is_manuel: bool = False) -> GammeModele:
    existantes = await charger_map(db)
    g = existantes.get(cle(marque, ligne))
    if g is None:
        g = GammeModele(marque=marque, ligne=ligne)
        db.add(g)
    g.type_unite = type_unite
    g.gamme = data.get("gamme")
    g.murs = data.get("murs")
    g.substrat = data.get("substrat")
    g.plancher = data.get("plancher")
    g.justification = data.get("justification")
    g.source = "manuel" if is_manuel else data.get("source", "IA")
    g.is_manuel = is_manuel
    g.cached_at = datetime.utcnow()
    await db.commit()
    return g
