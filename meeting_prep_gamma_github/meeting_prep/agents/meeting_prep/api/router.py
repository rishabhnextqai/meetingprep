from fastapi import APIRouter

from meeting_prep.agents.meeting_prep.schema import MeetingPrepInputs, MeetingPrepOutput
from meeting_prep.agents.meeting_prep.service import run_meeting_prep_agent

router = APIRouter(prefix="/api/agents/meeting-prep", tags=["meeting-prep"])


@router.post("", response_model=MeetingPrepOutput)
def run_meeting_prep(inputs: MeetingPrepInputs) -> MeetingPrepOutput:
    """Run Meeting Prep Agent (Gamma-style Output)."""
    return run_meeting_prep_agent(inputs)
