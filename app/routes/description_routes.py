from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from app.database import get_db
from app.auth import require_login
from app.models import Description, User, DescriptionExample, SpecsCache
from app.services.file_reader import find_vehicle_in_files
from app.services.web_search import search_vehicle_specs
from app.services.spec_cache import get_cached_specs, save_specs_to_cache
from app.services.ai_generator import generate_description
from app.services.terminology_helper import normalize_user_input
from datetime import datetime

router = APIRouter()
from app.templates_env import templates

VEHICLE_TYPES = [
    "Roulotte", "Fifth wheel", "Motorisé", "VTT",
    "Côte-à-côte", "Motoneige", "Cart de golf",
]


@router.get("/generate", response_class=HTMLResponse)
async def generate_page(request: Request, user=Depends(require_login)):
    return templates.TemplateResponse("generate.html", {
        "request": request, "user": user,
        "vehicle_types": VEHICLE_TYPES,
    })


@router.post("/generate")
async def do_generate(
    request: Request,
    stock_number: str = Form(...),
    vehicle_year: int = Form(...),
    vehicle_make: str = Form(...),
    vehicle_model: str = Form(...),
    vehicle_type: str = Form(""),
    options_accessories: str = Form(""),
    unique_features: str = Form(""),
    force_web_search: bool = Form(False),
    user=Depends(require_login),
    db: AsyncSession = Depends(get_db),
):
    specs_data = {}
    specs_source = ""
    specs_source_type = "none"
    from_cache = False

    # 1. Chercher dans les fichiers internes
    file_result = find_vehicle_in_files(vehicle_year, vehicle_make, vehicle_model)
    if file_result:
        specs_data = file_result
        specs_source = f"Fichier interne : {file_result.get('source_file', 'inconnu')}"
        specs_source_type = file_result.get("source_type", "file")

    # 2. Chercher dans le cache web
    if not specs_data or force_web_search:
        cached = await get_cached_specs(db, vehicle_year, vehicle_make, vehicle_model)
        if cached and not force_web_search:
            specs_data = cached.specs_data
            cached_date = cached.cached_at.strftime("%d %b %Y")
            specs_source = f"Cache ({cached_date}) — Source originale : {cached.source_name or cached.source_url or 'web'}"
            specs_source_type = "cache"
            from_cache = True

    # 3. Recherche web
    if not specs_data or force_web_search:
        web_result = await search_vehicle_specs(vehicle_year, vehicle_make, vehicle_model, vehicle_type)
        if web_result:
            specs_data = web_result
            source_name = web_result.get("source_name", "")
            source_url = web_result.get("source_url", "")
            specs_source = f"{source_name} — {source_url}" if source_url else source_name
            specs_source_type = web_result.get("source_type", "web")

            # Mémoriser dans le cache
            if not web_result.get("is_demo"):
                await save_specs_to_cache(
                    db, vehicle_year, vehicle_make, vehicle_model, vehicle_type,
                    specs_data=web_result,
                    source_url=source_url,
                    source_name=source_name,
                    source_type=specs_source_type,
                )

    # Normaliser la terminologie dans les champs utilisateur
    terminology_corrections = []
    if options_accessories and options_accessories.strip():
        options_accessories, corr1 = normalize_user_input(options_accessories)
        terminology_corrections.extend(corr1)
    if unique_features and unique_features.strip():
        unique_features, corr2 = normalize_user_input(unique_features)
        terminology_corrections.extend(corr2)

    # Construire le texte de specs pour l'IA
    specs_text = _extract_specs_text(specs_data)

    # Charger les exemples modèles (par type de véhicule)
    ex_query = select(DescriptionExample)
    if vehicle_type:
        ex_query = ex_query.where(
            or_(DescriptionExample.vehicle_type == vehicle_type, DescriptionExample.vehicle_type == None)
        ).order_by(DescriptionExample.vehicle_type.desc())  # priorité au type correspondant
    ex_result = await db.execute(ex_query.limit(5))
    examples = [{"title": e.title, "vehicle_type": e.vehicle_type, "content": e.content} for e in ex_result.scalars()]

    # Générer la description
    result = await generate_description(
        year=vehicle_year, make=vehicle_make, model=vehicle_model,
        vehicle_type=vehicle_type, specs_text=specs_text,
        options_accessories=options_accessories,
        unique_features=unique_features,
        examples=examples,
    )

    # Enregistrer dans l'historique
    desc = Description(
        user_id=user.id,
        stock_number=stock_number.strip().upper(),
        vehicle_year=vehicle_year,
        vehicle_make=vehicle_make,
        vehicle_model=vehicle_model,
        vehicle_type=vehicle_type,
        options_accessories=options_accessories,
        unique_features=unique_features,
        generated_description=result.get("description", ""),
        target_audience=result.get("target_audience", ""),
        specs_used=specs_data,
        specs_source=specs_source,
        specs_warnings=result.get("warnings", []),
        status="draft",
    )
    db.add(desc)
    await db.commit()
    await db.refresh(desc)

    # Notifier Supabase Realtime → les autres utilisateurs voient la mise à jour
    from app.services.supabase_client import notify_new_description
    vehicle_label = f"{vehicle_year} {vehicle_make} {vehicle_model}"
    await notify_new_description(
        desc_id=desc.id,
        username=user.username,
        display_name=user.full_name or user.username,
        vehicle=vehicle_label,
        stock_number=stock_number.strip().upper() if stock_number else None,
    )

    if terminology_corrections:
        request.session["terminology_corrections"] = terminology_corrections[:10]

    return RedirectResponse(f"/description/{desc.id}", status_code=303)


@router.get("/description/{desc_id}", response_class=HTMLResponse)
async def view_description(desc_id: int, request: Request, user=Depends(require_login), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Description, User.full_name, User.username)
        .join(User, Description.user_id == User.id)
        .where(Description.id == desc_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404)

    desc, author_name, author_username = row
    if user.role != "admin" and desc.user_id != user.id:
        raise HTTPException(status_code=403)

    terminology_corrections = request.session.pop("terminology_corrections", [])

    return templates.TemplateResponse("description.html", {
        "request": request, "user": user,
        "desc": desc,
        "author": author_name or author_username,
        "vehicle_types": VEHICLE_TYPES,
        "terminology_corrections": terminology_corrections,
    })


@router.post("/description/{desc_id}/save")
async def save_description(
    desc_id: int, request: Request,
    generated_description: str = Form(...),
    target_audience: str = Form(""),
    status: str = Form("draft"),
    user=Depends(require_login),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Description).where(Description.id == desc_id))
    desc = result.scalar_one_or_none()
    if not desc or (user.role != "admin" and desc.user_id != user.id):
        raise HTTPException(status_code=403)

    desc.generated_description = generated_description
    desc.target_audience = target_audience
    desc.status = status if status in ("draft", "approved", "published") else "draft"
    desc.updated_at = datetime.utcnow()
    await db.commit()
    return RedirectResponse(f"/description/{desc_id}?saved=1", status_code=303)


@router.post("/description/{desc_id}/regenerate")
async def regenerate_description(
    desc_id: int, request: Request,
    adjustment_note: str = Form(""),
    user=Depends(require_login),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Description).where(Description.id == desc_id))
    desc = result.scalar_one_or_none()
    if not desc or (user.role != "admin" and desc.user_id != user.id):
        raise HTTPException(status_code=403)

    specs_text = _extract_specs_text(desc.specs_used or {})

    ex_query = select(DescriptionExample)
    if desc.vehicle_type:
        ex_query = ex_query.where(
            or_(DescriptionExample.vehicle_type == desc.vehicle_type, DescriptionExample.vehicle_type == None)
        )
    ex_result = await db.execute(ex_query.limit(5))
    examples = [{"title": e.title, "vehicle_type": e.vehicle_type, "content": e.content} for e in ex_result.scalars()]

    new_result = await generate_description(
        year=desc.vehicle_year, make=desc.vehicle_make,
        model=desc.vehicle_model, vehicle_type=desc.vehicle_type,
        specs_text=specs_text,
        options_accessories=desc.options_accessories or "",
        unique_features=desc.unique_features or "",
        examples=examples,
        adjustment_note=adjustment_note,
    )

    desc.generated_description = new_result.get("description", desc.generated_description)
    desc.target_audience = new_result.get("target_audience", desc.target_audience)
    desc.specs_warnings = new_result.get("warnings", [])
    desc.adjustment_note = adjustment_note
    desc.updated_at = datetime.utcnow()
    await db.commit()
    return RedirectResponse(f"/description/{desc_id}?regenerated=1", status_code=303)


@router.post("/description/{desc_id}/status")
async def update_status(
    desc_id: int, request: Request,
    status: str = Form(...),
    user=Depends(require_login),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Description).where(Description.id == desc_id))
    desc = result.scalar_one_or_none()
    if not desc or (user.role != "admin" and desc.user_id != user.id):
        raise HTTPException(status_code=403)
    if status in ("draft", "approved", "published"):
        desc.status = status
        await db.commit()
    return RedirectResponse(f"/description/{desc_id}", status_code=303)


@router.post("/description/{desc_id}/delete")
async def delete_description(
    desc_id: int, request: Request,
    user=Depends(require_login),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Description).where(Description.id == desc_id))
    desc = result.scalar_one_or_none()
    if not desc or (user.role != "admin" and desc.user_id != user.id):
        raise HTTPException(status_code=403)
    await db.delete(desc)
    await db.commit()
    return RedirectResponse("/history?deleted=1", status_code=303)


@router.get("/description/{desc_id}/export")
async def export_description(desc_id: int, request: Request, user=Depends(require_login), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Description).where(Description.id == desc_id))
    desc = result.scalar_one_or_none()
    if not desc or (user.role != "admin" and desc.user_id != user.id):
        raise HTTPException(status_code=403)

    filename = f"{desc.stock_number}_{desc.vehicle_year}_{desc.vehicle_make}_{desc.vehicle_model}.txt".replace(" ", "_")

    def strip_html(html: str) -> str:
        import re
        text = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        import html as html_lib
        return html_lib.unescape(text).strip()

    content = f"{strip_html(desc.generated_description)}\n\n---\nClientèle cible :\n{strip_html(desc.target_audience)}"
    return PlainTextResponse(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/history", response_class=HTMLResponse)
async def history_page(
    request: Request,
    q: str = "",
    status_filter: str = "",
    user=Depends(require_login),
    db: AsyncSession = Depends(get_db),
):
    query = select(Description, User.full_name, User.username).join(User, Description.user_id == User.id)

    # Tous les utilisateurs voient l'historique complet partagé
    # ⚡ BACKEND — ajouter ici des filtres de permissions par équipe/organisation si besoin

    if q:
        query = query.where(
            or_(
                Description.stock_number.ilike(f"%{q}%"),
                Description.vehicle_make.ilike(f"%{q}%"),
                Description.vehicle_model.ilike(f"%{q}%"),
            )
        )
    if status_filter and status_filter in ("draft", "approved", "published"):
        query = query.where(Description.status == status_filter)

    query = query.order_by(Description.created_at.desc()).limit(100)
    rows = (await db.execute(query)).all()

    descriptions = [
        {
            "id": row[0].id,
            "stock_number": row[0].stock_number,
            "vehicle_year": row[0].vehicle_year,
            "vehicle_make": row[0].vehicle_make,
            "vehicle_model": row[0].vehicle_model,
            "vehicle_type": row[0].vehicle_type,
            "status": row[0].status,
            "created_at": row[0].created_at,
            "author": row[1] or row[2],
        }
        for row in rows
    ]

    return templates.TemplateResponse("history.html", {
        "request": request, "user": user,
        "descriptions": descriptions,
        "q": q,
        "status_filter": status_filter,
    })


def _extract_specs_text(specs_data: dict) -> str:
    """Convertit les données de specs en texte lisible pour l'IA."""
    if not specs_data:
        return "Aucune spécification trouvée."

    if "raw_text" in specs_data:
        return specs_data["raw_text"][:3000]

    if "specs" in specs_data:
        lines = [f"{k}: {v}" for k, v in specs_data["specs"].items() if v]
        return "\n".join(lines)

    return str(specs_data)[:2000]
