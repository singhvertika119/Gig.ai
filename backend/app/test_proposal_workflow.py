import asyncio
import json
import os
from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.db import get_sql_engine, close_sql_engine
from app.models import Base, Client, Project, Milestone
from app.agents import proposal_graph
from app.agents.workflow import db_saver_agent
from app.config import settings

async def run_tests():
    print("=== Starting Proposal Workflow Tests ===")
    
    # Delete the SQLite database file if it exists to ensure a clean run
    db_path = "gigai.db"
    if os.path.exists(db_path):
        try:
            # Dispose engine if already bound or close connection
            await close_sql_engine()
            os.remove(db_path)
            print("Cleaned up existing test database file.")
        except Exception as e:
            print(f"Could not remove database file: {e}")
            
    # 1. Ensure tables are created
    engine = get_sql_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 2. Test database saving node independently of LLM
    print("\n1. Testing Database Saving Node (db_saver_agent)...")
    mock_scope = {
        "client_name": "Supernova Corp",
        "client_company": "Supernova Inc",
        "client_email": "hello@supernova.com",
        "client_phone": "555-0199",
        "project_name": "Supernova Analytics Hub",
        "project_description": "A real-time sales reporting system.",
        "budget": 25000.00,
        "duration_days": 45,
        "milestones": [
            {
                "title": "Design & Prototyping",
                "description": "Figma screens and architecture document.",
                "due_days_from_start": 10,
                "amount": 5000.00
            },
            {
                "title": "Core Implementation",
                "description": "Backend services and charts page.",
                "due_days_from_start": 30,
                "amount": 15000.00
            },
            {
                "title": "Final Launch",
                "description": "Production rollout and testing.",
                "due_days_from_start": 45,
                "amount": 5000.00
            }
        ]
    }
    
    state = {
        "brief": "E-commerce dashboard brief",
        "project_scope": mock_scope,
        "proposal_draft": "Draft proposal markdown...",
        "saved_project_id": None,
        "saved_client_id": None,
        "error": None
    }
    
    saved_state = await db_saver_agent(state)
    if saved_state.get("error"):
        print(f"  [FAIL] Database saving node returned error: {saved_state['error']}")
        assert False
        
    assert saved_state.get("saved_project_id") is not None
    assert saved_state.get("saved_client_id") is not None
    print(f"  [PASS] Saved Client ID: {saved_state['saved_client_id']}")
    print(f"  [PASS] Saved Project ID: {saved_state['saved_project_id']}")
    
    # 2b. Test duplicate check in db_saver_agent
    print("\n1b. Testing Duplicate Project Check in db_saver_agent...")
    retry_state = {
        "brief": "E-commerce dashboard brief",
        "project_scope": mock_scope,
        "proposal_draft": "Draft proposal markdown...",
        "saved_project_id": None,
        "saved_client_id": None,
        "error": None
    }
    second_saved_state = await db_saver_agent(retry_state)
    assert second_saved_state.get("error") is None
    assert second_saved_state.get("saved_project_id") == saved_state["saved_project_id"]
    print(f"  [PASS] Duplicate project check skipped duplicate insertion and returned existing Project ID: {second_saved_state['saved_project_id']}")
    
    # Verify in DB
    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_factory() as session:
        # Check Client
        client_res = await session.execute(
            select(Client).where(Client.id == saved_state["saved_client_id"])
        )
        client = client_res.scalar_one()
        assert client.name == "Supernova Corp"
        assert client.company_name == "Supernova Inc"
        
        # Check Project
        project_res = await session.execute(
            select(Project).where(Project.id == saved_state["saved_project_id"])
        )
        project = project_res.scalar_one()
        assert project.budget == 25000.00
        assert project.end_date == date.today() + timedelta(days=45)
        
        # Check Milestones
        milestones_res = await session.execute(
            select(Milestone).where(Milestone.project_id == saved_state["saved_project_id"])
        )
        milestones = milestones_res.scalars().all()
        assert len(milestones) == 3
        print("  [PASS] Database verification checks passed successfully.")

    # 3. Test Full Multi-Agent Graph if API Key is configured
    print("\n2. Testing Full Multi-Agent Graph using Groq...")
    api_key = settings.groq_api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("Skipping full LangGraph flow test because GROQ_API_KEY is not configured.")
    else:
        messy_brief = (
            "We are looking to build a new client portal for 'Nebula Ventures'. "
            "Please call it the 'Nebula Client Portal'. We want a budget of $40000. "
            "It should take around 60 days total. Contact email is contact@nebulaventures.com. "
            "First milestone is UI Mockups in 15 days for $10000. "
            "Second is Beta Release in 40 days for $20000. "
            "Third is Launch in 60 days for $10000. "
            "The brief description: Portal to let our investors view portfolio performance."
        )
        
        print("API Key found. Executing graph...")
        initial_state = {
            "brief": messy_brief,
            "project_scope": None,
            "proposal_draft": None,
            "saved_project_id": None,
            "saved_client_id": None,
            "error": None
        }
        
        final_state = await proposal_graph.ainvoke(initial_state)
        
        if final_state.get("error"):
            print(f"  [FAIL] Graph returned error: {final_state['error']}")
            assert False
            
        print("\n=== Structured Scope Extracted ===")
        print(json.dumps(final_state["project_scope"], indent=2))
        
        print("\n=== Proposal Draft Generated ===")
        print(final_state["proposal_draft"])
        
        print("\n=== Saved Resource IDs ===")
        print(f"Client ID: {final_state['saved_client_id']}")
        print(f"Project ID: {final_state['saved_project_id']}")
        
        assert final_state["saved_client_id"] is not None
        assert final_state["saved_project_id"] is not None
        assert "Nebula" in final_state["project_scope"]["project_name"]
        print("  [PASS] Full LangGraph Multi-Agent Flow completed successfully.")
        
        # 3b. Test case: email domain client inference
        print("\n2b. Testing Client Name inference from email domain...")
        inference_brief = (
            "We need a backend API built for cloud storage. "
            "Budget is $15000. Timeline is 30 days. "
            "Please call it the 'Cloud Storage API'. "
            "Email: engineering@alphadynamic.com"
        )
        
        inf_state = {
            "brief": inference_brief,
            "project_scope": None,
            "proposal_draft": None,
            "saved_project_id": None,
            "saved_client_id": None,
            "error": None
        }
        
        inf_final_state = await proposal_graph.ainvoke(inf_state)
        assert inf_final_state.get("error") is None
        extracted_client = inf_final_state["project_scope"].get("client_name") or inf_final_state["project_scope"].get("client_company")
        print(f"Extracted client name/company: '{extracted_client}'")
        assert "AlphaDynamic" in extracted_client
        print("  [PASS] Client name correctly inferred from email domain.")

    print("\n=== All Proposal Workflow Tests Passed ===")

if __name__ == "__main__":
    asyncio.run(run_tests())
