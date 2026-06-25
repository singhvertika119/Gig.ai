from fastapi import APIRouter, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker, selectinload

from app.db import get_sql_engine
from app.models import Invoice, Project
from app.agents import invoice_ops_graph

router = APIRouter(prefix="/api/invoices", tags=["invoices"])

async def run_ops_in_background(invoice_id: int):
    """Asynchronous background task to run the Invoice Ops workflow."""
    initial_state = {
        "invoice_id": invoice_id,
        "client_email": None,
        "project_name": None,
        "amount_owed": None,
        "status": None,
        "webhook_status": None,
        "error": None
    }
    await invoice_ops_graph.ainvoke(initial_state)

@router.post("/{invoice_id}/mark-overdue")
async def mark_invoice_overdue(invoice_id: int, background_tasks: BackgroundTasks):
    """
    Mark an invoice as overdue in the database and trigger the Ops Agent workflow
    in an asynchronous background task to dispatch reminder notifications.
    """
    engine = get_sql_engine()
    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    # 1. Update the database record
    async with async_session_factory() as session:
        async with session.begin():
            stmt = select(Invoice).where(Invoice.id == invoice_id)
            result = await session.execute(stmt)
            invoice = result.scalar_one_or_none()
            
            if not invoice:
                raise HTTPException(status_code=404, detail=f"Invoice with ID {invoice_id} not found.")
                
            invoice.status = "overdue"
            await session.commit()
            
    # 2. Add to background tasks
    background_tasks.add_task(run_ops_in_background, invoice_id)
    
    return {
        "status": "success",
        "invoice_id": invoice_id,
        "db_status": "overdue",
        "webhook_status": "pending"
    }

@router.get("")
async def get_invoices():
    """Fetch all invoices, eager loading project and client data."""
    engine = get_sql_engine()
    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_factory() as session:
        # Query and eager load project and client
        stmt = select(Invoice).options(
            selectinload(Invoice.project).selectinload(Project.client)
        )
        result = await session.execute(stmt)
        invoices = result.scalars().all()
        return [
            {
                "id": inv.id,
                "amount": float(inv.amount),
                "status": inv.status,
                "due_date": inv.due_date.isoformat(),
                "issue_date": inv.issue_date.isoformat(),
                "project_name": inv.project.name if inv.project else None,
                "client_name": inv.project.client.name if inv.project and inv.project.client else None,
                "client_email": inv.project.client.email if inv.project and inv.project.client else None
            }
            for inv in invoices
        ]
