"""Routes d'évaluation de prix de VR usagés : Évaluer, Importer, Réglages."""
from types import SimpleNamespace
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import require_login, require_admin
from app.models import Listing, ImportBatch, UserEstimation, GammeModele, EvaluationLog, StockNeuf
from app.services import comparables_engine as engine
from app.services import csv_import
from app.services import eval_settings
from app.services import gamme_classifier
from app.services import fuzzy_search
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


def _estimation_en_comparable(e: UserEstimation) -> SimpleNamespace:
    """Convertit une estimation utilisateur en objet « comparable » pour le moteur."""
    return SimpleNamespace(
        type_unite=e.type_unite, marque=e.marque, ligne=e.ligne, modele=e.modele,
        annee=e.annee, prix_affiche=e.valeur_estimee, type_vendeur="Utilisateur",
        ville=None, localisation=None, longueur_pi=e.longueur_pi, url_annonce=None,
        is_usd=False, is_prix_sur_demande=False, is_volee=False,
        is_projet_bricoleur=False, is_doublon=False, is_notre_annonce=False,
        is_estimation_utilisateur=True,
        auteur=e.auteur, created_at=e.created_at, note=e.note,
    )


async def _run_evaluation(request, user, db, type_unite, marque, ligne, modele, annee,
                          message_estimation=None, journaliser=False):
    """Exécute une évaluation et renvoie la page de résultats (partagée)."""
    if type_unite not in TYPES_ACTIFS:
        type_unite = TYPES_ONGLETS[0]["cle"]

    try:
        annee_int = int(str(annee)) if str(annee).strip() else None
    except ValueError:
        annee_int = None

    settings = await eval_settings.get_settings(db)

    # Annonces réelles actives + estimations utilisateur (du même type d'unité)
    result = await db.execute(
        select(Listing).where(
            Listing.type_unite == type_unite,
            Listing.disparue == False,  # noqa: E712
        )
    )
    listings = list(result.scalars().all())

    est_result = await db.execute(
        select(UserEstimation).where(UserEstimation.type_unite == type_unite)
    )
    estimations = [_estimation_en_comparable(e) for e in est_result.scalars().all()]

    # Gammes de qualité : celle de la cible + celle de chaque annonce
    gammes_map = await gamme_classifier.charger_map(db)

    def _gamme_de(marque_v, ligne_v):
        g = gammes_map.get(gamme_classifier.cle(marque_v, ligne_v))
        return g.gamme if g else None

    gamme_cible = _gamme_de(marque, ligne)
    for l in listings:
        l.gamme = _gamme_de(l.marque, l.ligne)
        l.is_gamme_differente = bool(l.gamme and gamme_cible and l.gamme != gamme_cible)
    for e in estimations:
        # Une estimation porte sur le véhicule évalué -> même gamme que la cible
        e.gamme = gamme_cible
        e.is_gamme_differente = False

    resultat = engine.evaluer(
        listings + estimations,
        type_unite=type_unite,
        marque=marque.strip() or None,
        ligne=ligne.strip() or None,
        modele=modele.strip() or None,
        annee=annee_int,
        fenetre_annees=settings.fenetre_annees,
        tolerance_longueur=settings.tolerance_longueur_pi,
        inclure_bricoleur=settings.inclure_projets_bricoleur,
    )

    comparables_affichage = []
    for c in resultat["comparables"]:
        niveau = engine._niveau_correspondance(
            c, modele.strip() or None, ligne.strip() or None,
            resultat.get("longueur_cible"), settings.tolerance_longueur_pi,
        )
        comparables_affichage.append({
            "l": c,
            "niveau": engine.LIBELLE_NIVEAU.get(niveau, "—"),
            "exclusion": engine.raison_exclusion_mediane(c, settings.inclure_projets_bricoleur),
            "est_estimation": getattr(c, "is_estimation_utilisateur", False),
            "gamme": getattr(c, "gamme", None),
        })

    # « Vouliez-vous dire… ? » : aucun comparable mais des modèles proches existent
    suggestions_proches = []
    if not comparables_affichage and (marque.strip() or ligne.strip() or modele.strip()):
        suggestions_proches = await fuzzy_search.matches_proches(
            db, type_unite=type_unite, marque=marque, ligne=ligne, modele=modele,
        )

    # Journaliser l'évaluation (historique persistant), si demandé et véhicule renseigné
    if journaliser and (modele.strip() or ligne.strip()):
        db.add(EvaluationLog(
            user_id=user.id, auteur=(user.full_name or user.username),
            type_unite=type_unite, marque=marque.strip() or None,
            ligne=ligne.strip() or None, modele=modele.strip() or None,
            annee=annee_int, gamme=gamme_cible,
            prix_median=resultat["stats"].mediane,
            nb_comparables=resultat["stats"].n,
            created_at=datetime.utcnow(),
        ))
        await db.commit()

    return templates.TemplateResponse("evaluation/evaluer.html", {
        "request": request, "user": user,
        "onglets": TYPES_ONGLETS,
        "type_actif": type_unite,
        "form": {"marque": marque, "ligne": ligne, "modele": modele, "annee": annee},
        "resultat": resultat,
        "comparables": comparables_affichage,
        "longueur_cible": resultat.get("longueur_cible"),
        "gamme_cible": gamme_cible,
        "message_estimation": message_estimation,
        "suggestions_proches": suggestions_proches,
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
    return await _run_evaluation(request, user, db, type_unite, marque, ligne, modele, annee,
                                 journaliser=True)


@router.get("/api/evaluation/suggestions")
async def api_suggestions(
    q: str = "", champ: str = "", type_unite: str = "", source: str = "",
    user=Depends(require_login), db: AsyncSession = Depends(get_db),
):
    """Autocomplétion floue : renvoie les modèles proches de `q` (JSON).

    `source=neuf` cherche dans le stock neuf (mise en vente) ; sinon dans les usagés.
    """
    if len(q.strip()) < 2:
        return {"suggestions": []}
    champ_v = champ if champ in ("marque", "ligne", "modele") else None
    tu = type_unite if type_unite in TYPES_ACTIFS else None
    model = StockNeuf if source == "neuf" else Listing
    sugg = await fuzzy_search.suggestions(db, q, champ=champ_v, type_unite=tu, limit=8, model=model)
    return {"suggestions": sugg}


@router.post("/evaluer/estimation", response_class=HTMLResponse)
async def do_estimation(
    request: Request,
    type_unite: str = Form(...),
    marque: str = Form(""),
    ligne: str = Form(""),
    modele: str = Form(""),
    annee: str = Form(""),
    valeur_estimee: str = Form(...),
    longueur_cible: str = Form(""),
    note: str = Form(""),
    user=Depends(require_login),
    db: AsyncSession = Depends(get_db),
):
    if type_unite not in TYPES_ACTIFS:
        type_unite = TYPES_ONGLETS[0]["cle"]

    # Nettoyer le montant saisi (retirer $, espaces, séparateurs)
    digits = "".join(ch for ch in valeur_estimee if ch.isdigit())
    valeur = int(digits) if digits else 0

    message = None
    if valeur > 0:
        try:
            annee_int = int(annee) if annee.strip() else None
        except ValueError:
            annee_int = None
        try:
            lg = float(longueur_cible) if longueur_cible.strip() else None
        except ValueError:
            lg = None
        db.add(UserEstimation(
            type_unite=type_unite,
            marque=marque.strip() or None,
            ligne=ligne.strip() or None,
            modele=modele.strip() or None,
            annee=annee_int,
            longueur_pi=lg,
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

    return await _run_evaluation(request, user, db, type_unite, marque, ligne, modele, annee,
                                 message_estimation=message)


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


# --------------------------------------------------------------------------- #
# Gammes de qualité (admin)
# --------------------------------------------------------------------------- #

async def _page_gammes(request, user, db, message=None):
    lignes = await gamme_classifier.lignes_distinctes(db)
    gammes_map = await gamme_classifier.charger_map(db)
    rows = []
    for d in lignes:
        g = gammes_map.get(gamme_classifier.cle(d["marque"], d["ligne"]))
        rows.append({"info": d, "gamme": g})
    nb_classees = sum(1 for r in rows if r["gamme"] and r["gamme"].gamme)
    return templates.TemplateResponse("evaluation/gammes.html", {
        "request": request, "user": user,
        "rows": rows, "gammes": gamme_classifier.GAMMES,
        "nb_total": len(rows), "nb_classees": nb_classees,
        "message": message, "demo": gamme_classifier.DEMO_MODE,
    })


@router.get("/evaluer/gammes", response_class=HTMLResponse)
async def page_gammes(request: Request, user=Depends(require_admin),
                      db: AsyncSession = Depends(get_db)):
    return await _page_gammes(request, user, db)


@router.post("/evaluer/gammes/classer", response_class=HTMLResponse)
async def classer_gammes(request: Request, user=Depends(require_admin),
                         db: AsyncSession = Depends(get_db)):
    try:
        res = await gamme_classifier.classer_manquantes(db)
        message = f"{res['classees']} ligne(s) classée(s) automatiquement."
    except Exception as e:  # robustesse : ne jamais planter la page
        message = f"Erreur pendant la classification : {e}"
    return await _page_gammes(request, user, db, message=message)


@router.post("/evaluer/gammes/save", response_class=HTMLResponse)
async def save_gamme(
    request: Request,
    type_unite: str = Form(""),
    marque: str = Form(...),
    ligne: str = Form(""),
    gamme: str = Form(""),
    murs: str = Form(""),
    substrat: str = Form(""),
    plancher: str = Form(""),
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    data = {
        "gamme": gamme.strip() or None,
        "murs": murs.strip() or None,
        "substrat": substrat.strip() or None,
        "plancher": plancher.strip() or None,
        "justification": "Classée à la main.",
    }
    await gamme_classifier.upsert(db, type_unite or None, marque, ligne or None,
                                  data, is_manuel=True)
    return await _page_gammes(request, user, db, message="Gamme enregistrée.")


# --------------------------------------------------------------------------- #
# Historique des évaluations (tous les utilisateurs connectés)
# --------------------------------------------------------------------------- #

@router.get("/evaluer/historique", response_class=HTMLResponse)
async def historique_evaluations(request: Request, user=Depends(require_login),
                                 db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EvaluationLog).order_by(EvaluationLog.created_at.desc()).limit(200)
    )
    logs = result.scalars().all()
    return templates.TemplateResponse("evaluation/historique.html", {
        "request": request, "user": user, "logs": logs,
    })


# --------------------------------------------------------------------------- #
# Outil de mise en vente (tous les utilisateurs connectés)
# --------------------------------------------------------------------------- #

def _est_competiteur(l) -> bool:
    """Vendeur professionnel concurrent (pas nous, pas un particulier)."""
    if getattr(l, "is_notre_annonce", False):
        return False
    tv = fuzzy_search.normaliser(l.type_vendeur)
    return ("concession" in tv) or ("commer" in tv) or ("courtier" in tv)


@router.get("/mise-en-vente", response_class=HTMLResponse)
async def page_mise_en_vente(request: Request, user=Depends(require_login)):
    return templates.TemplateResponse("evaluation/mise_en_vente.html", {
        "request": request, "user": user,
        "onglets": TYPES_ONGLETS, "type_actif": TYPES_ONGLETS[0]["cle"],
    })


@router.post("/mise-en-vente", response_class=HTMLResponse)
async def do_mise_en_vente(
    request: Request,
    type_unite: str = Form(...),
    marque: str = Form(""),
    ligne: str = Form(""),
    modele: str = Form(""),
    user=Depends(require_login),
    db: AsyncSession = Depends(get_db),
):
    if type_unite not in TYPES_ACTIFS:
        type_unite = TYPES_ONGLETS[0]["cle"]

    # Stock NEUF compétiteur actif du bon type (jeu de données distinct des usagés)
    result = await db.execute(
        select(StockNeuf).where(
            StockNeuf.type_unite == type_unite,
            StockNeuf.disparue == False,  # noqa: E712
        )
    )
    pros = [l for l in result.scalars().all() if _est_competiteur(l)]

    # Matching flou du modèle recherché sur le stock compétiteur
    q = " ".join(x for x in (marque.strip(), ligne.strip(), modele.strip()) if x)
    scored = fuzzy_search.scorer(q, pros, limit=50) if q else []

    now = datetime.utcnow()
    resultats = []
    for score, l in scored:
        # « En vente depuis » = semaines depuis premier_import_le (1re détection dans vos imports)
        semaines = None
        if l.premier_import_le:
            semaines = max(0, (now - l.premier_import_le).days // 7)
        resultats.append({"l": l, "score": score, "semaines": semaines})

    suggestions_proches = []
    if not resultats and (marque.strip() or ligne.strip() or modele.strip()):
        suggestions_proches = await fuzzy_search.matches_proches(
            db, type_unite=type_unite, marque=marque, ligne=ligne, modele=modele,
            model=StockNeuf,
        )

    return templates.TemplateResponse("evaluation/mise_en_vente.html", {
        "request": request, "user": user,
        "onglets": TYPES_ONGLETS, "type_actif": type_unite,
        "form": {"marque": marque, "ligne": ligne, "modele": modele},
        "resultats": resultats, "recherche_faite": True,
        "suggestions_proches": suggestions_proches,
    })


# --- Import du stock NEUF (admin) : jeu de données séparé pour la mise en vente ---

_CTX_IMPORT_NEUF = {
    "import_action": "/mise-en-vente/importer",
    "import_titre": "Importer le stock neuf",
    "import_sous_titre": "Glissez le CSV du stock NEUF des compétiteurs (utilisé par l'outil de mise en vente).",
}


@router.get("/mise-en-vente/importer", response_class=HTMLResponse)
async def page_importer_neuf(request: Request, user=Depends(require_admin),
                             db: AsyncSession = Depends(get_db)):
    total = await db.execute(select(StockNeuf))
    nb_total = len(total.scalars().all())
    return templates.TemplateResponse("evaluation/importer.html", {
        "request": request, "user": user, "nb_total": nb_total, "historique": None,
        **_CTX_IMPORT_NEUF,
    })


@router.post("/mise-en-vente/importer", response_class=HTMLResponse)
async def do_importer_neuf(request: Request, fichier: UploadFile = File(...),
                           user=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    erreur, resume = None, None
    try:
        contenu = (await fichier.read()).decode("utf-8-sig")
        resume = await csv_import.importer_csv(
            db, contenu, nom_fichier=fichier.filename or "", user_id=user.id,
            model=StockNeuf, creer_batch=False,
        )
    except csv_import.ImportError_ as e:
        erreur = str(e)
    except UnicodeDecodeError:
        erreur = "Le fichier n'est pas encodé en UTF-8. Ré-enregistrez-le en UTF-8."
    except Exception as e:
        erreur = f"Erreur inattendue pendant l'import : {e}"

    total = await db.execute(select(StockNeuf))
    nb_total = len(total.scalars().all())
    return templates.TemplateResponse("evaluation/importer.html", {
        "request": request, "user": user, "resume": resume, "erreur": erreur,
        "nb_total": nb_total, "historique": None,
        **_CTX_IMPORT_NEUF,
    })
