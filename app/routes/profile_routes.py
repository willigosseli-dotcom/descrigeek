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


@router.get("/profile/debug")
async def debug_avatar(request: Request, user=Depends(require_login), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text
    from app.database import _is_postgres, DATABASE_URL
    try:
        result = await db.execute(text("SELECT avatar_data IS NOT NULL as has_avatar FROM users WHERE id = :id"), {"id": user.id})
        row = result.fetchone()
        has_avatar = row[0] if row else None
    except Exception as e:
        has_avatar = f"ERREUR: {e}"
    return JSONResponse({
        "db_type": "postgresql" if _is_postgres else "sqlite",
        "db_url_prefix": DATABASE_URL[:40],
        "user_id": user.id,
        "username": user.username,
        "has_avatar_data": has_avatar,
    })


@router.post("/profile/avatar")
async def upload_avatar_endpoint(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(require_login),
    db: AsyncSession = Depends(get_db),
):
    import base64
    from sqlalchemy import select, text
    from app.models import User

    try:
        image_bytes = await file.read()
        if len(image_bytes) > 5 * 1024 * 1024:
            return JSONResponse({"error": "Fichier trop volumineux (max 5 Mo)"}, status_code=400)

        content_type = file.content_type or "image/jpeg"
        b64 = base64.b64encode(image_bytes).decode()
        data_url = f"data:{content_type};base64,{b64}"

        # Mise à jour directe par SQL pour éviter tout problème de cache ORM
        await db.execute(
            text("UPDATE users SET avatar_data = :data WHERE id = :id"),
            {"data": data_url, "id": user.id}
        )
        await db.commit()
        print(f"[Avatar] Sauvegardé pour {user.username} ({len(data_url)} chars)")
        return JSONResponse({"url": data_url})
    except Exception as e:
        print(f"[Avatar] ERREUR : {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
