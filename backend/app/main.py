from contextlib import asynccontextmanager
from datetime import date, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import close_mongo_client, close_sql_engine, get_database, get_mongo_client, get_sql_engine
from app.models import Base, Client, Project, Milestone, Invoice
from app.routers.proposals import router as proposals_router
from app.routers.invoices import router as invoices_router
from app.routers.projects import router as projects_router
from app.routers.chat import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_mongo_client()
    
    # Initialize SQL database
    engine = get_sql_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # Seed database if empty
    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_factory() as session:
        # Check if we have clients
        result = await session.execute(select(Client).limit(1))
        if result.first() is None:
            # Seed data!
            # 1. Clients
            acme = Client(
                name="Acme Corporation",
                company_name="Acme Corp",
                email="billing@acme.com",
                phone="123-456-7890"
            )
            wayne = Client(
                name="Wayne Enterprises",
                company_name="Wayne Corp",
                email="finance@waynecorp.com",
                phone="987-654-3210"
            )
            session.add_all([acme, wayne])
            await session.commit() # save to generate IDs
            
            # Refresh to get IDs
            await session.refresh(acme)
            await session.refresh(wayne)
            
            # 2. Projects
            acme_portal = Project(
                client_id=acme.id,
                name="Acme Portal Integration",
                description="Enterprise portal and API integration for client onboarding.",
                status="active",
                start_date=date.today() - timedelta(days=30),
                budget=50000.00
            )
            wayne_app = Project(
                client_id=wayne.id,
                name="Wayne Mobile App",
                description="iOS and Android mobile app development for logistics.",
                status="completed",
                start_date=date.today() - timedelta(days=90),
                end_date=date.today() - timedelta(days=10),
                budget=120000.00
            )
            acme_website = Project(
                client_id=acme.id,
                name="Acme Corp Marketing Website",
                description="Redesign of public marketing site.",
                status="planning",
                budget=15000.00
            )
            session.add_all([acme_portal, wayne_app, acme_website])
            await session.commit()
            
            await session.refresh(acme_portal)
            await session.refresh(wayne_app)
            
            # 3. Milestones
            milestones = [
                Milestone(
                    project_id=acme_portal.id,
                    title="Architecture & Schema Design",
                    description="Database schema design and API endpoints definition.",
                    status="completed",
                    due_date=date.today() - timedelta(days=15),
                    amount=15000.00
                ),
                Milestone(
                    project_id=acme_portal.id,
                    title="Core UI Implementation",
                    description="Implementation of front-end pages and dashboards.",
                    status="in_progress",
                    due_date=date.today() + timedelta(days=15),
                    amount=20000.00
                ),
                Milestone(
                    project_id=wayne_app.id,
                    title="Beta Release",
                    description="Deployment to TestFlight and Google Play Beta.",
                    status="completed",
                    due_date=date.today() - timedelta(days=20),
                    amount=60000.00
                )
            ]
            session.add_all(milestones)
            
            # 4. Invoices
            invoices = [
                Invoice(
                    project_id=acme_portal.id,
                    amount=15000.00,
                    status="paid",
                    due_date=date.today() - timedelta(days=10),
                    issue_date=date.today() - timedelta(days=30)
                ),
                Invoice(
                    project_id=wayne_app.id,
                    amount=60000.00,
                    status="paid",
                    due_date=date.today() - timedelta(days=15),
                    issue_date=date.today() - timedelta(days=45)
                ),
                # Overdue invoice
                Invoice(
                    project_id=acme_portal.id,
                    amount=20000.00,
                    status="sent",
                    due_date=date.today() - timedelta(days=5),
                    issue_date=date.today() - timedelta(days=25)
                ),
                # Sent, not overdue invoice
                Invoice(
                    project_id=wayne_app.id,
                    amount=60000.00,
                    status="sent",
                    due_date=date.today() + timedelta(days=20),
                    issue_date=date.today() - timedelta(days=10)
                )
            ]
            session.add_all(invoices)
            await session.commit()
            
    yield
    await close_mongo_client()
    await close_sql_engine()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(proposals_router)
app.include_router(invoices_router)
app.include_router(projects_router)
app.include_router(chat_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    db = get_database()
    await db.command("ping")
    return {"status": "ok", "service": settings.app_name}


@app.get("/api/info")
async def info():
    return {
        "app": settings.app_name,
        "stack": ["fastapi", "langgraph", "sqlalchemy", "mcp", "mongodb"],
    }
