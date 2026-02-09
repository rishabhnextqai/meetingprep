import argparse
import sys
import logging
import os
import uuid
from meeting_prep.agents.meeting_prep.service import run_meeting_prep_agent
from meeting_prep.agents.meeting_prep.schema import MeetingPrepInputs
from meeting_prep.shared.models import FileRef

# Setup basic logging
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s: %(message)s")
logger = logging.getLogger("meeting_prep_cli")


def main():
    parser = argparse.ArgumentParser(description="Run Meeting Prep Agent (Gamma-ready) with exact PipelineState parameters")
    
    # Core Identity
    parser.add_argument("--contact-name", required=True, help="Name of the executive contact")
    parser.add_argument("--title", default="", help="Title of the contact")
    parser.add_argument("--company-name", required=True, help="Name of the company")
    parser.add_argument("--email", default="", help="Contact email")
    parser.add_argument("--linkedin-url", default="", help="LinkedIn profile URL")
    
    # Meeting Context
    parser.add_argument("--meeting-agenda", default="", help="Agenda for the meeting")
    parser.add_argument("--ae-goal", default="", help="Ultimate goal (AE Goal)")
    parser.add_argument("--region-city", default="", help="Region or City context")
    parser.add_argument("--gtm-vendor", default="Next Quarter", help="Your organization name")
    parser.add_argument("--days", type=int, default=60, help="Recency window for research")

    # Files
    parser.add_argument("--qpilot-path", required=False, help="Path to Q-Pilot report (PDF/TXT)")
    parser.add_argument("--research-doc-path", "--research-doc", type=str, default="")
    parser.add_argument("--playbook-doc-path", "--playbook-doc", type=str, default="")
    parser.add_argument("--solved-challenges-doc-path", "--solved-challenges-doc", type=str, default="")
    
    # IDs
    parser.add_argument("--event-id", help="Optional Event ID")
    parser.add_argument("--company-id", help="Optional Company ID")

    args = parser.parse_args()

    # 2. Build inputs
    # Helper to clean up file refs
    def _make_ref(path_str):
        if not path_str or not path_str.strip():
            return None
        return FileRef(
            id=str(uuid.uuid4()),
            storage_path=os.path.abspath(path_str.strip()),
            filename=os.path.basename(path_str.strip())
        )

    inputs = MeetingPrepInputs(
        contact_name=args.contact_name,
        title=args.title,
        company_name=args.company_name,
        email=args.email,
        linkedin_url=args.linkedin_url,
        region_city=args.region_city,
        gtm_vendor=args.gtm_vendor,
        
        meeting_agenda=args.meeting_agenda,
        ae_goal=args.ae_goal,
        
        qpilot_path=_make_ref(args.qpilot_path),
        research_doc=_make_ref(args.research_doc_path),
        playbook_doc=_make_ref(args.playbook_doc_path),
        solved_challenges_doc=_make_ref(args.solved_challenges_doc_path),

        event_id=args.event_id,
        company_id=args.company_id,
    )

    try:
        logger.info(f"Starting Meeting Prep for {args.contact_name} @ {args.company_name}...")
        output = run_meeting_prep_agent(inputs)
        
        print("\n" + "="*40)
        print("SUCCESS: Meeting Brief Generated")
        print("="*40)
        print(f"Download URL (Simulated): {output.download_url}")
        print("-" * 40)
        print("Markdown Content (Snippet):")
        print(output.deck_markdown[:500] + "...\n(truncated)")
        print("="*40 + "\n")
        
    except Exception as e:
        logger.error(f"Failed to run agent: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
