"""Routes d'évaluation de prix de VR usagés : Évaluer, Importer, Réglages."""
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import require_login, require_admin
from app.models import Listing, ImportBatch
from app.services import comparables_engine as engine
from app.services import csv_import
from app.services import eval_settings
from app.templates_env import templates

router = APIRouter()


# Onglets de type d'unité. `actif=False` → visible mais grisé (fonctionnalité future).
TYPES_ONGLETS = [
    {"cle": "Roulotte", "libelle": "Roulotte", "actif": True},
    {"cle": "Fifth wheel", "libelle": "Fifth wheel", "actif": True},
    {"cle": "Tente-roulotte", "libelle": "Tente-roulotte", "actif": True},
    {"cle": "VTT", "libelle": "VTT", "actif": False},
    {"cle": "Côte à côte", "libelle": "Côte à côte", "actif": False},
]
TYPES_ACTIFS = {t["cle"] for t in TYPES_ONGLETS if t["actif"]}


@router.get("/evaluer", response_class=HTMLResponse)
async def page_evaluer(request: Request, user=Depends(require_login)):
    return templates.TemplateResponse("evaluation/evaluer.html", {
        "request": request, "user": user,
        "onglets": TYPES_ONGLETS,
        "type_actif": TYPES_ONGLETS[0]["cle"],
    })


@router.post("/evaluer", response_class=HTMLResponse)
async def do_evaluer(
    request: Request,
    type_unite: str = Form(...),
    marque: str = Form(""),
    ligne: str = Form(""),
    modele: str = Form(""),
    annee: str = Form(""),
    user=Depends(require_login),
    db: AsyncSession = Depends(get_db),
):
    # Sécurité : ignorer un type inactif (VTT / Côte à côte) s'il est forcé
    if type_unite not in TYPES_ACTIFS:
        type_unite = TYPES_ONGLETS[0]["cle"]

    try:
        annee_int = int(annee) if annee.strip() else None
    except ValueError:
        annee_int = None

    settings = await eval_settings.get_settings(db)

    # Charger les annonces actives du bon type d'unité
    result = await db.execute(
        select(Listing).where(
            Listing.type_unite == type_unite,
            Listing.disparue == False,  # noqa: E712
        )
    )
    listings = result.scalars().all()

    resultat = engine.evaluer(
        listings,
        type_unite=type_unite,
        marque=marque.strip() or None,
        ligne=ligne.strip() or None,
        modele=modele.strip() or None,
        annee=annee_int,
        fenetre_annees=settings.fenetre_annees,
        tolerance_longueur=settings.tolerance_longueur_pi,
        inclure_bricoleur=settings.inclure_projets_bricoleur,
    )

    # Étiqueter chaque comparable : niveau de correspondance + raison d'exclusion éventuelle
    comparables_affichage = []
    for c in resultat["comparables"]:
        niveau = engine._niveau_correspondance(
            c, modele.strip() or None, ligne.strip() or None,
            None, settings.tolerance_longueur_pi,
        )
        comparables_affichage.append({
            "l": c,
            "niveau": engine.LIBELLE_NIVEAU.get(niveau, "—"),
            "exclusion": engine.raison_exclusion_mediane(c, settings.inclure_projets_bricoleur),
        })

    return templates.TemplateResponse("evaluation/evaluer.html", {
        "request": request, "user": user,
        "onglets": TYPES_ONGLETS,
        "type_actif": type_unite,
        "form": {"marque": marque, "ligne": ligne, "modele": modele, "annee": annee},
        "resultat": resultat,
        "comparables": comparables_affichage,
    })


# --------------------------------------------------------------------------- #
# Importer (admin)
# --------------------------------------------------------------------------- #

@router.get("/importer", response_class=HTMLResponse)
async def page_importer(request: Request, user=Depends(require_admin),
                        db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ImportBatch).order_by(ImportBatch.imported_at.desc()).limit(5)
    )
    historique = result.scalars().all()
    total = await db.execute(select(Listing))
    nb_total = len(total.scalars().all())
    return templates.TemplateResponse("evaluation/importer.html", {
        "request": request, "user": user,
        "historique": historique, "nb_total": nb_total,
    })


@router.post("/importer", response_class=HTMLResponse)
async def do_importer(request: Request, fichier: UploadFile = File(...),
                      user=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    erreur = None
    resume = None
    try:
        contenu_bytes = await fichier.read()
        contenu = contenu_bytes.decode("utf-8-sig")
        resume = await csv_import.importer_csv(
            db, contenu, nom_fichier=fichier.filename or "", user_id=user.id,
        )
    except csv_import.ImportError_ as e:
        erreur = str(e)
    except UnicodeDecodeError:
        erreur = "Le fichier n'est pas encodé en UTF-8. Ré-enregistrez-le en UTF-8."
    except Exception as e:  # robustesse : ne jamais planter la page
        erreur = f"Erreur inattendue pendant l'import : {e}"

    result = await db.execute(
        select(ImportBatch).order_by(ImportBatch.imported_at.desc()).limit(5)
    )
    historique = result.scalars().all()
    total = await db.execute(select(Listing))
    nb_total = len(total.scalars().all())

    return templates.TemplateResponse("evaluation/importer.html", {
        "request": request, "user": user,
        "resume": resume, "erreur": erreur,
        "historique": historique, "nb_total": nb_total,
    })


# --------------------------------------------------------------------------- #
# Réglages du moteur (admin)
# --------------------------------------------------------------------------- #

@router.get("/evaluer/reglages", response_class=HTMLResponse)
async def page_reglages(request: Request, user=Depends(require_admin),
                        db: AsyncSession = Depends(get_db)):
    settings = await eval_settings.get_settings(db)
    return templates.TemplateResponse("evaluation/reglages.html", {
        "request": request, "user": user, "settings": settings,
    })


@router.post("/evaluer/reglages", response_class=HTMLResponse)
async def do_reglages(
    request: Request,
    fenetre_annees: int = Form(2),
    inclure_projets_bricoleur: bool = Form(False),
    decote_bricoleur_pct: int = Form(40),
    ponderation_particulier_pct: int = Form(15),
    tolerance_longueur_pi: float = Form(2.0),
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    settings = await eval_settings.save_settings(
        db,
        fenetre_annees=fenetre_annees,
        inclure_projets_bricoleur=inclure_projets_bricoleur,
        decote_bricoleur_pct=decote_bricoleur_pct,
        ponderation_particulier_pct=ponderation_particulier_pct,
        tolerance_longueur_pi=tolerance_longueur_pi,
    )
    return templates.TemplateResponse("evaluation/reglages.html", {
        "request": request, "user": user, "settings": settings,
        "enregistre": True,
    })
