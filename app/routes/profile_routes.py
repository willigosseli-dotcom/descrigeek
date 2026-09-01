from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth import require_login, hash_password

router = APIRouter()
from app.templates_env import templates


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user=Depends(require_login)):
    success = request.session.pop("profile_saved", None)
    return templates.TemplateResponse("profile.html", {"request": request, "user": user, "success": success})


@router.post("/profile/save")
async def save_profile(
    request: Request,
    text_size: str = Form("normal"),
    color_theme: str = Form("vr-thetford"),
    custom_accent_color: str = Form(None),
    new_password: str = Form(""),
    confirm_password: str = Form(""),
    user=Depends(require_login),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from app.models import User
    result = await db.execute(select(User).where(User.id == user.id))
    u = result.scalar_one()

    u.text_size = text_size if text_size in ("tiny", "normal", "large", "xlarge") else "normal"
    u.color_theme = color_theme if color_theme in ("vr-thetford", "sunset", "dark", "custom") else "vr-thetford"
    u.custom_accent_color = custom_accent_color if color_theme == "custom" and custom_accent_color else None

    if new_password and new_password == confirm_password:
        u.hashed_password = hash_password(new_password)

    await db.commit()
    request.session["profile_saved"] = True
    return RedirectResponse("/profile", status_code=303)


@router.post("/profile/avatar")
async def upload_avatar_endpoint(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(require_login),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from app.models import User
    from app.services.supabase_client import upload_avatar

    image_bytes = await file.read()
    content_type = file.content_type or "image/jpeg"
    url = upload_avatar(user.username, image_bytes, content_type)
    if not url:
        return JSONResponse({"error": "Échec de l'upload vers Supabase"}, status_code=500)

    result = await db.execute(select(User).where(User.id == user.id))
    u = result.scalar_one()
    u.avatar_url = url
    await db.commit()
    return JSONResponse({"url": url})
