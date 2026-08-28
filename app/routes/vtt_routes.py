"""Routes d'évaluation de prix de VTT / Côte-à-côte usagés."""
from types import SimpleNamespace
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import require_login, require_admin
from app.models import VttListing, VttImportBatch, VttUserEstimation, VttEvaluationLog
from app.services import comparables_engine as engine
from app.services import vtt_csv_import
from app.services import eval_settings
from app.services import fuzzy_search
from app.templates_env import templates

router = APIRouter()

TYPES_ONGLETS = [
    {"cle": "VTT", "libelle": "VTT", "actif": True},
    {"cle": "Côte-à-côte", "libelle": "Côte-à-côte", "actif": True},
]
TYPES_ACTIFS = {t["cle"] for t in TYPES_ONGLETS if t["actif"]}


def _estimation_en_comparable(e: VttUserEstimation) -> SimpleNamespace:
    return SimpleNamespace(
        type_unite=e.type_unite, marque=e.marque, ligne=None, modele=e.modele,
        annee=e.annee, prix_affiche=e.valeur_estimee, type_vendeur="Utilisateur",
        ville=None, localisation=None, longueur_pi=None, url_annonce=None,
        is_usd=False, is_prix_sur_demande=False, is_volee=False,
        is_projet_bricoleur=False, is_doublon=False, is_notre_annonce=False,
        is_estimation_utilisateur=True,
        auteur=e.auteur, created_at=e.created_at, note=e.note,
    )


async def _run_evaluation(request, user, db, type_unite, marque, modele, annee,
                          message_estimation=None, journaliser=False):
    if type_unite not in TYPES_ACTIFS:
        type_unite = TYPES_ONGLETS[0]["cle"]

    try:
        annee_int = int(str(annee)) if str(annee).strip() else None
    except ValueError:
        annee_int = None

    settings = await eval_settings.get_settings(db)

    result = await db.execute(
        select(VttListing).where(
            VttListing.type_unite == type_unite,
            VttListing.disparue == False,  # noqa: E712
        )
    )
    listings_raw = list(result.scalars().all())

    # Adapter les VttListing pour le moteur générique (qui attend .ligne et .longueur_pi)
    listings = []
    for l in listings_raw:
        ns = SimpleNamespace(**{c.name: getattr(l, c.name) for c in l.__table__.columns})
        ns.ligne = None
        ns.longueur_pi = None
        ns.is_projet_bricoleur = False
        ns.gamme = None
        ns.is_gamme_differente = False
        listings.append(ns)

    est_result = await db.execute(
        select(VttUserEstimation).where(VttUserEstimation.type_unite == type_unite)
    )
    estimations = [_estimation_en_comparable(e) for e in est_result.scalars().all()]

    # Passer longueur_cible=None et tolérance très large → le moteur ne filtre pas sur la longueur
    resultat = engine.evaluer(
        listings + estimations,
        type_unite=type_unite,
        marque=marque.strip() or None,
        ligne=None,
        modele=modele.strip() or None,
        annee=annee_int,
        fenetre_annees=settings.fenetre_annees,
        tolerance_longueur=9999.0,
        inclure_bricoleur=settings.inclure_projets_bricoleur,
    )

    comparables_affichage = []
    for c in resultat["comparables"]:
        niveau = engine._niveau_correspondance(
            c, modele.strip() or None, None,
            None, 9999.0,
        )
        comparables_affichage.append({
            "l": c,
            "niveau": engine.LIBELLE_NIVEAU.get(niveau, "—"),
            "exclusion": engine.raison_exclusion_mediane(c, settings.inclure_projets_bricoleur),
            "est_estimation": getattr(c, "is_estimation_utilisateur", False),
        })

    # « Vouliez-vous dire… ? »
    suggestions_proches = []
    if not comparables_affichage and (marque.strip() or modele.strip()):
        res_all = await db.execute(select(VttListing).where(VttListing.type_unite == type_unite))
        pool = list(res_all.scalars().all())
        q = " ".join(x for x in (marque.strip(), modele.strip()) if x)
        scored = fuzzy_search.scorer(q, pool, limit=5)
        seen = set()
        for _, l in scored:
            key = (l.marque, l.modele)
            if key not in seen:
                seen.add(key)
                label = " ".join(x for x in (l.marque or "", l.modele or "") if x)
                suggestions_proches.append({"label": label, "marque": l.marque or "", "modele": l.modele or ""})

    if journaliser and (modele.strip() or marque.strip()):
        db.add(VttEvaluationLog(
            user_id=user.id, auteur=(user.full_name or user.username),
            type_unite=type_unite, marque=marque.strip() or None,
            modele=modele.strip() or None, annee=annee_int,
            prix_median=resultat["stats"].mediane,
            nb_comparables=resultat["stats"].n,
            created_at=datetime.utcnow(),
        ))
        await db.commit()

    return templates.TemplateResponse("vtt/evaluer.html", {
        "request": request, "user": user,
        "onglets": TYPES_ONGLETS,
        "type_actif": type_unite,
        "form": {"marque": marque, "modele": modele, "annee": annee},
        "resultat": resultat,
        "comparables": comparables_affichage,
        "message_estimation": message_estimation,
        "suggestions_proches": suggestions_proches,
    })


@router.get("/vtt/evaluer", response_class=HTMLResponse)
async def page_vtt_evaluer(request: Request, user=Depends(require_login)):
    return templates.TemplateResponse("vtt/evaluer.html", {
        "request": request, "user": user,
        "onglets": TYPES_ONGLETS,
        "type_actif": TYPES_ONGLETS[0]["cle"],
    })


@router.post("/vtt/evaluer", response_class=HTMLResponse)
async def do_vtt_evaluer(
    request: Request,
    type_unite: str = Form(...),
    marque: str = Form(""),
    modele: str = Form(""),
    annee: str = Form(""),
    user=Depends(require_login),
    db: AsyncSession = Depends(get_db),
):
    return await _run_evaluation(request, user, db, type_unite, marque, modele, annee,
                                 journaliser=True)


@router.post("/vtt/estimation", response_class=HTMLResponse)
async def do_vtt_estimation(
    request: Request,
    type_unite: str = Form(...),
    marque: str = Form(""),
    modele: str = Form(""),
    annee: str = Form(""),
    valeur_estimee: str = Form(...),
    note: str = Form(""),
    user=Depends(require_login),
    db: AsyncSession = Depends(get_db),
):
    if type_unite not in TYPES_ACTIFS:
        type_unite = TYPES_ONGLETS[0]["cle"]

    digits = "".join(ch for ch in valeur_estimee if ch.isdigit())
    valeur = int(digits) if digits else 0

    message = None
    if valeur > 0:
        try:
            annee_int = int(annee) if annee.strip() else None
        except ValueError:
            annee_int = None
        db.add(VttUserEstimation(
            type_unite=type_unite,
            marque=marque.strip() or None,
            modele=modele.strip() or None,
            annee=annee_int,
            valeur_estimee=valeur,
            note=note.strip() or None,
            user_id=user.id,
            auteur=(user.full_name or user.username),
            created_at=datetime.utcnow(),
        ))
        await db.commit()
        message = f"Estimation de {valeur:,} $".replace(",", " ") + \
            " enregistrée et ajoutée aux propositions."
    else:
        message = "Montant invalide — l'estimation n'a pas été enregistrée."

    return await _run_evaluation(request, user, db, type_unite, marque, modele, annee,
                                 message_estimation=message)


@router.get("/vtt/historique", response_class=HTMLResponse)
async def historique_vtt(request: Request, user=Depends(require_login),
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(VttEvaluationLog).order_by(VttEvaluationLog.created_at.desc()).limit(200)
    )
    logs = result.scalars().all()
    return templates.TemplateResponse("vtt/historique.html", {
        "request": request, "user": user, "logs": logs,
    })


@router.get("/vtt/importer", response_class=HTMLResponse)
async def page_vtt_importer(request: Request, user=Depends(require_admin),
                            db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(VttImportBatch).order_by(VttImportBatch.imported_at.desc()).limit(5)
    )
    historique = result.scalars().all()
    total = await db.execute(select(VttListing))
    nb_total = len(total.scalars().all())
    return templates.TemplateResponse("vtt/importer.html", {
        "request": request, "user": user,
        "historique": historique, "nb_total": nb_total,
    })


@router.post("/vtt/importer", response_class=HTMLResponse)
async def do_vtt_importer(request: Request, fichier: UploadFile = File(...),
                          user=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    erreur, resume = None, None
    try:
        contenu = (await fichier.read()).decode("utf-8-sig")
        resume = await vtt_csv_import.importer_csv(
            db, contenu, nom_fichier=fichier.filename or "", user_id=user.id,
        )
    except vtt_csv_import.ImportError_ as e:
        erreur = str(e)
    except UnicodeDecodeError:
        erreur = "Le fichier n'est pas encodé en UTF-8. Ré-enregistrez-le en UTF-8."
    except Exception as e:
        erreur = f"Erreur inattendue pendant l'import : {e}"

    result = await db.execute(
        select(VttImportBatch).order_by(VttImportBatch.imported_at.desc()).limit(5)
    )
    historique = result.scalars().all()
    total = await db.execute(select(VttListing))
    nb_total = len(total.scalars().all())
    return templates.TemplateResponse("vtt/importer.html", {
        "request": request, "user": user,
        "resume": resume, "erreur": erreur,
        "historique": historique, "nb_total": nb_total,
    })
