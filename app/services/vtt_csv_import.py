"""Import CSV pour les annonces VTT / Côte-à-côte usagés."""
import csv, io, re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import VttListing, VttImportBatch


class ImportError_(Exception):
    pass


COLONNES_REQUISES = {"url_annonce"}

TYPES_VALIDES = {"VTT", "Côte-à-côte", "Cote-a-cote", "Side-by-side", "SxS"}


def _normaliser_type(v: str) -> str:
    v = v.strip()
    if re.search(r"cote|side|sxs|sbs|ssv", v, re.I):
        return "Côte-à-côte"
    return "VTT"


def _int_ou_none(v: str):
    d = re.sub(r"[^\d]", "", v or "")
    return int(d) if d else None


def _bool_champ(v: str) -> bool:
    return (v or "").strip().lower() in ("1", "true", "oui", "yes", "x")


async def importer_csv(db: AsyncSession, contenu: str,
                       nom_fichier: str = "", user_id=None) -> dict:
    reader = csv.DictReader(io.StringIO(contenu))
    colonnes = set(reader.fieldnames or [])
    manquantes = COLONNES_REQUISES - colonnes
    if manquantes:
        raise ImportError_(f"Colonnes manquantes dans le CSV : {', '.join(sorted(manquantes))}")

    lignes = list(reader)
    nb_creees = nb_maj = 0

    for row in lignes:
        url = (row.get("url_annonce") or "").strip()
        if not url:
            continue

        # Vérifier si l'annonce existe déjà
        res = await db.execute(select(VttListing).where(VttListing.url_annonce == url))
        existant = res.scalar_one_or_none()

        type_v = _normaliser_type(row.get("type_unite") or "VTT")
        prix = _int_ou_none(row.get("prix_affiche") or row.get("prix") or "")
        cylindree = _int_ou_none(row.get("cylindree_cc") or row.get("cylindree") or "")
        km = _int_ou_none(row.get("kilometrage") or row.get("km") or "")
        try:
            date_c = datetime.strptime(row.get("date_collecte", ""), "%Y-%m-%d").date() if row.get("date_collecte") else None
        except ValueError:
            date_c = None

        champs = dict(
            type_unite=type_v,
            marque=(row.get("marque") or "").strip() or None,
            modele=(row.get("modele") or "").strip() or None,
            annee=_int_ou_none(row.get("annee") or ""),
            cylindree_cc=cylindree,
            prix_affiche=prix,
            kilometrage=km,
            vendeur=(row.get("vendeur") or "").strip() or None,
            type_vendeur=(row.get("type_vendeur") or "").strip() or None,
            localisation=(row.get("localisation") or "").strip() or None,
            ville=(row.get("ville") or "").strip() or None,
            etat_declare=(row.get("etat") or row.get("etat_declare") or "").strip() or None,
            statut=(row.get("statut") or "").strip() or None,
            notes=(row.get("notes") or "").strip() or None,
            date_collecte=date_c,
            is_usd=_bool_champ(row.get("is_usd") or ""),
            is_prix_sur_demande=_bool_champ(row.get("is_prix_sur_demande") or ""),
            is_volee=_bool_champ(row.get("is_volee") or ""),
            is_notre_annonce=_bool_champ(row.get("is_notre_annonce") or ""),
            is_doublon=_bool_champ(row.get("is_doublon") or ""),
            disparue=_bool_champ(row.get("disparue") or ""),
        )

        if existant:
            if existant.prix_affiche != prix and prix is not None:
                existant.prix_precedent = existant.prix_affiche
            for k, v in champs.items():
                setattr(existant, k, v)
            existant.dernier_import_le = datetime.utcnow()
            nb_maj += 1
        else:
            db.add(VttListing(url_annonce=url, **champs,
                              premier_import_le=datetime.utcnow(),
                              dernier_import_le=datetime.utcnow()))
            nb_creees += 1

    batch = VttImportBatch(
        imported_by=user_id,
        nom_fichier=nom_fichier,
        nb_lignes_csv=len(lignes),
        nb_importees=nb_creees + nb_maj,
        nb_creees=nb_creees,
        nb_maj=nb_maj,
        imported_at=datetime.utcnow(),
    )
    db.add(batch)
    await db.commit()

    return {
        "nb_lignes_csv": len(lignes),
        "nb_creees": nb_creees,
        "nb_maj": nb_maj,
        "nb_importees": nb_creees + nb_maj,
    }
