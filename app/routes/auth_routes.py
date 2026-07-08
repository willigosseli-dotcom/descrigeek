from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models import User
from app.auth import verify_password, hash_password, get_current_user
from app.services import app_config

router = APIRouter()
from app.templates_env import templates


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("home.html", {"request": request})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    error = request.session.pop("login_error", None)
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    app_password: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    # 1. Mot de passe général de l'app (partagé, changé de temps en temps)
    if not await app_config.verify_general_password(db, app_password):
        request.session["login_error"] = "Mot de passe de l'application incorrect."
        return RedirectResponse("/login", status_code=303)

    # 2. Compte personnel
    result = await db.execute(
        select(User).where(User.username == username, User.is_active == True)  # noqa: E712
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        request.session["login_error"] = "Nom d'utilisateur ou mot de passe incorrect."
        return RedirectResponse("/login", status_code=303)

    request.session["user_id"] = user.id
    request.session["user_role"] = user.role
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    error = request.session.pop("register_error", None)
    form = request.session.pop("register_form", {})
    return templates.TemplateResponse("register.html", {
        "request": request, "error": error, "form": form,
    })


@router.post("/register")
async def register(
    request: Request,
    full_name: str = Form(""),
    username: str = Form(...),
    email: str = Form(""),
    password: str = Form(...),
    password2: str = Form(...),
    app_password: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    def _echec(msg):
        request.session["register_error"] = msg
        request.session["register_form"] = {
            "full_name": full_name, "username": username, "email": email,
        }
        return RedirectResponse("/register", status_code=303)

    username = username.strip()
    if not await app_config.verify_general_password(db, app_password):
        return _echec("Mot de passe de l'application incorrect — demandez-le à votre gestionnaire.")
    if len(username) < 3:
        return _echec("Le nom d'utilisateur doit faire au moins 3 caractères.")
    if len(password) < 6:
        return _echec("Le mot de passe doit faire au moins 6 caractères.")
    if password != password2:
        return _echec("Les deux mots de passe ne correspondent pas.")

    # Unicité du nom d'utilisateur (insensible à la casse)
    exists = await db.execute(select(User).where(func.lower(User.username) == username.lower()))
    if exists.scalar_one_or_none():
        return _echec("Ce nom d'utilisateur est déjà pris.")

    user = User(
        username=username,
        full_name=full_name.strip() or None,
        email=email.strip() or None,
        hashed_password=hash_password(password),
        role="user",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Connexion automatique après inscription
    request.session["user_id"] = user.id
    request.session["user_role"] = user.role
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)
