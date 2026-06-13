from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.auth import require_admin, hash_password
from app.models import User
import json, os

router = APIRouter(prefix="/admin")
from app.templates_env import templates

SETTINGS_PATH = "config/settings.json"
TERMINOLOGY_PATH = "config/terminology.json"


@router.get("/users", response_class=HTMLResponse)
async def list_users(request: Request, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return templates.TemplateResponse("admin/users.html", {"request": request, "user": admin, "users": users})


@router.post("/users/create")
async def create_user(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(""),
    email: str = Form(""),
    password: str = Form(...),
    role: str = Form("user"),
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    hashed = hash_password(password)
    new_user = User(
        username=username,
        full_name=full_name or None,
        email=email or None,
        hashed_password=hashed,
        role=role,
    )
    db.add(new_user)
    await db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/toggle")
async def toggle_user(user_id: int, request: Request, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    if u and u.id != admin.id:
        u.is_active = not u.is_active
        await db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    request: Request,
    new_password: str = Form(...),
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    if u:
        u.hashed_password = hash_password(new_password)
        await db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, admin=Depends(require_admin)):
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        settings = json.load(f)
    with open(TERMINOLOGY_PATH, "r", encoding="utf-8") as f:
        terminology = json.load(f)
    return templates.TemplateResponse("admin/settings.html", {
        "request": request, "user": admin,
        "settings": settings, "terminology": terminology,
    })


@router.post("/settings/save")
async def save_settings(
    request: Request,
    closing_paragraph: str = Form(...),
    dealership_name: str = Form(...),
    dealership_city: str = Form(...),
    dealership_phone: str = Form(...),
    dealership_website: str = Form(...),
    admin=Depends(require_admin),
):
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        settings = json.load(f)
    settings["closing_paragraph"] = closing_paragraph
    settings["dealership"]["name"] = dealership_name
    settings["dealership"]["city"] = dealership_city
    settings["dealership"]["phone"] = dealership_phone
    settings["dealership"]["website"] = dealership_website
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    return RedirectResponse("/admin/settings", status_code=303)


@router.post("/settings/terminology/add")
async def add_term(
    request: Request,
    term_en: str = Form(...),
    term_fr: str = Form(...),
    admin=Depends(require_admin),
):
    with open(TERMINOLOGY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["terms"].append({"en": term_en, "fr": term_fr})
    with open(TERMINOLOGY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return RedirectResponse("/admin/settings#terminology", status_code=303)


@router.post("/settings/terminology/delete/{index}")
async def delete_term(index: int, request: Request, admin=Depends(require_admin)):
    with open(TERMINOLOGY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if 0 <= index < len(data["terms"]):
        data["terms"].pop(index)
    with open(TERMINOLOGY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return RedirectResponse("/admin/settings#terminology", status_code=303)
