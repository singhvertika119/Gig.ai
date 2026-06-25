from typing import List, Optional
from pydantic import BaseModel, Field

class MilestoneScope(BaseModel):
    """Structured scope details for a single project milestone."""
    title: str = Field(description="Short title of the milestone (e.g. Initial Design, Testing)")
    description: str = Field(description="Detailed description of deliverables for this milestone")
    due_days_from_start: int = Field(description="Number of days from the project start when this milestone is due")
    amount: float = Field(description="Allocated price/amount for this milestone (should sum up to project budget)")

class ProjectScope(BaseModel):
    """Structured scope details extracted from a client brief."""
    client_name: str = Field(description="Full name of the client contact person")
    client_company: Optional[str] = Field(None, description="Official company name of the client")
    client_email: Optional[str] = Field(None, description="Contact email address of the client")
    client_phone: Optional[str] = Field(None, description="Contact phone number of the client")
    
    project_name: str = Field(description="Short descriptive name for the project")
    project_description: str = Field(description="Overall explanation of the project scope and deliverables")
    budget: float = Field(description="Total project budget/price")
    duration_days: int = Field(description="Estimated total project duration in days")
    
    milestones: List[MilestoneScope] = Field(default_factory=list, description="Extracted milestone deliverables")

class ProposalRequest(BaseModel):
    """Request payload for the proposal generation endpoint."""
    brief: str = Field(..., description="The client brief or project description, often messy and unorganized.")
