"""
Meeting Prep Gamma — Streamlit Application
============================================
A polished, full-featured UI for generating executive-ready meeting
preparation briefs using the Meeting Prep Gamma agent pipeline.
"""

import asyncio
import os
import sys
import time
import datetime
import traceback

# ---------------------------------------------------------------------------
# Fix asyncio for Streamlit: Streamlit runs scripts in a thread without an
# event loop.  The OpenAI Agents SDK's Runner.run_sync() needs one.
# ---------------------------------------------------------------------------
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import nest_asyncio
nest_asyncio.apply()

import streamlit as st
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap: ensure the package root is importable
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

load_dotenv(os.path.join(_THIS_DIR, ".env"))
load_dotenv()  # also check cwd / parent

# ---------------------------------------------------------------------------
# Imports from the meeting_prep package
# ---------------------------------------------------------------------------
from meeting_prep.shared.models import FileRef
from meeting_prep.agents.meeting_prep.schema import MeetingPrepInputs, MeetingPrepOutput
from meeting_prep.agents.meeting_prep.service import run_meeting_prep_agent
from meeting_prep.shared.gamma_export import (
    list_themes as gamma_list_themes,
    generate_presentation as gamma_generate,
    download_presentation as gamma_download,
)

# ---------------------------------------------------------------------------
# Page Config & CSS
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Meeting Prep Agent — NextQuarter",
    page_icon="https://www.nextquarter.ai/favicon.ico",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    /* ---- Global ---- */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    h1 { font-weight: 800; letter-spacing: -0.5px; }
    h2, h3 { font-weight: 700; }

    /* ---- Sidebar ---- */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0F172A 0%, #1E293B 100%);
    }
    section[data-testid="stSidebar"] * {
        color: #E2E8F0 !important;
    }
    section[data-testid="stSidebar"] .stRadio label {
        color: #CBD5E1 !important;
    }

    /* ---- Primary Buttons ---- */
    .stButton > button {
        background: linear-gradient(135deg, #6366F1 0%, #4F46E5 50%, #4338CA 100%);
        color: white !important;
        border-radius: 10px;
        border: none;
        font-weight: 600;
        font-size: 0.95rem;
        padding: 0.6rem 1.5rem;
        transition: all 0.25s ease;
        box-shadow: 0 2px 8px rgba(99, 102, 241, 0.25);
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(99, 102, 241, 0.35);
    }
    .stButton > button:active {
        transform: translateY(0px);
    }

    /* ---- Download Button ---- */
    .stDownloadButton > button {
        background: linear-gradient(135deg, #059669 0%, #047857 100%);
        color: white !important;
        border-radius: 10px;
        border: none;
        font-weight: 600;
        transition: all 0.25s ease;
        box-shadow: 0 2px 8px rgba(5, 150, 105, 0.25);
    }
    .stDownloadButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(5, 150, 105, 0.35);
    }

    /* ---- Cards ---- */
    .metric-card {
        background: linear-gradient(135deg, #F8FAFC 0%, #F1F5F9 100%);
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1.25rem;
        text-align: center;
        transition: all 0.2s;
    }
    .metric-card:hover {
        border-color: #6366F1;
        box-shadow: 0 4px 12px rgba(99, 102, 241, 0.1);
    }
    .metric-card h3 {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #64748B;
        margin: 0;
    }
    .metric-card p {
        font-size: 1.5rem;
        font-weight: 700;
        color: #0F172A;
        margin: 0.25rem 0 0 0;
    }

    /* ---- Status Badges ---- */
    .badge-ready {
        display: inline-block;
        background: #DCFCE7;
        color: #166534;
        padding: 0.2rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-pending {
        display: inline-block;
        background: #FEF3C7;
        color: #92400E;
        padding: 0.2rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-error {
        display: inline-block;
        background: #FEE2E2;
        color: #991B1B;
        padding: 0.2rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
    }

    /* ---- File Upload Area ---- */
    .upload-zone {
        border: 2px dashed #CBD5E1;
        border-radius: 12px;
        padding: 1.5rem;
        background: #F8FAFC;
        transition: all 0.2s;
    }
    .upload-zone:hover {
        border-color: #6366F1;
        background: #EEF2FF;
    }

    /* ---- Expander Styling ---- */
    .streamlit-expanderHeader {
        font-weight: 600;
        font-size: 1rem;
    }

    /* ---- Markdown Result ---- */
    .deck-output {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 2rem;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    }

    /* ---- Divider ---- */
    hr {
        border: none;
        border-top: 1px solid #E2E8F0;
        margin: 1.5rem 0;
    }

    /* ---- Info boxes ---- */
    .info-banner {
        background: linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 100%);
        border-left: 4px solid #6366F1;
        border-radius: 0 8px 8px 0;
        padding: 1rem 1.25rem;
        margin-bottom: 1.5rem;
    }
    .info-banner p {
        margin: 0;
        color: #3730A3;
        font-size: 0.9rem;
    }

    /* ---- History Card ---- */
    .history-item {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.5rem;
        cursor: pointer;
        transition: all 0.15s;
    }
    .history-item:hover {
        background: #EEF2FF;
        border-color: #6366F1;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# API Key Verification
# ---------------------------------------------------------------------------
def _secret(name: str) -> str | None:
    """Safely read from Streamlit secrets, returning None if unavailable."""
    try:
        return st.secrets.get(name, None)
    except Exception:
        return None

api_key = _secret("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
if api_key:
    os.environ["OPENAI_API_KEY"] = api_key

scrapingdog_key = _secret("SCRAPINGDOG_API_KEY") or os.getenv("SCRAPINGDOG_API_KEY", "")
if scrapingdog_key:
    os.environ["SCRAPINGDOG_API_KEY"] = scrapingdog_key

gamma_api_key = _secret("GAMMA_API_KEY") or os.getenv("GAMMA_API_KEY", "")
if gamma_api_key:
    os.environ["GAMMA_API_KEY"] = gamma_api_key

# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------
_DEFAULTS = {
    # Agent output
    "deck_markdown": None,
    "download_url": None,
    "run_status": None,       # None | "running" | "success" | "error"
    "run_error": None,
    "run_duration": None,

    # Gamma export state
    "gamma_export_url": None,
    "gamma_file_bytes": None,
    "gamma_file_name": None,
    "gamma_status": None,     # None | "running" | "success" | "error"
    "gamma_error": None,

    # Gamma themes cache
    "gamma_themes": None,     # list[dict] | None

    # History of runs
    "history": [],            # list of dicts

    # File uploads persistence (paths)
    "upload_qpilot": None,
    "upload_research": None,
    "upload_playbook": None,
    "upload_solved": None,

    # Current page
    "page": "generate",
}

for key, default in _DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
UPLOAD_DIR = os.path.join(_THIS_DIR, "inputs", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def save_upload(uploaded_file, session_key: str) -> str | None:
    """Persist an uploaded file to disk and store path in session state."""
    if uploaded_file is None:
        return st.session_state.get(session_key)

    path = os.path.join(UPLOAD_DIR, uploaded_file.name)
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.session_state[session_key] = path
    return path


def _make_ref(ref_id: str, path: str) -> FileRef:
    return FileRef(
        id=ref_id,
        filename=os.path.basename(path),
        storage_path=path,
    )


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.0f}s"


def _add_to_history(contact_name: str, company: str, markdown: str, download_url: str | None):
    """Append a run to session history."""
    st.session_state["history"].insert(0, {
        "contact_name": contact_name,
        "company": company,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "markdown": markdown,
        "download_url": download_url,
    })
    # Keep last 20 runs
    st.session_state["history"] = st.session_state["history"][:20]


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_gamma_themes() -> list[dict]:
    """Fetch and cache Gamma themes for 5 minutes."""
    if not gamma_api_key:
        return []
    try:
        return gamma_list_themes(api_key=gamma_api_key)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    # Logo / Brand
    st.markdown("""
    <div style="text-align:center; padding: 1rem 0 0.5rem 0;">
        <div style="font-size: 2rem; margin-bottom: 0.25rem;">📋</div>
        <div style="font-size: 1.1rem; font-weight: 700; letter-spacing: -0.3px;">Meeting Prep Agent</div>
        <div style="font-size: 0.7rem; opacity: 0.6; margin-top: 2px;">NextQuarter AI</div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # Navigation
    page = st.radio(
        "Navigation",
        ["Generate Brief", "Run History", "Settings"],
        index=0,
        label_visibility="collapsed",
    )
    page_map = {"Generate Brief": "generate", "Run History": "history", "Settings": "settings"}
    st.session_state["page"] = page_map[page]

    st.divider()

    # Run Status Indicator
    st.markdown("### Status")
    status = st.session_state["run_status"]
    if status is None:
        st.markdown('<span class="badge-pending">Idle — Ready</span>', unsafe_allow_html=True)
    elif status == "running":
        st.markdown('<span class="badge-pending">Running...</span>', unsafe_allow_html=True)
    elif status == "success":
        dur = st.session_state.get("run_duration")
        dur_str = f" ({_format_duration(dur)})" if dur else ""
        st.markdown(f'<span class="badge-ready">Success{dur_str}</span>', unsafe_allow_html=True)
    elif status == "error":
        st.markdown('<span class="badge-error">Error</span>', unsafe_allow_html=True)

    # File Status
    st.divider()
    st.markdown("### Uploaded Files")

    def _file_indicator(label: str, key: str):
        path = st.session_state.get(key)
        if path and os.path.isfile(path):
            fname = os.path.basename(path)
            st.markdown(f"✅ **{label}**: `{fname}`")
        else:
            st.markdown(f"⚪ **{label}**: Not uploaded")

    _file_indicator("Q-Pilot Report", "upload_qpilot")
    _file_indicator("Research Doc", "upload_research")
    _file_indicator("Playbook Doc", "upload_playbook")
    _file_indicator("Solved Challenges", "upload_solved")

    # Gamma status
    st.divider()
    st.markdown("### Gamma Export")
    if not gamma_api_key:
        st.markdown("⚪ API key not set")
    elif st.session_state.get("gamma_status") == "success":
        st.markdown('<span class="badge-ready">Presentation Ready</span>', unsafe_allow_html=True)
    elif st.session_state.get("gamma_status") == "error":
        st.markdown('<span class="badge-error">Export Failed</span>', unsafe_allow_html=True)
    elif st.session_state.get("gamma_status") == "running":
        st.markdown('<span class="badge-pending">Generating...</span>', unsafe_allow_html=True)
    else:
        st.markdown("⚪ Not exported yet")

    # History count
    st.divider()
    hist_count = len(st.session_state["history"])
    st.markdown(f"### History ({hist_count} runs)")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE: GENERATE BRIEF                                                    ║
# ╚══════════════════════════════════════════════════════════════════════════╝
if st.session_state["page"] == "generate":

    # Header
    st.markdown("""
    <div style="margin-bottom: 0.5rem;">
        <h1 style="margin-bottom: 0.1rem;">📋 Meeting Prep Brief Generator</h1>
        <p style="color: #64748B; font-size: 0.95rem; margin-top: 0;">
            Generate executive-ready, Gamma-formatted meeting preparation briefs in minutes.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # API Key Warning
    if not api_key:
        st.warning("**OpenAI API Key not found.** Set `OPENAI_API_KEY` in your `.env` file or Streamlit secrets to run the agent.")

    # ---- SECTION 1: Contact Information ----
    st.markdown("### 👤 Contact Information")
    st.markdown('<div class="info-banner"><p>Enter details about the executive you are meeting. Name and Company are required.</p></div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        contact_name = st.text_input(
            "Contact Name *",
            placeholder="e.g. Michael Stevens",
            help="Full name of the executive contact",
        )
    with col2:
        title = st.text_input(
            "Title",
            placeholder="e.g. VP of Sales",
            help="Job title of the contact",
        )
    with col3:
        company_name = st.text_input(
            "Company Name *",
            placeholder="e.g. Acme Corp",
            help="Name of the company",
        )

    col4, col5, col6 = st.columns(3)
    with col4:
        email = st.text_input(
            "Email",
            placeholder="e.g. michael@acme.com",
            help="Contact email (optional)",
        )
    with col5:
        linkedin_url = st.text_input(
            "LinkedIn URL",
            placeholder="e.g. https://linkedin.com/in/michael-stevens",
            help="LinkedIn profile URL — the agent will fetch the profile if provided",
        )
    with col6:
        region_city = st.text_input(
            "Region / City",
            placeholder="e.g. San Francisco, CA",
            help="Location context for personalization",
        )

    st.markdown("---")

    # ---- SECTION 2: Meeting Context ----
    st.markdown("### 🎯 Meeting Context")
    st.markdown('<div class="info-banner"><p>Provide context about the meeting to generate more tailored talking points and entry points.</p></div>', unsafe_allow_html=True)

    col7, col8 = st.columns(2)
    with col7:
        meeting_agenda = st.text_area(
            "Meeting Agenda",
            placeholder="e.g. Discuss digital transformation strategy and how NextQuarter can accelerate their revenue forecasting accuracy.",
            height=120,
            help="Topics to discuss during the meeting",
        )
    with col8:
        ae_goal = st.text_area(
            "AE Goal / Value Proposition",
            placeholder="e.g. Identify $500K expansion opportunity in their revenue operations team. Position NextQuarter as their AI-powered forecasting solution.",
            height=120,
            help="Your ultimate objective for this meeting",
        )

    col9, col10 = st.columns(2)
    with col9:
        gtm_vendor = st.text_input(
            "GTM Vendor (Your Org)",
            value="Next Quarter",
            help="Your organization name — appears in the brief as the presenting company",
        )
    with col10:
        days = st.number_input(
            "Recency Window (days)",
            min_value=7,
            max_value=365,
            value=60,
            step=15,
            help="Prioritize research from this many recent days",
        )

    st.markdown("---")

    # ---- SECTION 3: Document Uploads ----
    st.markdown("### 📄 Input Documents")
    st.markdown('<div class="info-banner"><p>Upload supporting documents. The agent reads PDFs, DOCX, TXT, CSV, and XLSX files. All are optional but improve output quality.</p></div>', unsafe_allow_html=True)

    doc_col1, doc_col2 = st.columns(2)

    with doc_col1:
        f_qpilot = st.file_uploader(
            "Q-Pilot Research Report",
            type=["pdf", "txt", "md", "docx"],
            key="fu_qpilot",
            help="Primary research report (PDF recommended). The agent extracts company intelligence, contact details, and initiative data.",
        )
        f_research = st.file_uploader(
            "Company Research Document",
            type=["pdf", "txt", "md", "docx"],
            key="fu_research",
            help="Additional company research or intelligence brief.",
        )

    with doc_col2:
        f_playbook = st.file_uploader(
            "Sales Playbook",
            type=["pdf", "txt", "md", "docx"],
            key="fu_playbook",
            help="Sales playbook with positioning, messaging, and competitive info.",
        )
        f_solved = st.file_uploader(
            "Solved Challenges (CSV)",
            type=["csv", "xlsx", "xls"],
            key="fu_solved",
            help="Case studies CSV with columns: industry, customer_info, challenge, solution, product, reference. Auto-filtered by inferred industry.",
        )

    st.markdown("---")

    # ---- SECTION 4: Advanced Options ----
    with st.expander("⚙️ Advanced Options", expanded=False):
        adv_col1, adv_col2, adv_col3 = st.columns(3)
        with adv_col1:
            strict_persona = st.checkbox(
                "Strict Persona Verification",
                value=False,
                help="When enabled, the agent applies stricter contact name verification for initiative mapping.",
            )
        with adv_col2:
            event_id = st.text_input(
                "Event ID (auto-generated if empty)",
                placeholder="evt-xxxxxxxx",
                help="Optional custom event ID. If empty, one is generated automatically.",
            )
        with adv_col3:
            company_id = st.text_input(
                "Company ID (auto-inferred if empty)",
                placeholder="acme-corp",
                help="Optional company slug. If empty, inferred from Q-Pilot filename.",
            )

    st.markdown("---")

    # ---- GENERATE BUTTON ----
    generate_col1, generate_col2, generate_col3 = st.columns([1, 2, 1])
    with generate_col2:
        generate_clicked = st.button(
            "🚀  Generate Meeting Brief",
            use_container_width=True,
            type="primary",
        )

    # ---- EXECUTION ----
    if generate_clicked:
        # Validation
        errors = []
        if not contact_name.strip():
            errors.append("**Contact Name** is required.")
        if not company_name.strip():
            errors.append("**Company Name** is required.")
        if not api_key:
            errors.append("**OpenAI API Key** is not configured.")

        if errors:
            for err in errors:
                st.error(err)
        else:
            # Save uploads
            p_qpilot = save_upload(f_qpilot, "upload_qpilot")
            p_research = save_upload(f_research, "upload_research")
            p_playbook = save_upload(f_playbook, "upload_playbook")
            p_solved = save_upload(f_solved, "upload_solved")

            # Build inputs
            inputs = MeetingPrepInputs(
                contact_name=contact_name.strip(),
                title=title.strip(),
                company_name=company_name.strip(),
                email=email.strip() or None,
                linkedin_url=linkedin_url.strip() or None,
                region_city=region_city.strip(),
                gtm_vendor=gtm_vendor.strip() or "Next Quarter",
                meeting_agenda=meeting_agenda.strip(),
                ae_goal=ae_goal.strip(),
                days=days,
                strict_persona=strict_persona,
                qpilot_path=_make_ref("qpilot", p_qpilot) if p_qpilot else None,
                research_doc=_make_ref("research", p_research) if p_research else None,
                playbook_doc=_make_ref("playbook", p_playbook) if p_playbook else None,
                solved_challenges_doc=_make_ref("solved", p_solved) if p_solved else None,
                event_id=event_id.strip() or None,
                company_id=company_id.strip() or None,
            )

            # Run agent
            st.session_state["run_status"] = "running"
            st.session_state["run_error"] = None

            progress_placeholder = st.empty()
            status_placeholder = st.empty()

            with progress_placeholder.container():
                progress_bar = st.progress(0, text="Initializing agent...")

            start_time = time.time()

            try:
                # Progress simulation (the agent is a single synchronous call)
                steps = [
                    (0.05, "Reading input documents..."),
                    (0.15, "Processing Q-Pilot report..."),
                    (0.25, "Extracting contact intelligence..."),
                    (0.35, "Building agent payload..."),
                    (0.45, "Running Meeting Prep Agent (GPT-5.2)..."),
                ]
                for pct, msg in steps:
                    progress_bar.progress(pct, text=msg)
                    time.sleep(0.3)

                progress_bar.progress(0.50, text="Agent is reasoning and generating brief... This may take 1-3 minutes.")

                # Actual agent call
                output: MeetingPrepOutput = run_meeting_prep_agent(inputs)

                elapsed = time.time() - start_time
                progress_bar.progress(1.0, text=f"Complete! ({_format_duration(elapsed)})")
                time.sleep(0.5)
                progress_placeholder.empty()

                # Store results
                st.session_state["deck_markdown"] = output.deck_markdown
                st.session_state["download_url"] = output.download_url
                st.session_state["run_status"] = "success"
                st.session_state["run_duration"] = elapsed

                # Add to history
                _add_to_history(
                    contact_name=contact_name.strip(),
                    company=company_name.strip(),
                    markdown=output.deck_markdown,
                    download_url=output.download_url,
                )

            except Exception as e:
                elapsed = time.time() - start_time
                progress_placeholder.empty()
                st.session_state["run_status"] = "error"
                st.session_state["run_error"] = str(e)
                st.session_state["run_duration"] = elapsed

                st.error(f"**Agent failed after {_format_duration(elapsed)}**")
                with st.expander("Error Details", expanded=True):
                    st.code(traceback.format_exc(), language="python")

    # ---- RESULTS DISPLAY ----
    if st.session_state["deck_markdown"]:
        st.markdown("---")
        st.markdown("## 📝 Generated Meeting Brief")

        # Metrics row
        mc1, mc2, mc3, mc4 = st.columns(4)
        markdown_text = st.session_state["deck_markdown"]
        word_count = len(markdown_text.split())
        section_count = markdown_text.count("\n# ")
        char_count = len(markdown_text)

        with mc1:
            st.markdown(f"""
            <div class="metric-card">
                <h3>Words</h3>
                <p>{word_count:,}</p>
            </div>
            """, unsafe_allow_html=True)
        with mc2:
            st.markdown(f"""
            <div class="metric-card">
                <h3>Sections</h3>
                <p>{section_count}</p>
            </div>
            """, unsafe_allow_html=True)
        with mc3:
            st.markdown(f"""
            <div class="metric-card">
                <h3>Characters</h3>
                <p>{char_count:,}</p>
            </div>
            """, unsafe_allow_html=True)
        with mc4:
            dur = st.session_state.get("run_duration")
            st.markdown(f"""
            <div class="metric-card">
                <h3>Generation Time</h3>
                <p>{_format_duration(dur) if dur else "N/A"}</p>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("")

        # Action buttons
        btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])
        with btn_col1:
            st.download_button(
                label="⬇️  Download Markdown",
                data=markdown_text,
                file_name=f"Meeting_Brief_{contact_name.replace(' ', '_') if contact_name else 'brief'}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with btn_col2:
            if st.session_state.get("download_url"):
                st.info(f"**Saved to:** `{st.session_state['download_url']}`")

        # Tabs for viewing
        tab_rendered, tab_raw = st.tabs(["📖 Rendered Preview", "📝 Raw Markdown"])

        with tab_rendered:
            st.markdown('<div class="deck-output">', unsafe_allow_html=True)
            st.markdown(markdown_text)
            st.markdown('</div>', unsafe_allow_html=True)

        with tab_raw:
            st.code(markdown_text, language="markdown")

        # ---- GAMMA EXPORT SECTION ----
        st.markdown("---")
        st.markdown("## 🎨 Export to Gamma Presentation")

        if not gamma_api_key:
            st.warning(
                "**Gamma API Key not configured.** Set `GAMMA_API_KEY` in your "
                "`.env` file or Streamlit secrets to enable presentation export."
            )
        else:
            st.markdown(
                '<div class="info-banner"><p>'
                'Convert your meeting brief into a polished Gamma presentation. '
                'Choose a theme and export format below.'
                '</p></div>',
                unsafe_allow_html=True,
            )

            # Fetch themes
            themes = _fetch_gamma_themes()

            gamma_col1, gamma_col2, gamma_col3 = st.columns([2, 1, 1])

            with gamma_col1:
                # Theme selector
                if themes:
                    theme_options = {
                        t.get("name", t.get("id", "Unknown")): t.get("id", "")
                        for t in themes
                    }
                    # Prepend a "No theme" option
                    display_names = ["(Default — No Theme)"] + list(theme_options.keys())

                    selected_theme_name = st.selectbox(
                        "Gamma Theme",
                        options=display_names,
                        index=0,
                        help="Select a theme from your Gamma workspace. Themes control colors, fonts, and layout styling.",
                    )

                    selected_theme_id = (
                        theme_options.get(selected_theme_name)
                        if selected_theme_name != "(Default — No Theme)"
                        else None
                    )

                    # Show theme details if selected
                    if selected_theme_id:
                        selected_theme = next(
                            (t for t in themes if t.get("id") == selected_theme_id),
                            None,
                        )
                        if selected_theme:
                            colors = selected_theme.get("colorKeywords", [])
                            tones = selected_theme.get("toneKeywords", [])
                            detail_parts = []
                            if colors:
                                detail_parts.append(f"Colors: {', '.join(colors)}")
                            if tones:
                                detail_parts.append(f"Tone: {', '.join(tones)}")
                            if detail_parts:
                                st.caption(" | ".join(detail_parts))
                else:
                    st.info("No themes found in your Gamma workspace. The default theme will be used.")
                    selected_theme_id = None

            with gamma_col2:
                export_format = st.selectbox(
                    "Export Format",
                    options=["pptx", "pdf"],
                    index=0,
                    help="PPTX for editable PowerPoint, PDF for read-only sharing.",
                )

            with gamma_col3:
                st.markdown("<br>", unsafe_allow_html=True)
                gamma_export_clicked = st.button(
                    "🎨  Export to Gamma",
                    use_container_width=True,
                    type="primary",
                )

            # Gamma generation execution
            if gamma_export_clicked:
                st.session_state["gamma_status"] = "running"
                st.session_state["gamma_error"] = None
                st.session_state["gamma_file_bytes"] = None

                gamma_progress = st.empty()
                with gamma_progress.container():
                    gamma_bar = st.progress(0, text="Submitting to Gamma API...")

                def _gamma_progress_cb(msg: str, pct: float):
                    gamma_bar.progress(min(pct, 0.99), text=msg)

                start_gamma = time.time()
                result = gamma_generate(
                    markdown_text=markdown_text,
                    api_key=gamma_api_key,
                    theme_id=selected_theme_id,
                    export_as=export_format,
                    progress_callback=_gamma_progress_cb,
                )
                gamma_elapsed = time.time() - start_gamma

                if result["ok"] and result["export_url"]:
                    gamma_bar.progress(0.95, text="Downloading presentation...")

                    # Download to temp file
                    import tempfile
                    ext = export_format
                    safe_name = (contact_name or "brief").replace(" ", "_")
                    tmp_path = os.path.join(
                        tempfile.gettempdir(),
                        f"Meeting_Brief_{safe_name}.{ext}",
                    )
                    if gamma_download(result["export_url"], tmp_path):
                        with open(tmp_path, "rb") as f:
                            st.session_state["gamma_file_bytes"] = f.read()
                        st.session_state["gamma_file_name"] = os.path.basename(tmp_path)
                        st.session_state["gamma_export_url"] = result["export_url"]
                        st.session_state["gamma_status"] = "success"
                        gamma_bar.progress(1.0, text=f"Done! ({_format_duration(gamma_elapsed)})")
                        time.sleep(0.5)
                        gamma_progress.empty()
                    else:
                        st.session_state["gamma_status"] = "error"
                        st.session_state["gamma_error"] = "Download failed after generation succeeded."
                        gamma_progress.empty()
                else:
                    st.session_state["gamma_status"] = "error"
                    st.session_state["gamma_error"] = result.get("error", "Unknown error")
                    gamma_progress.empty()

            # Show Gamma result
            if st.session_state.get("gamma_status") == "success" and st.session_state.get("gamma_file_bytes"):
                st.success("Gamma presentation generated successfully!")
                dl_col1, dl_col2 = st.columns([1, 3])
                with dl_col1:
                    fname = st.session_state.get("gamma_file_name", "presentation.pptx")
                    mime = (
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                        if fname.endswith(".pptx")
                        else "application/pdf"
                    )
                    st.download_button(
                        label=f"⬇️  Download {fname.split('.')[-1].upper()}",
                        data=st.session_state["gamma_file_bytes"],
                        file_name=fname,
                        mime=mime,
                        use_container_width=True,
                    )

            elif st.session_state.get("gamma_status") == "error":
                st.error(f"**Gamma export failed:** {st.session_state.get('gamma_error', 'Unknown error')}")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE: RUN HISTORY                                                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝
elif st.session_state["page"] == "history":

    st.markdown("""
    <div style="margin-bottom: 1.5rem;">
        <h1 style="margin-bottom: 0.1rem;">📜 Run History</h1>
        <p style="color: #64748B; font-size: 0.95rem; margin-top: 0;">
            View previously generated meeting briefs from this session.
        </p>
    </div>
    """, unsafe_allow_html=True)

    history = st.session_state["history"]

    if not history:
        st.info("No briefs generated yet. Go to **Generate Brief** to create one.")
    else:
        for i, run in enumerate(history):
            with st.expander(
                f"**{run['contact_name']}** @ {run['company']} — {run['timestamp']}",
                expanded=(i == 0),
            ):
                # Metrics
                mc1, mc2 = st.columns(2)
                md_text = run["markdown"]
                with mc1:
                    st.metric("Words", f"{len(md_text.split()):,}")
                with mc2:
                    st.metric("Sections", md_text.count("\n# "))

                # Download
                st.download_button(
                    label="⬇️  Download",
                    data=md_text,
                    file_name=f"Brief_{run['contact_name'].replace(' ', '_')}_{run['timestamp'].replace(':', '-')}.md",
                    mime="text/markdown",
                    key=f"dl_hist_{i}",
                )

                # Preview
                tab_r, tab_m = st.tabs(["Rendered", "Raw"])
                with tab_r:
                    st.markdown(md_text)
                with tab_m:
                    st.code(md_text, language="markdown")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE: SETTINGS                                                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝
elif st.session_state["page"] == "settings":

    st.markdown("""
    <div style="margin-bottom: 1.5rem;">
        <h1 style="margin-bottom: 0.1rem;">⚙️ Settings & Diagnostics</h1>
        <p style="color: #64748B; font-size: 0.95rem; margin-top: 0;">
            Check API key status, environment configuration, and system info.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # API Keys
    st.markdown("### 🔑 API Keys")
    key_col1, key_col2, key_col3 = st.columns(3)
    with key_col1:
        if api_key:
            masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "****"
            st.success(f"**OpenAI API Key:** `{masked}`")
        else:
            st.error("**OpenAI API Key:** Not configured")
    with key_col2:
        if scrapingdog_key:
            masked = scrapingdog_key[:6] + "..." + scrapingdog_key[-4:] if len(scrapingdog_key) > 10 else "****"
            st.success(f"**ScrapingDog Key:** `{masked}`")
        else:
            st.warning("**ScrapingDog Key:** Not configured (LinkedIn fetch disabled)")
    with key_col3:
        if gamma_api_key:
            masked = gamma_api_key[:10] + "..." + gamma_api_key[-4:] if len(gamma_api_key) > 14 else "****"
            st.success(f"**Gamma API Key:** `{masked}`")
        else:
            st.warning("**Gamma API Key:** Not configured (presentation export disabled)")

    st.markdown("---")

    # Environment Info
    st.markdown("### 🖥️ Environment")
    env_col1, env_col2 = st.columns(2)
    with env_col1:
        st.markdown(f"**Python:** `{sys.version.split()[0]}`")
        st.markdown(f"**Working Dir:** `{os.getcwd()}`")
        st.markdown(f"**App Dir:** `{_THIS_DIR}`")
    with env_col2:
        st.markdown(f"**Upload Dir:** `{UPLOAD_DIR}`")
        st.markdown(f"**Output Dir:** `{os.getenv('TRADE_SHOW_OUTPUT_DIR', 'outputs')}`")
        st.markdown(f"**Agent Model:** `gpt-5.2`")
        gamma_theme_count = len(_fetch_gamma_themes()) if gamma_api_key else 0
        st.markdown(f"**Gamma Themes:** `{gamma_theme_count} available`")

    st.markdown("---")

    # Uploads Management
    st.markdown("### 📁 Uploaded Files")
    upload_keys = {
        "upload_qpilot": "Q-Pilot Report",
        "upload_research": "Research Document",
        "upload_playbook": "Sales Playbook",
        "upload_solved": "Solved Challenges CSV",
    }
    for key, label in upload_keys.items():
        path = st.session_state.get(key)
        if path and os.path.isfile(path):
            size_kb = os.path.getsize(path) / 1024
            st.markdown(f"- **{label}:** `{os.path.basename(path)}` ({size_kb:.1f} KB)")
        else:
            st.markdown(f"- **{label}:** Not uploaded")

    st.markdown("---")

    # Clear Session
    st.markdown("### 🧹 Session Management")
    if st.button("Clear All Session Data", type="secondary"):
        for key in _DEFAULTS:
            st.session_state[key] = _DEFAULTS[key]
        st.success("Session cleared. All data reset.")
        st.rerun()


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    '<div style="text-align: center; color: #94A3B8; font-size: 0.8rem; padding: 0.5rem 0;">'
    'Meeting Prep Agent &middot; NextQuarter AI &middot; Powered by GPT-5.2 &middot; Gamma-Ready Output'
    '</div>',
    unsafe_allow_html=True,
)
