from typing import Any, Dict

from agents import Agent, Runner, WebSearchTool  # OpenAI Agents SDK

from meeting_prep.shared import files, persistence
from meeting_prep.shared.logging import logger
import csv
import io
from meeting_prep.shared.identifiers import (
    generate_event_id,
    infer_company_id_from_filename,
    infer_event_id_from_ref,
)

from .schema import MeetingPrepInputs, MeetingPrepOutput
from .prompt import build_meeting_prep_system_prompt
from .tools.scrapedog import fetch_person_profile

from dotenv import load_dotenv
import os
import re

load_dotenv()


def _repair_contact_name_in_text(text: str, contact_name: str) -> str:
    """
    Normalizes occurrences of the contact name.
    1. Tries to fix simple whitespace/newline splits (e.g. 'Michael\\nStevens' -> 'Michael Stevens').
    2. If that fails, checks for 'proximity' matches (parts of name within 150 chars) and INJECTS
       the full name to ensure strict string matching passes without destroying data.
    """
    if not text or not contact_name:
        return text

    # Check if we already have it (fast path)
    if contact_name in text:
        return text
    
    parts = contact_name.split()
    if len(parts) < 2:
        return text

    # Pre-processing: Remove <br> tags which pymupdf4llm often inserts in table cells
    # This helps clear up "Abhushan<br>Sahu" -> "Abhushan Sahu" automatically if close
    text_clean = text.replace("<br>", " ").replace("<br/>", " ")
    if contact_name in text_clean:
         # If cleaning br tags made the name contiguous, usage the cleaned text
         # But we must be careful not to return the whole cleaned text if we want to preserve layout?
         # Actually, replacing <br> with space is generally safe and good for readability.
         text = text_clean

    # Strategy 1: Simple Whitespace Repair (replace match with clean name)
    # Pattern: part0 + \s+ + part1 ...
    pattern_simple = r"\s+".join(map(re.escape, parts))
    text, count = re.subn(pattern_simple, contact_name, text, flags=re.IGNORECASE)
    if count > 0:
        return text

    # Strategy 2: Proximity Injection (Insert name if parts are close)
    # Only checks start vs end of name to handle multi-part names roughly
    first = parts[0]
    last = parts[-1]
    
    # Pattern: first + anything (max 200 chars) + last
    # We capture the whole span to prepend the clean name to it
    proximity_pattern = re.compile(
        re.escape(first) + r".{0,200}?" + re.escape(last), 
        re.IGNORECASE | re.DOTALL
    )
    
    # Function to inject name: "MATCH" -> "Full Name MATCH"
    def _inject(match):
        return f"{contact_name} {match.group(0)}"
        
    text, count = proximity_pattern.subn(_inject, text)
    
    return text


def _get_relevant_solved_challenges(csv_text: str, research_text: str) -> str:
    """
    Parses the solved challenges CSV and filters for the most relevant industry based on research text.
    """
    if not csv_text or not csv_text.strip():
        return ""

    # 1. Define Industry Keywords Mapping
    # industries found: Financial Services, Manufacturing/Logistics, Media/Streaming, Online Travel, Retail/eCommerce, SaaS/Technology, Startup
    industry_keywords = {
        "Retail/eCommerce": ["retail", "ecommerce", "e-commerce", "shopping", "store", "merchandise", "consumer", "goods"],
        "Financial Services": ["bank", "finance", "financial", "fintech", "insurance", "investment", "payment", "wealth", "capital"],
        "Manufacturing/Logistics": ["manufacturing", "logistics", "supply chain", "shipping", "freight", "transport", "production", "industrial"],
        "Media/Streaming": ["media", "streaming", "entertainment", "broadcasting", "content", "video", "music", "gaming"],
        "Online Travel": ["travel", "booking", "flight", "hotel", "accommodation", "tourism", "vacation"],
        "SaaS/Technology": ["saas", "technology", "software", "cloud", "platform", "tech", "digital", "app"],
        "Startup": ["startup", "scaleup", "venture", "growth", "early stage"]
    }

    # 2. Infer Industry from Research Text
    text_lower = research_text.lower()
    scores = {ind: 0 for ind in industry_keywords}
    
    for industry, keywords in industry_keywords.items():
        for keyword in keywords:
            if keyword in text_lower:
                scores[industry] += text_lower.count(keyword)
    
    # Get top scoring industry
    best_industry = max(scores, key=scores.get)
    if scores[best_industry] == 0:
        logger.warning("Could not infer industry from research text. Defaulting to all (capped).")
        target_industry = None # No specific filter
    else:
        logger.info(f"Inferred Industry: {best_industry} (Score: {scores[best_industry]})")
        target_industry = best_industry

    # 3. Parse CSV and Filter
    output_lines = []
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
        count = 0
        for row in reader:
            # Check industry match
            row_industry = row.get("industry", "").strip()
            
            if target_industry and row_industry != target_industry:
                continue
                
            # Formatting the output
            # Columns: "industry","customer_info","problem_overview","challenge","product","capability","solution", "reference"
            customer = row.get("customer_info", "N/A")
            challenge = row.get("challenge", "N/A")
            solution = row.get("solution", "N/A")
            product = row.get("product", "N/A")
            reference = row.get("reference", "N/A")
            
            output_lines.append(f"### Case Study: {customer}")
            output_lines.append(f"- **Industry**: {row_industry}")
            output_lines.append(f"- **Challenge**: {challenge}")
            output_lines.append(f"- **Solution ({product})**: {solution}")
            output_lines.append(f"- **Reference**: {reference}")
            output_lines.append("") # Spacer
            
            count += 1
            if count >= 30: # Safety cap to avoid huge prompt
                output_lines.append("... (List truncated for length)")
                break
                
        if not output_lines and target_industry:
             output_lines.append(f"No specific case studies found for inferred industry: {target_industry}")

    except Exception as e:
        logger.error(f"Error parsing solved challenges CSV: {e}")
        return f"Error processing Solved Challenges data: {e}"

    if not output_lines:
        return "No solved challenges data found."
        
    header = f"Relevant Solved Challenges (Inferred Industry: {target_industry if target_industry else 'All'})\n"
    return header + "\n" + "\n".join(output_lines)

    return header + "\n" + "\n".join(output_lines)

def _extract_linkedin_for_contact(text: str, contact_name: str) -> str:
    """
    Locates the contact in the text and extracts their specific LinkedIn URL,
    repairing PDF fragmentation if necessary.
    """
    if not text or not contact_name:
        return ""
    
    lines = text.splitlines()
    contact_parts = contact_name.lower().split()
    
    # 1. Find the "Anchor Line" - where the contact's name appears
    # best match logic: line containing most parts of the name
    anchor_idx = -1
    best_match_count = 0
    
    for i, line in enumerate(lines):
        lower_line = line.lower()
        match_count = sum(1 for part in contact_parts if part in lower_line)
        
        # We want a strong match (at least one full name part, preferably both)
        # Check against "Key Contacts" table heuristic (often Name is first/second col)
        if match_count > 0:
            if match_count > best_match_count:
                best_match_count = match_count
                anchor_idx = i
            # If we match all parts, break early? No, keep scanning for dense block?
            # Actually, "Eddie" is on line X, "Guerrero" on X+1.
            # So a single line match might be partial.
            # Let's verify if we can find a *block* match.
            
    # Fallback: if names are split across lines (e.g. Eddie \n Guerrero)
    # Scan for sequential lines matching parts
    if anchor_idx == -1 or best_match_count < len(contact_parts):
        for i in range(len(lines) - 1):
             # check window of 2 lines
             window = (lines[i] + " " + lines[i+1]).lower()
             match_count = sum(1 for part in contact_parts if part in window)
             if match_count >= len(contact_parts): # Found split name
                 anchor_idx = i
                 break

    if anchor_idx == -1:
        logger.info(f"Could not locate contact '{contact_name}' in text.")
        return ""
        
    logger.info(f"Found contact '{contact_name}' anchor at line {anchor_idx}.")
    
    # 2. Extract Window (Anchor ± 6 lines) to capture the row's data
    start_line = max(0, anchor_idx - 2)
    end_line = min(len(lines), anchor_idx + 8)
    window_lines = lines[start_line:end_line]
    
    # 3. Scan for LinkedIn Pattern in this window
    # Pattern: http...lin... matches, look ahead for kedin...
    import re
    
    found_urls = []
    
    i = 0
    while i < len(window_lines):
        line = window_lines[i]
        tokens = line.split()
        
        # Find start token
        idx = -1
        for ti, t in enumerate(tokens):
            if (t.endswith('lin') or t.endswith('linkedin')) and ('http' in t or 'www' in t):
                idx = ti
                break
        
        if idx != -1:
            # Found start. Look at next line(s) for continuation
            if i + 1 < len(window_lines):
                next_tokens = window_lines[i+1].split()
                idx2 = -1
                for ti2, t in enumerate(next_tokens):
                    if t.startswith('kedin') or t.startswith('.com'):
                        idx2 = ti2
                        break
                
                if idx2 != -1:
                    # Stitch Base
                    base = tokens[idx] + next_tokens[idx2]
                    
                    # Stitch Slug Parts
                    # Heuristic: Slug parts are likely lowercase, contain name parts, or are alphanumeric IDs
                    full_url = base
                    
                    # Look at the END of the current token (idx2). Does it look like it continues?
                    # e.g. "kedin.com/in/e" -> ends in 'e'. Need more.
                    # Scan remaining lines in window associated with this column
                    
                    curr_line_offset = i + 2
                    slug_building = True
                    
                    while slug_building and curr_line_offset < len(window_lines):
                        check_tokens = window_lines[curr_line_offset].split()
                        
                        candidate = None
                        
                        for t in check_tokens:
                            # Clean the token first
                            clean_t = t.rstrip(',.;!:')
                            
                            # 1. Negative Filters (Reject obvious bad tokens)
                            if not clean_t: continue
                            if t[0].isupper(): continue # Title Case -> Start of new sentence/Title
                            if not re.match(r'^[a-z0-9\-]+$', clean_t): continue # Invalid chars
                            if clean_t.lower() in ["and", "the", "of", "in", "for", "with", "a", "an", "at", "as", "to"]: continue
                            
                            # 2. Positive Filters (Must look like a slug part)
                            # - Contains part of the name (e.g. "michael")
                            # - Is an Alphanumeric ID (has digits or is mixed)
                            # - Is a connector (-)
                            # - Is a known slug continuation? (hard to define, rely on name/id)
                            
                            is_name_part = any(part in clean_t.lower() for part in contact_parts if len(part) > 2) # avoiding short parts matching randomly
                            has_digit = any(c.isdigit() for c in clean_t)
                            is_connector = (clean_t == '-')
                            
                            if is_name_part or has_digit or is_connector:
                                candidate = clean_t
                                break # Found the slug part for this line
                        
                        if candidate:
                            full_url += candidate
                            curr_line_offset += 1
                        else:
                            # Stop if no valid slug part found in this line
                            slug_building = False
                    
                    # Validate URL
                    full_url = full_url.strip('-,.;:')
                    if "linkedin.com/in/" in full_url:
                        found_urls.append(full_url)
        i += 1
        
    if found_urls:
         # Dedup and pick best
         best_url = found_urls[0] 
         logger.info(f"🎯 Extracted Target LinkedIn: {best_url}")
         return best_url

    return ""

def _build_input_payload(inputs: MeetingPrepInputs) -> str:
    """
    Build the single text payload for the Meeting Prep Agent.
    Mapping strict inputs to the prompt structure.
    """
    
    # 1. Read files
    qpilot_text = files.read_document(inputs.qpilot_path) if inputs.qpilot_path else ""
    research_text = files.read_document(inputs.research_doc) if inputs.research_doc else ""
    playbook_text = files.read_document(inputs.playbook_doc) if inputs.playbook_doc else ""
    solved_challenges_raw = files.read_document(inputs.solved_challenges_doc) if inputs.solved_challenges_doc else ""

    # Normalization: specific repair for the contact name to fix PDF splitting (e.g. "Michael\nStevens")
    if inputs.contact_name:
        if research_text:
            research_text = _repair_contact_name_in_text(research_text, inputs.contact_name)
        if playbook_text:
            playbook_text = _repair_contact_name_in_text(playbook_text, inputs.contact_name)

    # Targeted LinkedIn Extraction
    # If not provided in inputs, try to find it in the docs for THIS contact
    found_linkedin = ""
    if not inputs.linkedin_url:
        found_linkedin = _extract_linkedin_for_contact(research_text, inputs.contact_name)
        if not found_linkedin:
             found_linkedin = _extract_linkedin_for_contact(playbook_text, inputs.contact_name)
    
    # Process Solved Challenges with smart inference
    combined_research_for_inference = qpilot_text + "\n" + research_text + "\n" + playbook_text
    solved_challenges_processed = ""
    if solved_challenges_raw:
        solved_challenges_processed = _get_relevant_solved_challenges(solved_challenges_raw, combined_research_for_inference)
    
    # Note: We do NOT globally repair text anymore to avoid garbage.
    combined_research = qpilot_text + "\n\n" + research_text + "\n\n" + playbook_text

    # Prepare LinkedIn display with aggressive hint
    final_linkedin = inputs.linkedin_url or found_linkedin
    linkedin_field = f"{final_linkedin} (ACTION REQUIRED: FETCH PROFILE)" if final_linkedin else "N/A"

    parts: list[str] = [
        "You are the Meeting Prep Specialist Agent.\n",
        "Use the following inputs to create a Gamma-ready Meeting Brief deck.\n\n",
        f"# MEETING CONTEXT\n",
        f"Attendee: {inputs.contact_name}\n",
        f"Title: {inputs.title}\n",
        f"Company: {inputs.company_name}\n",
        f"Email: {inputs.email or 'N/A'}\n",
        f"LinkedIn: {linkedin_field}\n",
        f"Region/City: {inputs.region_city or 'N/A'}\n",
        f"GTM Vendor (Us): {inputs.gtm_vendor}\n\n",
        
        f"# STRATEGY CONTEXT\n",
        f"Meeting Agenda: {inputs.meeting_agenda or 'N/A'}\n",
        f"Ultimate Goal (AE Goal): {inputs.ae_goal or 'N/A'}\n\n",
    ]
    
    combined_research = qpilot_text + "\n\n" + research_text + "\n\n" + playbook_text

    # Add inputs... (omitted for brevity in replacement, but parts is list)
    if qpilot_text.strip():
        parts.extend(["# INPUT: Q-Pilot Document\n", qpilot_text, "\n\n"])

    if research_text.strip():
        parts.extend(["# INPUT: Research Document\n", research_text, "\n\n"])

    if playbook_text.strip():
        parts.extend(["# INPUT: Playbook Document\n", playbook_text, "\n\n"])

    if solved_challenges_processed.strip():
        parts.extend(["# INPUT: Solved Challenges Document\n", solved_challenges_processed, "\n\n"])

    parts.extend([
        "# TASK\n",
        "Synthesize these inputs into the Meeting Brief deck.\n",
        "- CRITICAL: A LinkedIn URL is provided in the Context. You MUST call the `fetch_person_profile` tool to get the biography. Do NOT skip this step.\n",
        "- Output MUST be clean Markdown, Gamma-ready, with `#` headings and `---` separators.\n"
    ])

    return "".join(parts)


def run_meeting_prep_agent(inputs: MeetingPrepInputs) -> MeetingPrepOutput:
    """
    Run the Meeting Prep Agent and return the deck.
    """
    # 1) Resolve IDs
    event_id = inputs.event_id or generate_event_id()
    company_id = inputs.company_id
    if not company_id and inputs.qpilot_path:
        company_id = infer_company_id_from_filename(inputs.qpilot_path.filename)
    if not company_id:
        company_id = "unknown_company"

    logger.info("Running Meeting Prep Agent for %s @ %s (EventID: %s)", inputs.contact_name, inputs.company_name, event_id)

    # 2) Build System Prompt + Payload
    system_prompt = build_meeting_prep_system_prompt(inputs.contact_name, inputs.gtm_vendor)
    payload = _build_input_payload(inputs)

    # 3) Configure Agent
    agent = Agent(
        name="Meeting Prep Agent",
        instructions=system_prompt,
        model="gpt-5.2",
        tools=[WebSearchTool(), fetch_person_profile],
    )

    # 4) Run
    result = Runner.run_sync(agent, input=payload)
    deck_markdown = result.final_output

    # 5) Persist
    download_url = persistence.save_deck(
        event_id=event_id,
        step="meeting_prep",
        markdown=deck_markdown,
    )

    return MeetingPrepOutput(deck_markdown=deck_markdown, download_url=download_url)
