from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

load_dotenv()

from app.database import init_db
from app.auth import NotAuthenticatedException, NotAuthorizedException
from app.routes import auth_routes, dashboard_routes, admin_routes, profile_routes, examples_routes, description_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="DescriGeek", lifespan=lifespan)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=86400)

os.makedirs("data/assets", exist_ok=True)
os.makedirs("data/uploads", exist_ok=True)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/assets", StaticFiles(directory="data/assets"), name="assets")

app.include_router(auth_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(admin_routes.router)
app.include_router(profile_routes.router)
app.include_router(examples_routes.router)
app.include_router(description_routes.router)

# Instance Jinja2Templates partagée (filtres + globaux enregistrés dans templates_env)
from app.templates_env import templates as _templates  # noqa: F401 — déclenche l'enregistrement


@app.exception_handler(NotAuthenticatedException)
async def not_authenticated_handler(request: Request, exc):
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/login", status_code=302)


@app.exception_handler(NotAuthorizedException)
async def not_authorized_handler(request: Request, exc):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse("error.html", {
        "request": request, "code": 403,
        "message": "Vous n'avez pas la permission d'accéder à cette page."
    }, status_code=403)


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse("error.html", {
        "request": request, "code": 403,
        "message": "Vous n'avez pas la permission d'accéder à cette page."
    }, status_code=403)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse("error.html", {
        "request": request, "code": 404,
        "message": "Page introuvable."
    }, status_code=404)
