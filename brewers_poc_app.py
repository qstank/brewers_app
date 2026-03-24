from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Brewers Tailored Marketing Engine POC", layout="wide")

SCHEDULE_PATH = Path("GameTicketPromotionPrice.csv")
FAN_PATH = Path("brewers mock fan data.csv")

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
        + df["SUBJECT"].fillna("Unknown Matchup")
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
            "email_engagement": "Unknown",
            "interests": [],
            "notes": [],
        }

    return {
        "segment": segment,
        "sample_size": len(seg_df),
        "attendance_behavior": seg_df["Attendance_Behavior"].dropna().astype(str).value_counts().head(3).index.tolist(),
        "email_engagement": seg_df["Email_Engagement"].dropna().astype(str).value_counts().idxmax(),
        "interests": seg_df["Interests"].dropna().astype(str).value_counts().head(3).index.tolist(),
        "notes": seg_df["Notes"].dropna().astype(str).value_counts().head(3).index.tolist(),
    }



def build_rule_based_output(game_row: pd.Series, segment: str, summary: dict, extra_notes: str = "") -> dict:
    g = SEGMENT_GUIDANCE[segment]
    game_date = game_row.get("GAME_DATE_DISPLAY", "")
    opponent = game_row.get("OPPONENT", "")
    game_time = game_row.get("GAME_TIME_DISPLAY", "")
    daypart = "tonight" if "PM" in str(game_time) else "this game"

    interests = ", ".join(summary.get("interests", [])[:2]) or "game-day moments"
    attendance = ", ".join(summary.get("attendance_behavior", [])[:2]) or "live games"

    if segment == "Die-hard":
        subject = f"{opponent} vs. Brewers: be there {daypart}"
        preheader = f"For fans who follow every matchup, this is one to catch live on {game_date}."
        headline = f"Catch the matchup live against {opponent}"
        body = (
            f"You follow the details, and this game gives you a reason to be in the ballpark. "
            f"With interest around {interests}, now is a great time to lock in an individual ticket for {game_date} at {game_time}."
        )
    elif segment == "F&B":
        subject = f"Your next Brewers night out starts here"
        preheader = f"Great game, great eats, and a ballpark experience worth planning for {game_date}."
        headline = f"Make the Brewers game your next night out"
        body = (
            f"From {interests} to the full stadium atmosphere, this matchup with {opponent} is more than the game itself. "
            f"Grab an individual ticket and turn {game_date} into an easy outing built around the full ballpark experience."
        )
    elif segment == "Family":
        subject = f"A simple family outing at the ballpark"
        preheader = f"Plan an easy Brewers memory together on {game_date}."
        headline = f"Bring the family to the ballpark"
        body = (
            f"If you are looking for an easy outing, Brewers game day is a strong fit. "
            f"Fans like this segment often value {attendance} and {interests}, making this game against {opponent} a great pick for {game_date}."
        )
    else:
        subject = f"Grab your crew and head to the Brewers game"
        preheader = f"Turn {game_date} into a social plan with friends, food, and game-day energy."
        headline = f"Game-day plans start with Brewers tickets"
        body = (
            f"This matchup with {opponent} is a chance to make a plan, not just watch a game. "
            f"Think {interests}, lively energy, and a reason to get everyone together for {game_date} at {game_time}."
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
        "cta": g["cta"],
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
    custom_note = st.text_area("Optional campaign note", placeholder="Weekend energy, rivalry angle, giveaway note, etc.")
    show_data_preview = st.checkbox("Show uploaded data preview", value=False)

selected_game_label = st.selectbox("Select upcoming game", options=schedule_df["GAME_LABEL"].tolist())
selected_game = schedule_df[schedule_df["GAME_LABEL"] == selected_game_label].iloc[0]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Game date", selected_game["GAME_DATE_DISPLAY"])
col2.metric("Opponent", selected_game["OPPONENT"])
col3.metric("Game time", str(selected_game["GAME_TIME_DISPLAY"]))
col4.metric("Home/Away", selected_game["HOME_AWAY"])

segment_summary = build_segment_summary(fan_df, selected_segment)
creative = build_rule_based_output(selected_game, selected_segment, segment_summary, custom_note)
crm_export = build_crm_export(fan_df, selected_segment, creative, selected_game)

left, right = st.columns([1, 1])

with left:
    st.subheader("Segment summary")
    if segment_summary["sample_size"] == 0:
        st.warning("This segment is not present in the uploaded fan file. The POC uses a manual fallback definition for this persona.")
    st.json(segment_summary)

    st.subheader("Generated creative")
    st.text_input("Subject line", value=creative["subject_line"], disabled=True)
    st.text_input("Preheader", value=creative["preheader"], disabled=True)
    st.text_input("Headline", value=creative["headline"], disabled=True)
    st.text_area("Body copy", value=creative["body_copy"], height=170, disabled=True)
    st.text_input("CTA", value=creative["cta"], disabled=True)
    st.text_area("Image concept", value=creative["image_concept"], height=120, disabled=True)
    st.caption(creative["rationale"])

with right:
    st.subheader("CRM-ready export preview")
    if crm_export.empty:
        st.info("No rows to export for this segment because the uploaded fan data does not contain that segment. This still demonstrates the file structure for CRM handoff.")
    st.dataframe(crm_export.head(25), use_container_width=True)

    csv_bytes = crm_export.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download CRM export CSV",
        data=csv_bytes,
        file_name=f"brewers_campaign_export_{selected_segment.lower().replace('&', 'and')}_{selected_game['GAME_DATE_DISPLAY']}.csv",
        mime="text/csv",
    )

    prompt_payload = {
        "game": {
            "date": selected_game["GAME_DATE_DISPLAY"],
            "opponent": selected_game["OPPONENT"],
            "time": selected_game["GAME_TIME_DISPLAY"],
            "home_away": selected_game["HOME_AWAY"],
            "location": selected_game["LOCATION"],
        },
        "segment": selected_segment,
        "segment_persona": SEGMENT_LABELS[selected_segment],
        "segment_summary": segment_summary,
        "custom_note": custom_note,
        "poc_output": creative,
    }
    st.subheader("LLM handoff payload (optional next step)")
    st.code(json.dumps(prompt_payload, indent=2), language="json")

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
