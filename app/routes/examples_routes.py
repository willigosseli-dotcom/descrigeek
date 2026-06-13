from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.auth import require_admin
from app.models import DescriptionExample

router = APIRouter(prefix="/admin/examples")
from app.templates_env import templates


@router.get("", response_class=HTMLResponse)
async def list_examples(request: Request, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DescriptionExample).order_by(DescriptionExample.created_at.desc()))
    examples = result.scalars().all()
    return templates.TemplateResponse("admin/examples.html", {"request": request, "user": admin, "examples": examples})


@router.post("/add")
async def add_example(
    request: Request,
    title: str = Form(...),
    vehicle_type: str = Form(""),
    content: str = Form(...),
    notes: str = Form(""),
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    ex = DescriptionExample(
        title=title,
        vehicle_type=vehicle_type or None,
        content=content,
        notes=notes or None,
        created_by=admin.id,
    )
    db.add(ex)
    await db.commit()
    return RedirectResponse("/admin/examples", status_code=303)


@router.post("/{ex_id}/edit")
async def edit_example(
    ex_id: int,
    request: Request,
    title: str = Form(...),
    vehicle_type: str = Form(""),
    content: str = Form(...),
    notes: str = Form(""),
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DescriptionExample).where(DescriptionExample.id == ex_id))
    ex = result.scalar_one_or_none()
    if ex:
        ex.title = title
        ex.vehicle_type = vehicle_type or None
        ex.content = content
        ex.notes = notes or None
        await db.commit()
    return RedirectResponse("/admin/examples", status_code=303)


@router.post("/{ex_id}/delete")
async def delete_example(ex_id: int, request: Request, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DescriptionExample).where(DescriptionExample.id == ex_id))
    ex = result.scalar_one_or_none()
    if ex:
        await db.delete(ex)
        await db.commit()
    return RedirectResponse("/admin/examples", status_code=303)
