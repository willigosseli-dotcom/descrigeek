"""Import du CSV maître d'annonces de VR usagés.

Schéma attendu : 19 colonnes, séparateur virgule, UTF-8, en-tête sur la 1re ligne,
champs quotés pour ceux contenant des virgules (ex. localisation « Ville, QC »).

  type_unite, marque, ligne, modele, annee, prix_affiche, vendeur, type_vendeur,
  localisation, longueur_pi, kilometrage, etat_declare, extensions, url_annonce,
  date_collecte, date_derniere_observation, statut, ancien_prix, notes

À l'import :
  - `N/D` (et vide) → None
  - prix nettoyés vers un entier (retire $, espaces, séparateurs)
  - clé stable = url_annonce (upsert d'un import à l'autre)
  - annonces absentes du nouvel import → marquées « disparues »
  - baisses de prix détectées (nouveau prix < prix précédent)
"""
from __future__ import annotations

import csv
import io
import unicodedata
from datetime import datetime, date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Listing, ImportBatch


COLONNES_ATTENDUES = [
    "type_unite", "marque", "ligne", "modele", "annee", "prix_affiche",
    "vendeur", "type_vendeur", "localisation", "longueur_pi", "kilometrage",
    "etat_declare", "extensions", "url_annonce", "date_collecte",
    "date_derniere_observation", "statut", "ancien_prix", "notes",
]


class ImportError_(Exception):
    """Erreur d'import lisible pour l'utilisateur final."""


# --------------------------------------------------------------------------- #
# Nettoyage de valeurs
# --------------------------------------------------------------------------- #

def _norm(value: Optional[str]) -> str:
    if value is None:
        return ""
    txt = unicodedata.normalize("NFD", str(value))
    txt = "".join(c for c in txt if unicodedata.category(c) != "Mn")
    return txt.strip().lower()


def _clean_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip()
    if v == "" or v.upper() == "N/D":
        return None
    return v


def _clean_int(value: Optional[str]) -> Optional[int]:
    """Nettoie un entier : retire $, espaces, séparateurs de milliers, décimales."""
    v = _clean_str(value)
    if v is None:
        return None
    # Garder seulement les chiffres (et un éventuel point décimal)
    digits = "".join(c for c in v if c.isdigit() or c == ".")
    if not digits:
        return None
    try:
        return int(round(float(digits)))
    except ValueError:
        return None


def _clean_float(value: Optional[str]) -> Optional[float]:
    v = _clean_str(value)
    if v is None:
        return None
    v = v.replace(",", ".")
    digits = "".join(c for c in v if c.isdigit() or c == ".")
    if not digits or digits == ".":
        return None
    try:
        return float(digits)
    except ValueError:
        return None


def _clean_date(value: Optional[str]) -> Optional[date]:
    v = _clean_str(value)
    if v is None:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _extraire_ville(localisation: Optional[str]) -> Optional[str]:
    """« Thetford Mines, QC » → « Thetford Mines »."""
    v = _clean_str(localisation)
    if v is None:
        return None
    return v.split(",")[0].strip() or None


# --------------------------------------------------------------------------- #
# Détection des cas limites (drapeaux)
# --------------------------------------------------------------------------- #

def detecter_drapeaux(notes: Optional[str], prix: Optional[int],
                      localisation: Optional[str], url: Optional[str]) -> dict:
    n = _norm(notes)
    loc = _norm(localisation)
    u = _norm(url)

    is_usd = "usd" in n
    is_sur_demande = (prix is None) or ("sur demande" in n)
    is_volee = "volee" in n  # couvre VOLÉE / volée / volee après normalisation
    is_bricoleur = "bricoleur" in n
    is_doublon = "doublon" in n
    # Nos propres annonces : Facebook Marketplace à Thetford Mines
    is_notre = ("notre annonce" in n or "nos annonces" in n) or (
        "thetford" in loc and ("facebook" in u or "marketplace" in u)
    )
    return {
        "is_usd": is_usd,
        "is_prix_sur_demande": is_sur_demande,
        "is_volee": is_volee,
        "is_projet_bricoleur": is_bricoleur,
        "is_doublon": is_doublon,
        "is_notre_annonce": is_notre,
    }


# --------------------------------------------------------------------------- #
# Parsing du CSV
# --------------------------------------------------------------------------- #

def parser_csv(contenu: str) -> list[dict]:
    """Parse le texte CSV en une liste de dictionnaires normalisés.

    Lève ImportError_ si l'en-tête ne correspond pas au schéma attendu.
    """
    # Retirer un éventuel BOM
    if contenu and contenu[0] == "﻿":
        contenu = contenu[1:]

    reader = csv.reader(io.StringIO(contenu))
    try:
        entete = next(reader)
    except StopIteration:
        raise ImportError_("Le fichier CSV est vide.")

    entete = [h.strip() for h in entete]
    if entete != COLONNES_ATTENDUES:
        manquantes = [c for c in COLONNES_ATTENDUES if c not in entete]
        surplus = [c for c in entete if c not in COLONNES_ATTENDUES]
        detail = ""
        if manquantes:
            detail += f" Colonnes manquantes : {', '.join(manquantes)}."
        if surplus:
            detail += f" Colonnes inattendues : {', '.join(surplus)}."
        raise ImportError_(
            "L'en-tête du CSV ne correspond pas au schéma attendu "
            f"(19 colonnes dans l'ordre exact).{detail}"
        )

    lignes: list[dict] = []
    for i, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
            continue  # ligne vide
        if len(row) != len(COLONNES_ATTENDUES):
            raise ImportError_(
                f"Ligne {i} : {len(row)} champs au lieu de {len(COLONNES_ATTENDUES)}. "
                "Vérifiez les guillemets autour des champs contenant des virgules."
            )
        brut = dict(zip(COLONNES_ATTENDUES, row))
        url = _clean_str(brut["url_annonce"])
        if not url:
            raise ImportError_(f"Ligne {i} : url_annonce manquante (identifiant obligatoire).")

        prix = _clean_int(brut["prix_affiche"])
        localisation = _clean_str(brut["localisation"])
        notes = _clean_str(brut["notes"])
        drapeaux = detecter_drapeaux(notes, prix, localisation, url)

        lignes.append({
            "url_annonce": url,
            "type_unite": _clean_str(brut["type_unite"]),
            "marque": _clean_str(brut["marque"]),
            "ligne": _clean_str(brut["ligne"]),
            "modele": _clean_str(brut["modele"]),
            "annee": _clean_int(brut["annee"]),
            "prix_affiche": prix,
            "vendeur": _clean_str(brut["vendeur"]),
            "type_vendeur": _clean_str(brut["type_vendeur"]),
            "localisation": localisation,
            "ville": _extraire_ville(localisation),
            "longueur_pi": _clean_float(brut["longueur_pi"]),
            "kilometrage": _clean_int(brut["kilometrage"]),
            "etat_declare": _clean_str(brut["etat_declare"]),
            "extensions": _clean_str(brut["extensions"]),
            "date_collecte": _clean_date(brut["date_collecte"]),
            "date_derniere_observation": _clean_date(brut["date_derniere_observation"]),
            "statut": _clean_str(brut["statut"]),
            "ancien_prix": _clean_int(brut["ancien_prix"]),
            "notes": notes,
            **drapeaux,
        })
    return lignes


# --------------------------------------------------------------------------- #
# Import en base (upsert + diff)
# --------------------------------------------------------------------------- #

async def importer_csv(db: AsyncSession, contenu: str, *,
                       nom_fichier: str = "", user_id: Optional[int] = None,
                       model=Listing, creer_batch: bool = True) -> dict:
    """Importe le CSV : upsert par url_annonce, marque les disparues, détecte les baisses.

    `model` cible la table (Listing = usagés, StockNeuf = neufs). Retourne un résumé ;
    crée un `ImportBatch` seulement si `creer_batch`.
    """
    lignes = parser_csv(contenu)

    # Charger l'état actuel
    result = await db.execute(select(model))
    existantes = {l.url_annonce: l for l in result.scalars().all()}

    urls_importees: set[str] = set()
    nb_creees = 0
    nb_maj = 0
    baisses: list[dict] = []
    maintenant = datetime.utcnow()

    for data in lignes:
        url = data["url_annonce"]
        urls_importees.add(url)
        existante = existantes.get(url)

        if existante is None:
            listing = model(
                premier_import_le=maintenant,
                dernier_import_le=maintenant,
                disparue=False,
                **data,
            )
            db.add(listing)
            nb_creees += 1
        else:
            ancien_prix_actif = existante.prix_affiche
            nouveau_prix = data["prix_affiche"]
            # Détection d'une baisse de prix entre deux imports
            if (ancien_prix_actif is not None and nouveau_prix is not None
                    and nouveau_prix < ancien_prix_actif):
                existante.prix_precedent = ancien_prix_actif
                baisses.append({
                    "url": url,
                    "modele": data.get("modele"),
                    "avant": ancien_prix_actif,
                    "apres": nouveau_prix,
                    "baisse": ancien_prix_actif - nouveau_prix,
                })
            for champ, valeur in data.items():
                setattr(existante, champ, valeur)
            existante.dernier_import_le = maintenant
            existante.disparue = False
            nb_maj += 1

    # Marquer comme disparues les annonces absentes du nouvel import
    nb_disparues = 0
    for url, listing in existantes.items():
        if url not in urls_importees and not listing.disparue:
            listing.disparue = True
            if listing.statut and "disparue" not in _norm(listing.statut):
                listing.statut = "disparue"
            elif not listing.statut:
                listing.statut = "disparue"
            nb_disparues += 1

    if creer_batch:
        db.add(ImportBatch(
            imported_at=maintenant,
            imported_by=user_id,
            nom_fichier=nom_fichier,
            nb_lignes_csv=len(lignes),
            nb_importees=nb_creees + nb_maj,
            nb_creees=nb_creees,
            nb_maj=nb_maj,
            nb_disparues=nb_disparues,
            nb_baisses=len(baisses),
            details={"baisses": baisses[:50]},
        ))
    await db.commit()

    return {
        "nb_lignes_csv": len(lignes),
        "nb_importees": nb_creees + nb_maj,
        "nb_creees": nb_creees,
        "nb_maj": nb_maj,
        "nb_disparues": nb_disparues,
        "nb_baisses": len(baisses),
        "baisses": baisses,
    }
