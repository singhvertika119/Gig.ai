import json
import os
from datetime import date, timedelta
from typing import TypedDict, Optional, Dict, Any

from langgraph.graph import StateGraph, START, END
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from groq import Groq

from app.config import settings
from app.db import get_sql_engine
from app.models import Client, Project, Milestone
from app.schemas import ProjectScope

class ProposalState(TypedDict):
    """LangGraph state schema for the proposal multi-agent workflow."""
    brief: str
    project_scope: Optional[Dict[str, Any]]
    proposal_draft: Optional[str]
    saved_project_id: Optional[int]
    saved_client_id: Optional[int]
    error: Optional[str]

async def scoping_agent(state: ProposalState) -> ProposalState:
    """Node 1: Extract scope, timeline, and pricing into structured JSON using Groq Llama."""
    api_key = settings.groq_api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {**state, "error": "Missing Groq API Key. Please configure GROQ_API_KEY settings or environment variables."}
        
    try:
        client = Groq(api_key=api_key)
        schema_json = json.dumps(ProjectScope.model_json_schema(), indent=2)
        
        prompt = f"""Extract the client scope, timeline, budget, and milestones from this client brief:

Client Brief:
{state['brief']}

You must return a JSON object that adheres strictly to this JSON schema:
{schema_json}
"""
        
        response = client.chat.completions.create(
            model=settings.groq_model or "llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict data extraction assistant that outputs only a JSON object matching the requested schema. "
                        "Be extremely precise and strict when extracting the client name (client_name) and client company (client_company). "
                        "If a company or client name is not explicitly clear in the text but a contact email exists (e.g. contact@alphadynamic.com), "
                        "you must parse and infer the client name from the email domain (e.g. infer 'AlphaDynamic' from '@alphadynamic.com' by capitalizing the name and removing the top-level domain like .com/.org)."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        
        project_scope_dict = json.loads(response.choices[0].message.content.strip())
        return {**state, "project_scope": project_scope_dict}
    except Exception as e:
        return {**state, "error": f"Scoping LLM error: {str(e)}"}

async def drafting_agent(state: ProposalState) -> ProposalState:
    """Node 2: Generate a polished project proposal in Markdown based on the extracted scope using Groq."""
    if state.get("error") or not state.get("project_scope"):
        return state
        
    api_key = settings.groq_api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {**state, "error": "Missing Groq API Key. Please configure GROQ_API_KEY settings or environment variables."}
        
    try:
        client = Groq(api_key=api_key)
        
        scope_str = json.dumps(state["project_scope"], indent=2)
        prompt = f"""You are an expert business consultant. Draft a professional, comprehensive project proposal in markdown format based on the following structured project scope:

Project Scope:
{scope_str}

Include these sections:
1. Executive Summary
2. Detailed Scope of Work
3. Milestones & Deliverables Table (showing descriptions, due days, and amounts)
4. Financial Terms & Budget Breakdown
5. Next Steps

Make it professional, polished, and detailed. Do not include any meta comments, chatbot pleasantries, or wrapping markdown code blocks (e.g. no ```markdown), output only the raw markdown proposal text."""

        response = client.chat.completions.create(
            model=settings.groq_model or "llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        
        return {**state, "proposal_draft": response.choices[0].message.content.strip()}
    except Exception as e:
        return {**state, "error": f"Drafting LLM error: {str(e)}"}

async def db_saver_agent(state: ProposalState) -> ProposalState:
    """Node 3: Persist the project and milestones in the database using SQLAlchemy."""
    if state.get("error") or not state.get("project_scope"):
        return state
        
    scope = state["project_scope"]
    engine = get_sql_engine()
    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    try:
        async with async_session_factory() as session:
            async with session.begin():
                # 1. Resolve or Create Client
                client_name = scope.get("client_name") or scope.get("client_company") or "Valued Client"
                client_company = scope.get("client_company") or client_name
                
                stmt = select(Client).where(Client.name == client_name)
                result = await session.execute(stmt)
                db_client = result.scalars().first()
                
                if not db_client:
                    db_client = Client(
                        name=client_name,
                        company_name=client_company,
                        email=scope.get("client_email"),
                        phone=scope.get("client_phone"),
                    )
                    session.add(db_client)
                    await session.flush()  # populated id
                
                # 2. Check if a project with the same name and client already exists before inserting
                project_name = scope.get("project_name", "Proposal Project")
                proj_stmt = select(Project).where(
                    Project.client_id == db_client.id,
                    Project.name == project_name
                )
                proj_result = await session.execute(proj_stmt)
                db_project = proj_result.scalars().first()
                
                if not db_project:
                    duration = scope.get("duration_days") or 30
                    db_project = Project(
                        client_id=db_client.id,
                        name=project_name,
                        description=scope.get("project_description"),
                        status="planning",
                        start_date=date.today(),
                        end_date=date.today() + timedelta(days=duration),
                        budget=scope.get("budget", 0.0),
                    )
                    session.add(db_project)
                    await session.flush()  # populated id
                    
                    # 3. Save Milestones (only insert milestones if creating the project)
                    for m in scope.get("milestones", []):
                        due_days = m.get("due_days_from_start") or 30
                        due_date = date.today() + timedelta(days=due_days)
                        db_milestone = Milestone(
                            project_id=db_project.id,
                            title=m.get("title"),
                            description=m.get("description"),
                            due_date=due_date,
                            status="pending",
                            amount=m.get("amount", 0.0),
                        )
                        session.add(db_milestone)
                else:
                    print(f"Skipping duplicate project insertion for client {db_client.id} and project name '{project_name}'.")
                
                await session.commit()
                
                return {
                    **state,
                    "saved_project_id": db_project.id,
                    "saved_client_id": db_client.id
                }
    except Exception as e:
        return {**state, "error": f"Database save error: {str(e)}"}

# Define and compile the multi-agent graph workflow
workflow = StateGraph(ProposalState)
workflow.add_node("scoping_agent", scoping_agent)
workflow.add_node("drafting_agent", drafting_agent)
workflow.add_node("db_saver_agent", db_saver_agent)

workflow.add_edge(START, "scoping_agent")
workflow.add_edge("scoping_agent", "drafting_agent")
workflow.add_edge("drafting_agent", "db_saver_agent")
workflow.add_edge("db_saver_agent", END)

proposal_graph = workflow.compile()
