import json
import logging
import re
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

from ollama_service import OllamaService

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
RESULTS_DIR = PROJECT_ROOT / "results"
PROMPTS_DIR = PROJECT_ROOT / "prompts"

SEGMENT_LABELS = {
    "Die-hard": "Die-Hard Danny",
    "F&B": "Foodie Frank",
    "Family": "Parent Patty",
    "Social": "Tailgate Tammy",
}


def _load_segment_guidance() -> dict:
    """Load segment guidance from prompts/segment_guidance.yml."""
    with open(PROMPTS_DIR / "segment_guidance.yml", "r") as f:
        return yaml.safe_load(f)


SEGMENT_GUIDANCE = _load_segment_guidance()


SEGMENT_RULES_FILES = {
    "Die-hard": "rules_die-hard.txt",
    "F&B": "rules_fb.txt",
    "Family": "rules_family.txt",
    "Social": "rules_social.txt",
}

NL_DIVISION = {"Cubs", "Cardinals", "Reds", "Pirates"}


def _load_segment_rules(segment: str) -> str:
    """Load segment-specific prompt rules from prompts/ directory."""
    filename = SEGMENT_RULES_FILES.get(segment)
    if not filename:
        return ""
    rules_path = PROMPTS_DIR / filename
    if rules_path.exists():
        return rules_path.read_text().strip()
    return ""


def _build_game_context(game_row: pd.Series, is_home: bool) -> str:
    """Build dynamic game context lines based on game attributes."""
    lines = []
    opponent = game_row.get("OPPONENT", "")
    game_time = str(game_row.get("GAME_TIME_DISPLAY", ""))

    # Day vs night
    if "PM" in game_time:
        try:
            hour = int(game_time.split(":")[0])
            if 5 <= hour <= 11:
                lines.append("TIMING: Evening game — lean into night-out energy.")
            else:
                lines.append("TIMING: Afternoon game — relaxed, daytime feel.")
        except ValueError:
            lines.append("TIMING: Afternoon game.")
    else:
        lines.append("TIMING: Afternoon game — relaxed, daytime feel.")

    # Day of week
    start_date = game_row.get("START DATE")
    if pd.notna(start_date):
        day_name = pd.Timestamp(start_date).day_name()
        if day_name in ("Saturday", "Sunday"):
            lines.append(f"DAY: {day_name} — weekend game, great for plans with friends/family.")
        elif day_name == "Friday":
            lines.append(f"DAY: {day_name} — Friday night energy, kickoff to the weekend.")
        else:
            lines.append(f"DAY: {day_name} — weeknight game, emphasize ease and convenience.")

    # Rivalry
    if opponent in NL_DIVISION:
        lines.append(f"RIVALRY: NL Central divisional matchup vs {opponent} — high stakes, extra intensity.")

    # Broadcast info for away games
    if not is_home:
        broadcast = str(game_row.get("DESCRIPTION", "")).strip()
        if broadcast:
            lines.append(f"BROADCAST: {broadcast}")

    return "\n".join(lines)


def load_config() -> dict:
    with open(PROJECT_ROOT / "config.yml", "r") as f:
        return yaml.safe_load(f)


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


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    config = load_config()
    schedule_path = PROJECT_ROOT / config["app"]["schedule_csv"]
    fan_path = PROJECT_ROOT / config["app"]["fan_csv"]

    schedule_df = pd.read_csv(schedule_path).copy()
    schedule_df["START DATE"] = pd.to_datetime(schedule_df["START DATE"], format="%m/%d/%y", errors="coerce")
    schedule_df["GAME_DATE_DISPLAY"] = schedule_df["START DATE"].dt.strftime("%Y-%m-%d")
    schedule_df["GAME_TIME_DISPLAY"] = schedule_df["START TIME"].astype(str)

    parsed = schedule_df["SUBJECT"].apply(parse_subject)
    schedule_df["OPPONENT"] = parsed.apply(lambda x: x["opponent"])
    schedule_df["HOME_AWAY"] = parsed.apply(lambda x: x["home_away"])
    schedule_df["GAME_LABEL"] = (
        schedule_df["GAME_DATE_DISPLAY"].fillna("Unknown Date")
        + " | "
        + schedule_df["OPPONENT"].fillna("Unknown")
        + " | "
        + schedule_df["GAME_TIME_DISPLAY"].fillna("Unknown Time")
    )
    schedule_df = schedule_df.sort_values(["START DATE", "GAME_TIME_DISPLAY", "SUBJECT"]).reset_index(drop=True)

    fan_df = pd.read_csv(fan_path).copy()
    if "Segment" in fan_df.columns:
        fan_df["Segment"] = fan_df["Segment"].replace({"Die hard": "Die-hard", "Food": "F&B"})

    return schedule_df, fan_df


def build_segment_summary(fan_df: pd.DataFrame, segment: str) -> dict:
    seg_df = fan_df[fan_df["Segment"] == segment].copy() if segment in fan_df["Segment"].unique() else pd.DataFrame()
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


def _friendly_date(game_row: pd.Series) -> str:
    """Format game date as 'Tuesday, 17 March' from START DATE or GAME_DATE_DISPLAY."""
    start_date = game_row.get("START DATE")
    if pd.notna(start_date):
        ts = pd.Timestamp(start_date)
        return ts.strftime("%A, %-d %B")
    return game_row.get("GAME_DATE_DISPLAY", "")


def build_rule_based_creative(game_row: pd.Series, segment: str, summary: dict, extra_notes: str = "") -> dict:
    g = SEGMENT_GUIDANCE[segment]
    game_date = _friendly_date(game_row)
    opponent = game_row.get("OPPONENT", "")
    game_time = game_row.get("GAME_TIME_DISPLAY", "")
    home_away = game_row.get("HOME_AWAY", "Home")
    is_home = home_away == "Home"
    daypart = "tonight" if "PM" in str(game_time) else "this game"
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
                f"With interest around {interests}, now is a great time to lock in a home game ticket for {game_date} at {game_time}."
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
            subject = "Your next Brewers night out starts here"
            preheader = f"Great game, great eats, and a ballpark experience worth planning for {game_date}."
            headline = "Make the Brewers game your next night out"
            body = (
                f"From {interests} to the full stadium atmosphere, this home matchup with {opponent} is more than the game itself. "
                f"Grab a home game ticket and turn {game_date} into an easy outing built around the full ballpark experience."
            )
        else:
            subject = "Brewers road game watch party — eat, drink, cheer"
            preheader = f"The Crew is at {opponent} on {game_date}. Make it a watch party."
            headline = "Turn this away game into an event"
            body = (
                f"The Brewers are on the road at {opponent}, but that doesn't mean you can't make it a night. "
                f"Gather around {interests} at your favorite spot and cheer the team on {game_date} at {game_time}."
            )
    elif segment == "Family":
        if is_home:
            subject = "A simple family outing at the ballpark"
            preheader = f"Plan an easy Brewers memory together on {game_date}."
            headline = "Bring the family to the ballpark"
            body = (
                f"If you are looking for an easy outing, a Brewers home game is a great fit. "
                f"Fans like you value {attendance} and {interests}, making this game against {opponent} a great pick for {game_date}."
            )
        else:
            subject = f"Family watch day: Brewers at {opponent}"
            preheader = f"Cheer on the Brewers together from home on {game_date}."
            headline = "A family watch day for the Brewers road game"
            body = (
                f"The Brewers are away at {opponent}, but it's still a great excuse to gather the family. "
                f"With your interest in {interests}, tune in together on {game_date} at {game_time} and make it a fun one."
            )
    else:
        if is_home:
            subject = "Grab your crew and head to the Brewers game"
            preheader = f"Turn {game_date} into a social plan with friends, food, and game-day energy."
            headline = "Game-day plans start with Brewers tickets"
            body = (
                f"This home matchup with {opponent} is a chance to make a plan, not just watch a game. "
                f"Think {interests}, lively energy, and a reason to get everyone together for {game_date} at {game_time}."
            )
        else:
            subject = f"Brewers at {opponent} — rally the crew for watch day"
            preheader = f"The Crew is on the road {game_date}. Make it a group thing."
            headline = "Watch the Brewers road game with your crew"
            body = (
                f"The Brewers are heading to {opponent}, and that's still a reason to rally the group. "
                f"Think {interests}, your go-to spot, and a reason to get everyone together on {game_date} at {game_time}."
            )

    return {
        "type": "rule-based",
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


def _build_fan_profile(fan_row: pd.Series) -> str:
    """Build a single-fan profile string for prompt injection."""
    return (
        f"PRIMARY TARGET (use this as your main data source, segment data is background context only):\n"
        f"Fan #{int(fan_row.get('Fan_ID', 0))} — "
        f"attendance: {fan_row.get('Attendance_Behavior', 'Unknown')}, "
        f"email engagement: {fan_row.get('Email_Engagement', 'Unknown')}, "
        f"interest: {fan_row.get('Interests', 'Unknown')}, "
        f"notes: {fan_row.get('Notes', 'None')}"
    )


def build_llm_creative(
    game_row: pd.Series,
    segment: str,
    summary: dict,
    ollama_service: OllamaService,
    rule_based: Optional[dict] = None,
    fan_row: Optional[pd.Series] = None,
    extra_notes: str = "",
) -> Optional[dict]:
    g = SEGMENT_GUIDANCE[segment]
    attendance_dist = summary.get("attendance_distribution", "") or "Unknown"
    email_dist = summary.get("email_engagement_distribution", "") or "Unknown"
    interests_dist = summary.get("interests_distribution", "") or "Unknown"
    home_away = game_row.get("HOME_AWAY", "Home")
    is_home = home_away == "Home"
    broadcast_info = str(game_row.get("DESCRIPTION", "")).strip()

    rule_brief = ""
    if rule_based:
        rule_brief = f"""DRAFT TO ELEVATE:
- Subject: {rule_based.get('subject_line', '')}
- Headline: {rule_based.get('headline', '')}
- Body: {rule_based.get('body_copy', '')}
- CTA: {rule_based.get('cta', '')}
- Image: {rule_based.get('image_concept', '')}
Keep the intent but make it sharper, more personal, and more compelling.
"""

    venue_line = (
        "HOME game at American Family Field. Fan attends in person."
        if is_home else
        f"AWAY game at {game_row.get('OPPONENT', '')}. Fan watches remotely. Broadcast: {broadcast_info or 'Check local listings'}. Do NOT mention buying tickets."
    )

    prompt_template = (PROMPTS_DIR / "creative_email.txt").read_text()
    prompt = prompt_template.format(
        opponent=game_row.get("OPPONENT", ""),
        vs_at="vs" if is_home else "at",
        game_date=_friendly_date(game_row),
        game_time=game_row.get("GAME_TIME_DISPLAY", ""),
        venue_line=venue_line,
        game_context=_build_game_context(game_row, is_home),
        tone=g["tone"],
        hooks=", ".join(g["hooks"]),
        interests_dist=interests_dist,
        attendance_dist=attendance_dist,
        email_dist=email_dist,
        segment_rules=_load_segment_rules(segment),
        rule_brief=rule_brief,
        fan_profile=_build_fan_profile(fan_row) if fan_row is not None else "",
        campaign_note=f"CAMPAIGN NOTE (secondary priority — use to flavor the output, but fan data comes first): {extra_notes.strip()}\n" if extra_notes.strip() else "",
    )

    config = load_config()
    success, result = ollama_service.generate_json(prompt, timeout=config.get("ollama", {}).get("timeout", 60))
    if success and result:
        result["type"] = "llm"
        result["segment"] = segment
        result["segment_persona"] = SEGMENT_LABELS[segment]
        return result
    logger.warning("LLM creative generation failed for segment=%s game=%s (success=%s)",
                    segment, game_row.get("GAME_DATE_DISPLAY", "?"), success)
    return None


def generate_for_game_segment(
    schedule_df: pd.DataFrame,
    fan_df: pd.DataFrame,
    game_date: str,
    segment: str,
    use_llm: bool = False,
    ollama_service: Optional[OllamaService] = None,
    extra_notes: str = "",
    fan_row: Optional[pd.Series] = None,
) -> dict:
    game_rows = schedule_df[schedule_df["GAME_DATE_DISPLAY"] == game_date]
    if game_rows.empty:
        return {"error": "Game not found"}

    game_row = game_rows.iloc[0]
    summary = build_segment_summary(fan_df, segment)
    rule_based = build_rule_based_creative(game_row, segment, summary, extra_notes=extra_notes)
    llm_creative = None
    if use_llm and ollama_service:
        llm_creative = build_llm_creative(game_row, segment, summary, ollama_service, rule_based, fan_row=fan_row, extra_notes=extra_notes)

    return {
        "game_date": game_date,
        "opponent": game_row.get("OPPONENT", ""),
        "segment": segment,
        "segment_persona": SEGMENT_LABELS.get(segment, segment),
        "rule_based": rule_based,
        "llm": llm_creative,
        "summary": summary,
    }


def build_crm_export(fan_df: pd.DataFrame, selected_segment: str, creative: dict, game_row: pd.Series) -> pd.DataFrame:
    if selected_segment in fan_df["Segment"].unique():
        audience = fan_df[fan_df["Segment"] == selected_segment].copy()
    else:
        audience = fan_df.iloc[0:0].copy()

    return pd.DataFrame({
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


def save_results(results: dict, game_date: str, segment: str) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = RESULTS_DIR / f"{segment}_{game_date}.json"
    with open(filepath, "w") as f:
        json.dump(results, f, indent=2)
    return filepath


def build_ollama_service() -> OllamaService:
    ollama_config = load_config().get("ollama", {})
    return OllamaService(
        base_url=ollama_config.get("base_url", "http://localhost:11434"),
        model=ollama_config.get("model", "mistral"),
    )