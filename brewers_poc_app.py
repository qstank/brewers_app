from __future__ import annotations

import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

# Load configuration
with open("config.yml", "r") as f:
    config = yaml.safe_load(f)

RESULTS_DIR = Path("results")

st.set_page_config(page_title="Brewers Tailored Marketing Engine POC", layout="wide")

SCHEDULE_PATH = Path("data") / "GameTicketPromotionPrice.csv"
FAN_PATH = Path("data") / "brewers mock fan data.csv"

SEGMENT_LABELS = {
    "Die-hard": "Die-Hard Danny",
    "F&B": "Foodie Frank",
    "Family": "Parent Patty",
    "Social": "Tailgate Tammy",
}

SEGMENT_GUIDANCE = {
    "Die-hard": {
        "tone": "baseball-smart, energetic, insider",
        "hooks": ["division battle", "pitching matchup", "see the roster live", "ballpark energy"],
        "image": "Action-forward image with batter/pitcher focus, scoreboard details, and strong Brewers branding.",
        "cta": "See tickets",
    },
    "F&B": {
        "tone": "appetizing, lively, experience-first",
        "hooks": ["ballpark eats", "cold beer", "try something new", "make the game your night out"],
        "image": "Food-and-drink-led image concept with branded cups, concession favorites, and stadium background.",
        "cta": "Plan your night",
    },
    "Family": {
        "tone": "welcoming, easy, family-friendly",
        "hooks": ["easy family outing", "weekend memory", "kids love game day", "simple night out together"],
        "image": "Family-focused image with parents and kids smiling in seats, mascot/stadium atmosphere, daylight or early evening feel.",
        "cta": "Bring the family",
    },
    "Social": {
        "tone": "social, upbeat, group-energy",
        "hooks": ["weekend vibes", "pregame energy", "friends night out", "grab seats and make it a plan"],
        "image": "Social scene with friends in Brewers gear, drinks/food nearby, lively concourse or tailgate-adjacent feel.",
        "cta": "Grab your seats",
    },
}


@st.cache_data
def load_schedule(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path).copy()
    df["START DATE"] = pd.to_datetime(df["START DATE"], format="%m/%d/%y", errors="coerce")
    df["GAME_DATE_DISPLAY"] = df["START DATE"].dt.strftime("%Y-%m-%d")
    df["GAME_TIME_DISPLAY"] = df["START TIME"].astype(str)

    parsed = df["SUBJECT"].apply(parse_subject)
    df["OPPONENT"] = parsed.apply(lambda x: x["opponent"])
    df["HOME_AWAY"] = parsed.apply(lambda x: x["home_away"])

    df["GAME_LABEL"] = (
        df["GAME_DATE_DISPLAY"].fillna("Unknown Date")
        + " | "
        + df["OPPONENT"].fillna("Unknown")
        + " | "
        + df["GAME_TIME_DISPLAY"].fillna("Unknown Time")
    )
    return df.sort_values(["START DATE", "GAME_TIME_DISPLAY", "SUBJECT"]).reset_index(drop=True)


@st.cache_data
def load_fans(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path).copy()
    if "Segment" in df.columns:
        df["Segment"] = df["Segment"].replace({"Die hard": "Die-hard", "Food": "F&B"})
    return df



def parse_subject(subject: str) -> dict:
    if pd.isna(subject):
        return {"opponent": "", "home_away": ""}

    subject = str(subject).strip()
    home_match = re.match(r"^(.*?)\s+at\s+Brewers$", subject, flags=re.IGNORECASE)
    away_match = re.match(r"^Brewers\s+at\s+(.*)$", subject, flags=re.IGNORECASE)

    if home_match:
        return {"opponent": home_match.group(1).strip(), "home_away": "Home"}
    if away_match:
        return {"opponent": away_match.group(1).strip(), "home_away": "Away"}
    return {"opponent": subject, "home_away": "Unknown"}



def build_segment_summary(df: pd.DataFrame, segment: str) -> dict:
    seg_df = df[df["Segment"] == segment].copy() if segment in df["Segment"].unique() else pd.DataFrame()
    if seg_df.empty:
        return {
            "segment": segment,
            "sample_size": 0,
            "attendance_behavior": [],
            "attendance_distribution": "",
            "attendance_table": {},
            "email_engagement": "Unknown",
            "email_engagement_distribution": "",
            "email_table": {},
            "interests": [],
            "interests_distribution": "",
            "interests_table": {},
            "notes": [],
            "notes_distribution": "",
            "notes_table": {},
        }

    n = len(seg_df)

    def top_with_pct(series, top_n=5):
        counts = series.dropna().astype(str).value_counts().head(top_n)
        return [f"{val} ({count}/{n}, {count*100//n}%)" for val, count in counts.items()]

    def counts_dict(series, top_n=None):
        """Return {value: 'count (pct%)' } for all values (no limit)."""
        counts = series.dropna().astype(str).value_counts()
        if top_n:
            counts = counts.head(top_n)
        return {val: f"{count} ({count*100//n}%)" for val, count in counts.items()}

    attendance_counts = seg_df["Attendance_Behavior"].dropna().astype(str).value_counts().head(5)
    email_counts = seg_df["Email_Engagement"].dropna().astype(str).value_counts()
    interest_counts = seg_df["Interests"].dropna().astype(str).value_counts().head(5)
    note_counts = seg_df["Notes"].dropna().astype(str).value_counts().head(5)

    return {
        "segment": segment,
        "sample_size": n,
        "attendance_behavior": attendance_counts.index.tolist(),
        "attendance_distribution": "; ".join(top_with_pct(seg_df["Attendance_Behavior"])),
        "attendance_table": counts_dict(seg_df["Attendance_Behavior"]),
        "email_engagement": email_counts.idxmax(),
        "email_engagement_distribution": "; ".join(top_with_pct(seg_df["Email_Engagement"])),
        "email_table": counts_dict(seg_df["Email_Engagement"]),
        "interests": interest_counts.index.tolist(),
        "interests_distribution": "; ".join(top_with_pct(seg_df["Interests"])),
        "interests_table": counts_dict(seg_df["Interests"]),
        "notes": note_counts.index.tolist(),
        "notes_distribution": "; ".join(top_with_pct(seg_df["Notes"])),
        "notes_table": counts_dict(seg_df["Notes"]),
    }



def build_rule_based_output(game_row: pd.Series, segment: str, summary: dict, extra_notes: str = "") -> dict:
    g = SEGMENT_GUIDANCE[segment]
    game_date = game_row.get("GAME_DATE_DISPLAY", "")
    opponent = game_row.get("OPPONENT", "")
    game_time = game_row.get("GAME_TIME_DISPLAY", "")
    home_away = game_row.get("HOME_AWAY", "Home")
    is_home = home_away == "Home"
    daypart = "tonight" if "PM" in str(game_time) else "this game"

    venue = "American Family Field" if is_home else f"{opponent}'s ballpark"
    location_phrase = "at the ballpark" if is_home else f"on the road in {opponent} territory"
    ticket_phrase = "a home game ticket" if is_home else "away game tickets"
    watch_phrase = "be in the stands" if is_home else "follow the Brewers on the road"
    broadcast_info = str(game_row.get("DESCRIPTION", "")).strip() if not is_home else ""

    interests = ", ".join(summary.get("interests", [])[:2]) or "game-day moments"
    attendance = ", ".join(summary.get("attendance_behavior", [])[:2]) or "live games"

    if segment == "Die-hard":
        if is_home:
            subject = f"{opponent} vs. Brewers: be there {daypart}"
            preheader = f"For fans who follow every matchup, this is one to catch live on {game_date}."
            headline = f"Catch the matchup live against {opponent}"
            body = (
                f"You follow the details, and this game gives you a reason to be in the ballpark. "
                f"With interest around {interests}, now is a great time to lock in {ticket_phrase} for {game_date} at {game_time}."
            )
        else:
            subject = f"Brewers at {opponent}: don't miss this road matchup"
            preheader = f"The Crew heads to {opponent} on {game_date} — tune in or travel."
            headline = f"Brewers take on {opponent} on the road"
            body = (
                f"The Brewers are heading to {opponent} territory, and with your interest in {interests}, "
                f"this is a road game worth watching. Catch every pitch on {game_date} at {game_time}."
            )
    elif segment == "F&B":
        if is_home:
            subject = f"Your next Brewers night out starts here"
            preheader = f"Great game, great eats, and a ballpark experience worth planning for {game_date}."
            headline = f"Make the Brewers game your next night out"
            body = (
                f"From {interests} to the full stadium atmosphere, this home matchup with {opponent} is more than the game itself. "
                f"Grab {ticket_phrase} and turn {game_date} into an easy outing built around the full ballpark experience."
            )
        else:
            subject = f"Brewers road game watch party — eat, drink, cheer"
            preheader = f"The Crew is at {opponent} on {game_date}. Make it a watch party."
            headline = f"Turn this away game into an event"
            body = (
                f"The Brewers are on the road at {opponent}, but that doesn't mean you can't make it a night. "
                f"Gather around {interests} at your favorite spot and cheer the team on {game_date} at {game_time}."
            )
    elif segment == "Family":
        if is_home:
            subject = f"A simple family outing at the ballpark"
            preheader = f"Plan an easy Brewers memory together on {game_date}."
            headline = f"Bring the family to the ballpark"
            body = (
                f"If you are looking for an easy outing, a Brewers home game is a great fit. "
                f"Fans like you value {attendance} and {interests}, making this game against {opponent} a great pick for {game_date}."
            )
        else:
            subject = f"Family watch day: Brewers at {opponent}"
            preheader = f"Cheer on the Brewers together from home on {game_date}."
            headline = f"A family watch day for the Brewers road game"
            body = (
                f"The Brewers are away at {opponent}, but it's still a great excuse to gather the family. "
                f"With your interest in {interests}, tune in together on {game_date} at {game_time} and make it a fun one."
            )
    else:  # Social
        if is_home:
            subject = f"Grab your crew and head to the Brewers game"
            preheader = f"Turn {game_date} into a social plan with friends, food, and game-day energy."
            headline = f"Game-day plans start with Brewers tickets"
            body = (
                f"This home matchup with {opponent} is a chance to make a plan, not just watch a game. "
                f"Think {interests}, lively energy, and a reason to get everyone together for {game_date} at {game_time}."
            )
        else:
            subject = f"Brewers at {opponent} — rally the crew for watch day"
            preheader = f"The Crew is on the road {game_date}. Make it a group thing."
            headline = f"Watch the Brewers road game with your crew"
            body = (
                f"The Brewers are heading to {opponent}, and that's still a reason to rally the group. "
                f"Think {interests}, your go-to spot, and a reason to get everyone together on {game_date} at {game_time}."
            )

    if extra_notes.strip():
        body += f" Campaign note: {extra_notes.strip()}"

    return {
        "segment": segment,
        "segment_persona": SEGMENT_LABELS[segment],
        "subject_line": subject,
        "preheader": preheader,
        "headline": headline,
        "body_copy": body,
        "cta": g["cta"] if is_home else f"Listen in — {broadcast_info}" if broadcast_info else "Tune in on game day",
        "image_concept": g["image"],
        "rationale": f"Rule-based POC using game context plus top segment traits ({interests}; {attendance}).",
    }



def build_crm_export(fan_df: pd.DataFrame, selected_segment: str, creative: dict, game_row: pd.Series) -> pd.DataFrame:
    if selected_segment in fan_df["Segment"].unique():
        audience = fan_df[fan_df["Segment"] == selected_segment].copy()
    else:
        audience = fan_df.iloc[0:0].copy()

    export = pd.DataFrame({
        "Fan_ID": audience.get("Fan_ID", pd.Series(dtype="int64")),
        "Segment": selected_segment,
        "Segment_Persona": SEGMENT_LABELS[selected_segment],
        "Game_Date": game_row.get("GAME_DATE_DISPLAY", ""),
        "Opponent": game_row.get("OPPONENT", ""),
        "Creative_Subject_Line": creative["subject_line"],
        "Creative_Headline": creative["headline"],
        "Creative_CTA": creative["cta"],
        "Creative_Image_Concept": creative["image_concept"],
        "Creative_Version_ID": f"{selected_segment.lower().replace('&', 'and').replace('-', '')}_{game_row.get('GAME_DATE_DISPLAY', '')}",
    })
    return export


def load_llm_creative(game_date: str, segment: str) -> dict | None:
    """Load pre-generated LLM creative from batch results JSON file.
    
    The batch script (generate_creative.py) creates these files.
    Returns the LLM creative dict if file exists, else None.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{segment}_{game_date}.json"
    filepath = RESULTS_DIR / filename
    
    if not filepath.exists():
        return None
    
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
        return data.get("llm")  # Return LLM creative if it exists
    except Exception as e:
        st.error(f"Error loading creative: {e}")
        return None


def run_batch_generation(segment: str, game_date: str, use_llm: bool = True):
    """Run the batch generation script for a specific game and segment."""
    try:
        cmd = [
            sys.executable,
            "generate_creative.py",
            "--segment", segment,
            "--game", game_date,
        ]
        if use_llm:
            cmd.append("--use-llm")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "Ollama service is not running" in stderr:
                st.error("Ollama is not running. Start it with `ollama serve` in a terminal, then try again.")
            elif "Model" in stderr and "not found" in stderr:
                st.error("Ollama model not found. Pull it with `ollama pull mistral`, then try again.")
            else:
                st.error(f"Generation failed: {stderr.splitlines()[-1] if stderr else 'Unknown error'}")
            return False
        
        # Check if LLM creative was actually produced
        if use_llm:
            results_path = Path("results") / f"{segment}_{game_date}.json"
            if not results_path.exists():
                st.warning("⚠️ Generation completed but no results file was created. Check that Ollama is running.")
                return False
            with open(results_path, "r") as f:
                data = json.load(f)
            if data.get("llm") is None:
                st.warning("⚠️ Generation completed but LLM creative was not produced. Check that Ollama is running.")
                return False
        
        st.success("✅ Creative generated successfully!")
        return True
    except subprocess.TimeoutExpired:
        st.error("Generation timed out (took more than 2 minutes)")
        return False
    except Exception as e:
        st.error(f"Error running batch generation: {e}")
        return False



schedule_df = load_schedule(SCHEDULE_PATH)
fan_df = load_fans(FAN_PATH)

st.title("Milwaukee Brewers Tailored Marketing Engine")
st.caption("POC Streamlit app for segment-based email creative generation and CRM export.")

with st.sidebar:
    st.header("POC Settings")
    selected_segment = st.selectbox(
        "Target segment",
        options=["Die-hard", "F&B", "Family", "Social"],
        format_func=lambda x: f"{SEGMENT_LABELS[x]} ({x})",
    )
    selected_game_label = st.selectbox("Select upcoming game", options=schedule_df["GAME_LABEL"].tolist())
    selected_game = schedule_df[schedule_df["GAME_LABEL"] == selected_game_label].iloc[0]
    # Move generation mode radio here, right after game selection
    generation_mode = st.radio(
        "Generation mode",
        options=["Segment-level", "Customer-level"],
        help="Segment-level: One creative for all customers in segment. Customer-level: Personalized per customer (beta)."
    )
    custom_note = st.text_area("Optional campaign note", placeholder="Weekend energy, rivalry angle, giveaway note, etc.")
    show_data_preview = st.checkbox("Show uploaded data preview", value=False)
    st.divider()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Game date", selected_game["GAME_DATE_DISPLAY"])
col2.metric("Opponent", selected_game["OPPONENT"])
col3.metric("Game time", str(selected_game["GAME_TIME_DISPLAY"]))
col4.metric("Home/Away", selected_game["HOME_AWAY"])

segment_summary = build_segment_summary(fan_df, selected_segment)
creative = build_rule_based_output(selected_game, selected_segment, segment_summary, custom_note)
crm_export = build_crm_export(fan_df, selected_segment, creative, selected_game)

# Track current selection and reload LLM creative when game/segment changes
current_key = f"{selected_segment}_{selected_game['GAME_DATE_DISPLAY']}"
if st.session_state.get("_llm_selection_key") != current_key:
    st.session_state._llm_selection_key = current_key
    st.session_state.llm_creative = load_llm_creative(selected_game["GAME_DATE_DISPLAY"], selected_segment)

if "show_full_export" not in st.session_state:
    st.session_state.show_full_export = False


st.subheader("Segment summary")
if segment_summary["sample_size"] == 0:
    st.warning("This segment is not present in the uploaded fan file. The POC uses a manual fallback definition for this persona.")
else:
    n = segment_summary['sample_size']
    st.markdown(f"**{selected_segment}** — {n} fans in segment")
    st.caption(f"Percentages represent share of the {n} fans in the {selected_segment} segment.")

    def _format_breakdown(table_dict):
        if not table_dict:
            return "—"
        return "<br>".join(f"• {k}: {v}" for k, v in table_dict.items())

    summary_rows = [
        ("Attendance Patterns", _format_breakdown(segment_summary.get("attendance_table", {}))),
        ("Email Engagement", _format_breakdown(segment_summary.get("email_table", {}))),
        ("Top Interests", _format_breakdown(segment_summary.get("interests_table", {}))),
        ("Behavioral Notes", _format_breakdown(segment_summary.get("notes_table", {}))),
    ]
    md = "| Category | Breakdown |\n|---|---|\n"
    for cat, bd in summary_rows:
        md += f"| **{cat}** | {bd} |\n"
    st.markdown(md, unsafe_allow_html=True)

st.subheader("Generated creative")

# Button to generate/fetch LLM creative
col_button, col_info = st.columns([1, 3])
with col_button:
    if generation_mode == "Segment-level":
        if st.button("✨ Generate AI Creative", key="generate_llm"):
            with st.spinner("Running batch generation..."):
                if run_batch_generation(selected_segment, selected_game["GAME_DATE_DISPLAY"], use_llm=True):
                    # Reload creative
                    llm_result = load_llm_creative(selected_game["GAME_DATE_DISPLAY"], selected_segment)
                    if llm_result:
                        st.session_state.llm_creative = llm_result
                        st.rerun()
    else:
        st.button("✨ Generate AI Creative (Beta)", key="generate_llm", disabled=True)

with col_info:
    if generation_mode == "Segment-level":
        st.caption("Generates one creative for all customers in this segment")
    else:
        st.caption("⏳ Customer-level personalization coming soon")

# Display rule-based and LLM versions side-by-side
if st.session_state.llm_creative:
    col_rb, col_llm = st.columns([1, 1])
    
    with col_rb:
        st.write("**Rule-Based Output**")
        st.markdown(f"**Subject line:** {creative['subject_line']}")
        st.markdown(f"**Preheader:** {creative['preheader']}")
        st.markdown(f"**Headline:** {creative['headline']}")
        st.markdown(f"**Body copy:**\n\n{creative['body_copy']}")
        st.markdown(f"**CTA:** {creative['cta']}")
        st.markdown(f"**Image concept:**\n\n{creative['image_concept']}")
        st.caption("Generated from segment rules and game context")
    
    with col_llm:
        st.write("**LLM Generated**")
        st.markdown(f"**Subject line:** {st.session_state.llm_creative.get('subject_line', '')}")
        st.markdown(f"**Preheader:** {st.session_state.llm_creative.get('preheader', '')}")
        st.markdown(f"**Headline:** {st.session_state.llm_creative.get('headline', '')}")
        st.markdown(f"**Body copy:**\n\n{st.session_state.llm_creative.get('body_copy', '')}")
        st.markdown(f"**CTA:** {st.session_state.llm_creative.get('cta', '')}")
        st.markdown(f"**Image concept:**\n\n{st.session_state.llm_creative.get('image_concept', '')}")
        st.caption("Generated by batch script using Ollama")
else:
    st.write("**Rule-Based Output** (Click button above to generate AI version)")
    st.markdown(f"**Subject line:** {creative['subject_line']}")
    st.markdown(f"**Preheader:** {creative['preheader']}")
    st.markdown(f"**Headline:** {creative['headline']}")
    st.markdown(f"**Body copy:**\n\n{creative['body_copy']}")
    st.markdown(f"**CTA:** {creative['cta']}")
    st.markdown(f"**Image concept:**\n\n{creative['image_concept']}")
    st.caption(creative["rationale"])


st.divider()
st.subheader("CRM-ready export preview")

if crm_export.empty:
    st.info("No customers in this segment. CRM export is empty.")
else:
    # Prepare fallback export (with rule-based creative)
    fallback_export = crm_export.copy()
    
    # Prepare LLM export if creative was generated
    llm_export = None
    if st.session_state.llm_creative:
        llm_export = crm_export.copy()
        llm_export["Creative_Subject_Line"] = st.session_state.llm_creative.get("subject_line", "")
        llm_export["Creative_Headline"] = st.session_state.llm_creative.get("headline", "")
        llm_export["Creative_CTA"] = st.session_state.llm_creative.get("cta", "")
        llm_export["Creative_Image_Concept"] = st.session_state.llm_creative.get("image_concept", "")
    
    st.write(f"**Example Preview: All {len(fallback_export)} Customers (Rule-Based Creative)**")
    st.dataframe(fallback_export, use_container_width=True, hide_index=True)
    
    # Button to generate for all with LLM
    col_gen, col_space = st.columns([2, 3])
    with col_gen:
        if st.button(f"🚀 Generate for All ({len(crm_export)} customers) with LLM", key="generate_for_all"):
            with st.spinner("Running batch generation for all..."):
                if run_batch_generation(selected_segment, selected_game["GAME_DATE_DISPLAY"], use_llm=True):
                    # Reload creative and trigger UI update
                    llm_result = load_llm_creative(selected_game["GAME_DATE_DISPLAY"], selected_segment)
                    if llm_result:
                        st.session_state.llm_creative = llm_result
                        st.session_state.show_full_export = True
                        st.rerun()
    
    st.divider()
    
    # Show comparison if LLM creative was generated
    if llm_export is not None and st.session_state.show_full_export:
        col_fb, col_llm = st.columns([1, 1])
        
        with col_fb:
            st.write(f"**Fallback (Rule-Based): {len(fallback_export)} customers**")
            st.dataframe(fallback_export, use_container_width=True, hide_index=True)
            fb_csv = fallback_export.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Download Fallback Export",
                data=fb_csv,
                file_name=f"brewers_campaign_fallback_{selected_segment.lower().replace('&', 'and')}_{selected_game['GAME_DATE_DISPLAY']}.csv",
                mime="text/csv",
            )
        
        with col_llm:
            st.write(f"**LLM Generated: {len(llm_export)} customers**")
            st.dataframe(llm_export, use_container_width=True, hide_index=True)
            llm_csv = llm_export.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Download LLM Export",
                data=llm_csv,
                file_name=f"brewers_campaign_llm_{selected_segment.lower().replace('&', 'and')}_{selected_game['GAME_DATE_DISPLAY']}.csv",
                mime="text/csv",
                type="primary"
            )
    elif st.session_state.show_full_export and not st.session_state.llm_creative:
        st.warning("Waiting for AI creative generation to complete. Check back in a moment.")


st.divider()
st.subheader("What this POC demonstrates")
st.markdown(
    """
- Business user selects a game and target audience segment.
- App combines schedule data with fan-segment traits.
- System generates differentiated email copy and an image concept.
- App outputs a simple CSV structure for CRM upload / downstream activation.
- A later version can swap the rule-based creative block for an LLM call while keeping the same UI and export pattern.
"""
)

if show_data_preview:
    st.divider()
    st.subheader("Uploaded data preview")
    t1, t2 = st.tabs(["Fan data", "Schedule data"])
    with t1:
        st.dataframe(fan_df.head(25), use_container_width=True)
    with t2:
        st.dataframe(schedule_df.head(25), use_container_width=True)
