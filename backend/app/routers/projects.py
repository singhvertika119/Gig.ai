from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload, sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sql_engine
from app.models import Project

router = APIRouter(prefix="/api/projects", tags=["projects"])

@router.get("")
async def get_projects():
    """Fetch all projects, including the related client contact details."""
    engine = get_sql_engine()
    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_factory() as session:
        stmt = select(Project).options(selectinload(Project.client))
        result = await session.execute(stmt)
        projects = result.scalars().all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "status": p.status,
                "budget": float(p.budget) if p.budget is not None else None,
                "start_date": p.start_date.isoformat() if p.start_date else None,
                "end_date": p.end_date.isoformat() if p.end_date else None,
                "client_name": p.client.name if p.client else None
            }
            for p in projects
        ]
