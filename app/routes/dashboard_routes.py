from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from app.database import get_db
from app.auth import require_login
from app.models import Listing, VttListing, EvaluationLog, VttEvaluationLog, ImportBatch, VttImportBatch

router = APIRouter()
from app.templates_env import templates


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user=Depends(require_login), db: AsyncSession = Depends(get_db)):
    depuis = datetime.utcnow() - timedelta(days=30)

    # Annonces actives en base
    nb_roulo = (await db.execute(
        select(func.count()).select_from(Listing).where(Listing.disparue == False)
    )).scalar() or 0
    nb_vtt = (await db.execute(
        select(func.count()).select_from(VttListing).where(VttListing.disparue == False)
    )).scalar() or 0

    # Évaluations des 30 derniers jours
    eval_roulo = (await db.execute(
        select(func.count()).select_from(EvaluationLog).where(EvaluationLog.created_at >= depuis)
    )).scalar() or 0
    eval_vtt = (await db.execute(
        select(func.count()).select_from(VttEvaluationLog).where(VttEvaluationLog.created_at >= depuis)
    )).scalar() or 0

    # Prix médian moyen des évaluations VR du dernier mois
    prix_median_roulo = (await db.execute(
        select(func.avg(EvaluationLog.prix_median)).where(
            EvaluationLog.created_at >= depuis,
            EvaluationLog.prix_median.isnot(None)
        )
    )).scalar()

    prix_median_vtt = (await db.execute(
        select(func.avg(VttEvaluationLog.prix_median)).where(
            VttEvaluationLog.created_at >= depuis,
            VttEvaluationLog.prix_median.isnot(None)
        )
    )).scalar()

    # Dernier import
    dernier_import_roulo = (await db.execute(
        select(ImportBatch.imported_at).order_by(ImportBatch.imported_at.desc()).limit(1)
    )).scalar()
    dernier_import_vtt = (await db.execute(
        select(VttImportBatch.imported_at).order_by(VttImportBatch.imported_at.desc()).limit(1)
    )).scalar()

    # Évaluations récentes (toutes catégories confondues)
    recentes_roulo = (await db.execute(
        select(EvaluationLog).where(EvaluationLog.created_at >= depuis)
        .order_by(EvaluationLog.created_at.desc()).limit(5)
    )).scalars().all()
    recentes_vtt = (await db.execute(
        select(VttEvaluationLog).where(VttEvaluationLog.created_at >= depuis)
        .order_by(VttEvaluationLog.created_at.desc()).limit(5)
    )).scalars().all()

    # Fusionner et trier par date desc
    recentes = sorted(
        [{"cat": "VR", "obj": r} for r in recentes_roulo] +
        [{"cat": "VTT", "obj": r} for r in recentes_vtt],
        key=lambda x: x["obj"].created_at,
        reverse=True
    )[:8]

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "nb_roulo": nb_roulo,
        "nb_vtt": nb_vtt,
        "eval_roulo": eval_roulo,
        "eval_vtt": eval_vtt,
        "prix_median_roulo": int(prix_median_roulo) if prix_median_roulo else None,
        "prix_median_vtt": int(prix_median_vtt) if prix_median_vtt else None,
        "dernier_import_roulo": dernier_import_roulo,
        "dernier_import_vtt": dernier_import_vtt,
        "recentes": recentes,
        "depuis": depuis,
    })
