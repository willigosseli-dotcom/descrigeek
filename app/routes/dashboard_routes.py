from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.auth import require_login
from app.models import Description, User

router = APIRouter()
from app.templates_env import templates


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user=Depends(require_login), db: AsyncSession = Depends(get_db)):
    # Statistiques pour le dashboard
    if user.role == "admin":
        total_q = await db.execute(select(func.count()).select_from(Description))
        draft_q = await db.execute(select(func.count()).select_from(Description).where(Description.status == "draft"))
        approved_q = await db.execute(select(func.count()).select_from(Description).where(Description.status == "approved"))
        published_q = await db.execute(select(func.count()).select_from(Description).where(Description.status == "published"))
        recent_q = await db.execute(
            select(Description, User.full_name, User.username)
            .join(User, Description.user_id == User.id)
            .order_by(Description.created_at.desc())
            .limit(5)
        )
    else:
        total_q = await db.execute(select(func.count()).select_from(Description).where(Description.user_id == user.id))
        draft_q = await db.execute(select(func.count()).select_from(Description).where(Description.user_id == user.id, Description.status == "draft"))
        approved_q = await db.execute(select(func.count()).select_from(Description).where(Description.user_id == user.id, Description.status == "approved"))
        published_q = await db.execute(select(func.count()).select_from(Description).where(Description.user_id == user.id, Description.status == "published"))
        recent_q = await db.execute(
            select(Description, User.full_name, User.username)
            .join(User, Description.user_id == User.id)
            .where(Description.user_id == user.id)
            .order_by(Description.created_at.desc())
            .limit(5)
        )

    recent_rows = recent_q.all()
    recent = [
        {
            "id": row[0].id,
            "stock_number": row[0].stock_number,
            "vehicle_year": row[0].vehicle_year,
            "vehicle_make": row[0].vehicle_make,
            "vehicle_model": row[0].vehicle_model,
            "status": row[0].status,
            "created_at": row[0].created_at,
            "author": row[1] or row[2],
        }
        for row in recent_rows
    ]

    stats = {
        "total": total_q.scalar(),
        "draft": draft_q.scalar(),
        "approved": approved_q.scalar(),
        "published": published_q.scalar(),
    }

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "stats": stats,
        "recent": recent,
    })
