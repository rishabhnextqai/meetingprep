from typing import Optional
from pydantic import BaseModel, Field

from meeting_prep.shared.models import FileRef, DeckOutputBase


class MeetingPrepInputs(BaseModel):
    """Inputs for Meeting Prep Agent (Aligned with PipelineState).
    
    Reflects the exact fields used in nq_meeting_prep_agent_final.
    """

    # Primary Contact
    contact_name: str
    title: str = ""
    company_name: str
    linkedin_url: Optional[str] = None
    email: Optional[str] = None  # retained as optional extra

    # Context / Strategy
    meeting_agenda: str = ""
    ae_goal: str = ""  # The "Ultimate Goal"
    region_city: str = ""
    gtm_vendor: str = "Next Quarter"
    
    # Files
    qpilot_path: Optional[FileRef] = None
    
    # New parameter for "Solved Challenges" doc
    solved_challenges_doc: Optional[FileRef] = None
    # Retaining split inputs as optional fallbacks or for new functionality
    research_doc: Optional[FileRef] = None
    playbook_doc: Optional[FileRef] = None

    # Config
    days: int = 60
    strict_persona: bool = False
    
    # IDs (optional, internal)
    event_id: Optional[str] = None
    company_id: Optional[str] = None


class MeetingPrepOutput(DeckOutputBase):
    """Output Meeting Prep Brief deck."""
    pass
