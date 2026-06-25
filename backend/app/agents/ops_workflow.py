from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from sqlalchemy import select
from sqlalchemy.orm import selectinload, sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import settings
from app.db import get_sql_engine
from app.models import Client, Project, Milestone, Invoice

class OpsState(TypedDict):
    """LangGraph state schema for invoice operations (overdue reminders)."""
    invoice_id: int
    client_email: Optional[str]
    project_name: Optional[str]
    amount_owed: Optional[float]
    status: Optional[str]
    webhook_status: Optional[str]
    error: Optional[str]

async def fetch_invoice_details(state: OpsState) -> OpsState:
    """Node 1: Fetch invoice details, including project and client relationships, from the database."""
    engine = get_sql_engine()
    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    try:
        async with async_session_factory() as session:
            # Query the invoice and eager load project and client
            stmt = (
                select(Invoice)
                .where(Invoice.id == state["invoice_id"])
                .options(
                    selectinload(Invoice.project).selectinload(Project.client)
                )
            )
            result = await session.execute(stmt)
            invoice = result.scalar_one_or_none()
            
            if not invoice:
                return {**state, "error": f"Invoice with ID {state['invoice_id']} not found."}
                
            if not invoice.project:
                return {**state, "error": f"Project relation missing for Invoice ID {state['invoice_id']}."}
                
            if not invoice.project.client:
                return {**state, "error": f"Client relation missing for Project ID {invoice.project.id}."}
                
            return {
                **state,
                "client_email": invoice.project.client.email or "billing@example.com",
                "project_name": invoice.project.name,
                "amount_owed": float(invoice.amount),
                "status": invoice.status
            }
    except Exception as e:
        return {**state, "error": f"Database read error: {str(e)}"}

def sync_send_email(smtp_host: str, smtp_port: int, smtp_user: str, smtp_password: str, to_email: str, project_name: str, amount_owed: float, invoice_id: int):
    """Synchronously send email to keep smtplib interactions clean and run inside to_thread."""
    msg = MIMEMultipart()
    msg['From'] = smtp_user
    msg['To'] = to_email
    msg['Subject'] = f"Friendly Payment Reminder: {project_name}"
    
    body = f"""Dear Client,

This is a friendly reminder that invoice #{invoice_id} for the project "{project_name}" is currently marked as overdue.
Outstanding Amount: ${amount_owed:,.2f}

Please arrange for payment at your earliest convenience.

Best regards,
The Gig.ai Team"""
    
    msg.attach(MIMEText(body, 'plain'))
    
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, to_email, msg.as_string())

async def ops_agent_node(state: OpsState) -> OpsState:
    """Node 2: Dispatch notifications to n8n webhook, Discord webhook, and/or smtplib email."""
    if state.get("error"):
        return state
        
    if state.get("status") != "overdue":
        # Skip if the status in the database is not overdue
        return {**state, "webhook_status": "skipped", "error": "Invoice status is not overdue."}
        
    client_email = state.get("client_email")
    project_name = state.get("project_name")
    amount_owed = state.get("amount_owed")
    invoice_id = state.get("invoice_id")
    
    payload = {
        "client_email": client_email,
        "project_name": project_name,
        "amount_owed": amount_owed,
        "invoice_id": invoice_id
    }
    
    status_msg = []
    webhook_status = "sent"
    error_msg = None
    
    # 1. Dispatch to n8n Webhook
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.n8n_webhook_url,
                json=payload,
                timeout=5.0
            )
            if not (200 <= response.status_code < 300):
                webhook_status = "failed"
                error_msg = f"n8n webhook returned status code {response.status_code}"
                status_msg.append(f"n8n failed: {response.status_code}")
            else:
                status_msg.append("n8n webhook success")
    except Exception as e:
        webhook_status = "failed"
        error_msg = f"n8n connection error: {str(e)}"
        status_msg.append("n8n offline/error")

    # 2. Dispatch to Discord Webhook if configured
    if settings.discord_webhook_url:
        try:
            discord_payload = {
                "embeds": [
                    {
                        "title": "⚠️ Payment Reminder Notice",
                        "description": f"An invoice for project **{project_name}** has been marked as overdue.",
                        "color": 16734208,  # Orange-red color
                        "fields": [
                            {"name": "Client Email", "value": client_email or "N/A", "inline": True},
                            {"name": "Amount Owed", "value": f"${amount_owed:,.2f}", "inline": True},
                            {"name": "Invoice ID", "value": f"#{invoice_id}", "inline": True}
                        ],
                        "footer": {"text": "Gig.ai Operations Console"}
                    }
                ]
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(settings.discord_webhook_url, json=discord_payload, timeout=5.0)
                if resp.status_code >= 300:
                    status_msg.append(f"Discord failed: {resp.status_code}")
                else:
                    status_msg.append("Discord webhook success")
        except Exception as e:
            status_msg.append(f"Discord connection error: {str(e)}")

    # 3. Dispatch direct SMTP Email if configured
    if settings.smtp_user and settings.smtp_password:
        try:
            await asyncio.to_thread(
                sync_send_email,
                settings.smtp_host,
                settings.smtp_port,
                settings.smtp_user,
                settings.smtp_password,
                client_email or "billing@example.com",
                project_name,
                amount_owed,
                invoice_id
            )
            status_msg.append("Direct SMTP email success")
        except Exception as e:
            status_msg.append(f"Direct SMTP failed: {str(e)}")

    final_error = error_msg
    if status_msg:
        combined_status = " | ".join(status_msg)
        if error_msg:
            final_error = f"{error_msg} ({combined_status})"
        else:
            final_error = f"Details: {combined_status}"

    return {
        **state,
        "webhook_status": webhook_status,
        "error": final_error
    }

# Define and compile the Ops Graph
workflow = StateGraph(OpsState)
workflow.add_node("fetch_invoice_details", fetch_invoice_details)
workflow.add_node("ops_agent_node", ops_agent_node)

workflow.add_edge(START, "fetch_invoice_details")
workflow.add_edge("fetch_invoice_details", "ops_agent_node")
workflow.add_edge("ops_agent_node", END)

invoice_ops_graph = workflow.compile()
