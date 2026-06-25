from fastapi import APIRouter, HTTPException

from app.agents import proposal_graph
from app.schemas import ProposalRequest

router = APIRouter(prefix="/api/proposals", tags=["proposals"])

@router.post("/generate")
async def generate_proposal(req: ProposalRequest):
    """
    Generate a structured project proposal and insert the resources into the database
    by executing the multi-agent scoping -> drafting -> db_saver LangGraph workflow.
    """
    initial_state = {
        "brief": req.brief,
        "project_scope": None,
        "proposal_draft": None,
        "saved_project_id": None,
        "saved_client_id": None,
        "error": None
    }
    
    result_state = await proposal_graph.ainvoke(initial_state)
    
    if result_state.get("error"):
        raise HTTPException(
            status_code=400,
            detail=result_state["error"]
        )
        
    return {
        "status": "success",
        "client_id": result_state.get("saved_client_id"),
        "project_id": result_state.get("saved_project_id"),
        "project_scope": result_state.get("project_scope"),
        "proposal_draft": result_state.get("proposal_draft")
    }
