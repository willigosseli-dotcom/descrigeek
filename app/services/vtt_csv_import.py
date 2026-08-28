"""Import CSV pour les annonces VTT / Côte-à-côte / Motoneige usagés."""
import csv, io, re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import VttListing, VttImportBatch


class ImportError_(Exception):
    pass


COLONNES_REQUISES = {"url_annonce"}


def _int_ou_none(v: str):
    d = re.sub(r"[^\d]", "", v or "")
    return int(d) if d else None


def _bool_champ(v: str) -> bool:
    return (v or "").strip().lower() in ("1", "true", "oui", "yes", "x")


def _date_ou_none(v: str):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime((v or "").strip(), fmt).date()
        except ValueError:
            continue
    return None


def _ville_depuis_localisation(loc: str) -> str | None:
    """Extrait la ville depuis 'Ville, Province' ou retourne None."""
    if not loc:
        return None
    return loc.split(",")[0].strip() or None


async def importer_csv(db: AsyncSession, contenu: str,
                       nom_fichier: str = "", user_id=None) -> dict:
    reader = csv.DictReader(io.StringIO(contenu))
    colonnes = set(reader.fieldnames or [])
    manquantes = COLONNES_REQUISES - colonnes
    if manquantes:
        raise ImportError_(f"Colonne manquante dans le CSV : {', '.join(sorted(manquantes))}")

    lignes = list(reader)
    nb_creees = nb_maj = 0

    for row in lignes:
        url = (row.get("url_annonce") or "").strip()
        if not url:
            continue

        res = await db.execute(select(VttListing).where(VttListing.url_annonce == url))
        existant = res.scalar_one_or_none()

        # Colonnes du CSV — supporte "cylindree" ET "cylindree_cc"
        cylindree = _int_ou_none(row.get("cylindree") or row.get("cylindree_cc") or "")
        prix = _int_ou_none(row.get("prix_affiche") or row.get("prix") or "")
        km = _int_ou_none(row.get("kilometrage") or row.get("km") or "")
        heures = _int_ou_none(row.get("heures") or "")
        loc = (row.get("localisation") or "").strip() or None
        ville = (row.get("ville") or _ville_depuis_localisation(loc) or "")

        # ancien_prix / prix_precedent
        ancien = _int_ou_none(row.get("ancien_prix") or row.get("prix_precedent") or "")

        champs = dict(
            type_unite=(row.get("type_unite") or "VTT").strip(),
            marque=(row.get("marque") or "").strip() or None,
            gamme=(row.get("gamme") or "").strip() or None,
            modele=(row.get("modele") or "").strip() or None,
            annee=_int_ou_none(row.get("annee") or ""),
            cylindree_cc=cylindree,
            prix_affiche=prix,
            kilometrage=km,
            heures=heures,
            vendeur=(row.get("vendeur") or "").strip() or None,
            type_vendeur=(row.get("type_vendeur") or "").strip() or None,
            localisation=loc,
            ville=ville or None,
            etat_declare=(row.get("etat_declare") or row.get("etat") or "").strip() or None,
            statut=(row.get("statut") or "").strip() or None,
            notes=(row.get("notes") or "").strip() or None,
            date_collecte=_date_ou_none(row.get("date_collecte") or ""),
            date_derniere_observation=_date_ou_none(row.get("date_derniere_observation") or ""),
            is_usd=_bool_champ(row.get("is_usd") or ""),
            is_prix_sur_demande=_bool_champ(row.get("is_prix_sur_demande") or ""),
            is_volee=_bool_champ(row.get("is_volee") or ""),
            is_notre_annonce=_bool_champ(row.get("is_notre_annonce") or ""),
            is_doublon=_bool_champ(row.get("is_doublon") or ""),
            disparue=_bool_champ(row.get("disparue") or ""),
            prix_precedent=ancien,
        )

        if existant:
            # Conserver l'ancien prix si le prix change
            if prix is not None and existant.prix_affiche != prix and ancien is None:
                champs["prix_precedent"] = existant.prix_affiche
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
