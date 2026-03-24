"""Batch script to generate marketing creative for Brewers POC.

Usage:
    python generate_creative.py --segment "Die-hard" --game "2026-02-21" --use-llm
    python generate_creative.py --limit 10 --use-llm  # random 10 combinations
    python generate_creative.py --limit 20 --use-llm --workers 5  # 20 combos with 5 parallel workers
    python generate_creative.py --use-llm  # all combinations
"""

import argparse
import json
import logging
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

from ollama_service import OllamaService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = PROJECT_ROOT / "results"

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


def load_config() -> dict:
    """Load configuration from YAML file."""
    config_file = Path(__file__).parent / "config.yml"
    with open(config_file, "r") as f:
        return yaml.safe_load(f)


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load schedule and fan data."""
    config = load_config()
    schedule_path = PROJECT_ROOT / config["app"]["schedule_csv"]
    fan_path = PROJECT_ROOT / config["app"]["fan_csv"]
    
    # Load schedule
    schedule_df = pd.read_csv(schedule_path).copy()
    schedule_df["START DATE"] = pd.to_datetime(schedule_df["START DATE"], format="%m/%d/%y", errors="coerce")
    schedule_df["GAME_DATE_DISPLAY"] = schedule_df["START DATE"].dt.strftime("%Y-%m-%d")
    schedule_df["GAME_TIME_DISPLAY"] = schedule_df["START TIME"].astype(str)
    
    parsed = schedule_df["SUBJECT"].apply(parse_subject)
    schedule_df["OPPONENT"] = parsed.apply(lambda x: x["opponent"])
    schedule_df["HOME_AWAY"] = parsed.apply(lambda x: x["home_away"])
    
    # Load fans
    fan_df = pd.read_csv(fan_path).copy()
    if "Segment" in fan_df.columns:
        fan_df["Segment"] = fan_df["Segment"].replace({"Die hard": "Die-hard", "Food": "F&B"})
    
    return schedule_df, fan_df


def parse_subject(subject: str) -> dict:
    """Parse game subject to extract opponent and home/away."""
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


def build_segment_summary(fan_df: pd.DataFrame, segment: str) -> dict:
    """Build aggregated summary of segment characteristics with distributions."""
    seg_df = fan_df[fan_df["Segment"] == segment].copy() if segment in fan_df["Segment"].unique() else pd.DataFrame()
    
    if seg_df.empty:
        return {
            "segment": segment,
            "sample_size": 0,
            "attendance_behavior": [],
            "attendance_distribution": "",
            "email_engagement": "Unknown",
            "email_engagement_distribution": "",
            "interests": [],
            "interests_distribution": "",
            "notes": [],
            "notes_distribution": "",
        }
    
    n = len(seg_df)
    
    def top_with_pct(series, top_n=5):
        """Return top values with percentage of segment."""
        counts = series.dropna().astype(str).value_counts().head(top_n)
        return [f"{val} ({count}/{n}, {count*100//n}%)" for val, count in counts.items()]
    
    attendance_counts = seg_df["Attendance_Behavior"].dropna().astype(str).value_counts().head(5)
    email_counts = seg_df["Email_Engagement"].dropna().astype(str).value_counts()
    interest_counts = seg_df["Interests"].dropna().astype(str).value_counts().head(5)
    note_counts = seg_df["Notes"].dropna().astype(str).value_counts().head(5)
    
    return {
        "segment": segment,
        "sample_size": n,
        "attendance_behavior": attendance_counts.index.tolist(),
        "attendance_distribution": "; ".join(top_with_pct(seg_df["Attendance_Behavior"])),
        "email_engagement": email_counts.idxmax(),
        "email_engagement_distribution": "; ".join(top_with_pct(seg_df["Email_Engagement"])),
        "interests": interest_counts.index.tolist(),
        "interests_distribution": "; ".join(top_with_pct(seg_df["Interests"])),
        "notes": note_counts.index.tolist(),
        "notes_distribution": "; ".join(top_with_pct(seg_df["Notes"])),
    }


def build_rule_based_creative(game_row: pd.Series, segment: str, summary: dict) -> dict:
    """Build rule-based creative."""
    g = SEGMENT_GUIDANCE[segment]
    game_date = game_row.get("GAME_DATE_DISPLAY", "")
    opponent = game_row.get("OPPONENT", "")
    game_time = game_row.get("GAME_TIME_DISPLAY", "")
    home_away = game_row.get("HOME_AWAY", "Home")
    is_home = home_away == "Home"
    daypart = "tonight" if "PM" in str(game_time) else "this game"
    
    ticket_phrase = "a home game ticket" if is_home else "away game tickets"
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
    
    return {
        "type": "rule-based",
        "segment": segment,
        "segment_persona": SEGMENT_LABELS[segment],
        "subject_line": subject,
        "preheader": preheader,
        "headline": headline,
        "body_copy": body,
        "cta": g["cta"] if is_home else f"Join us at {broadcast_info}" if broadcast_info else "Tune in on game day",
        "image_concept": g["image"],
        "rationale": f"Rule-based POC using game context plus top segment traits ({interests}; {attendance}).",
    }


def build_llm_creative(
    game_row: pd.Series,
    segment: str,
    summary: dict,
    ollama_service: OllamaService,
    rule_based: dict = None
) -> Optional[dict]:
    """Generate LLM-based creative using Ollama, informed by rule-based output."""
    g = SEGMENT_GUIDANCE[segment]
    sample_size = summary.get("sample_size", 0)
    
    # Aggregated segment distributions
    attendance_dist = summary.get("attendance_distribution", "") or "Unknown"
    email_dist = summary.get("email_engagement_distribution", "") or "Unknown"
    interests_dist = summary.get("interests_distribution", "") or "Unknown"
    notes_dist = summary.get("notes_distribution", "") or "None"
    
    # Top values for rule-based references
    interests = ", ".join(summary.get("interests", [])[:3]) or "game-day moments"
    attendance = ", ".join(summary.get("attendance_behavior", [])[:3]) or "live games"
    email_engagement = summary.get("email_engagement", "Unknown")
    notes = ", ".join(summary.get("notes", [])[:3]) or "none"
    
    home_away = game_row.get('HOME_AWAY', 'Home')
    is_home = home_away == "Home"
    broadcast_info = str(game_row.get("DESCRIPTION", "")).strip()
    venue_context = (
        "This is a HOME GAME at American Family Field. The fan can attend in person. "
        "Focus on the in-stadium experience: being in the stands, ballpark food, live atmosphere, buying tickets."
        if is_home else
        f"This is an AWAY GAME — the Brewers are traveling to {game_row.get('OPPONENT', '')}. "
        "The fan is NOT attending in person. Focus on watch parties, tuning in from home or a bar, "
        "following the team on the road, and group watch experiences. Do NOT mention buying tickets or being at the ballpark.\n"
        f"Broadcast info: {broadcast_info or 'Check local listings'}. "
        "The CTA should encourage listening/watching via the broadcast info provided."
    )

    # Build the rule-based brief section if available
    rule_brief = ""
    if rule_based:
        rule_brief = f"""RULE-BASED CREATIVE BRIEF (use as your starting point — refine and elevate this draft):
- Subject line: {rule_based.get('subject_line', '')}
- Preheader: {rule_based.get('preheader', '')}
- Headline: {rule_based.get('headline', '')}
- Body copy: {rule_based.get('body_copy', '')}
- CTA: {rule_based.get('cta', '')}
- Image concept: {rule_based.get('image_concept', '')}
- Rationale: {rule_based.get('rationale', '')}

INSTRUCTIONS FOR USING THE BRIEF:
- The rule-based draft above captures the correct audience tone, game context, and key selling points.
- Use it as a foundation: keep what works, but make the language more compelling, creative, and natural.
- Sharpen the subject line for higher open rates. Add urgency or curiosity where appropriate.
- Elevate the body copy — make it feel personal and written by a human, not templated.
- You may adjust the CTA wording for impact, but keep the same intent (buy tickets for home, tune in for away).
- The image concept should be more vivid and specific than the brief — describe a scene, not just a category.
"""

    prompt = f"""You are a creative strategist for the Milwaukee Brewers' marketing team.

Your job is to take a rule-based marketing draft and elevate it into polished, personalized email creative.

INTERNAL SEGMENT CONTEXT (for your reference only — do NOT use segment names, persona names, or segment labels in the output):
- Internal persona label: {SEGMENT_LABELS[segment]} ({segment})
- Tone to use: {g['tone']}
- Key hooks: {', '.join(g['hooks'])}

SEGMENT PROFILE (aggregated across {sample_size} fans in this segment — use these patterns to shape language and content):
- Attendance patterns: {attendance_dist}
- Email engagement levels: {email_dist}
- Top interests: {interests_dist}
- Behavioral notes & preferences: {notes_dist}

Read the segment profile above carefully. The percentages tell you what matters most to this audience as a whole. Lean into the dominant patterns and tailor language accordingly.

LANGUAGE & STYLE RULES (adapt based on the segment context above):
- If attendance behavior suggests season ticket holders or 15+ games: use insider language, assume they know the team well, reference matchups and roster. Keep it sharp and confident.
- If attendance behavior suggests casual or 2-3 games/year: keep language simple and inviting. Don't assume deep baseball knowledge. Focus on the experience, not the sport.
- If interests mention food, beer, or social atmosphere: lead with the experience around the game, not the game itself. Make it feel like a night out, not a sporting event.
- If interests mention family, ease of access, or kids: emphasize convenience, simplicity, and togetherness. Use warm, reassuring language. Mention things like parking, kid-friendly options.
- If email engagement is "Low": use a punchy, curiosity-driven subject line to earn the open. Keep body copy shorter and high-impact.
- If email engagement is "Very High": you can include more detail; these fans read the full email. Add specifics that reward engaged readers.
- If behavioral notes mention preferences (e.g. "Prefers night games", "Weekend preference"): weave those naturally into the copy when the game context matches.

GAME DETAILS:
- Date: {game_row.get('GAME_DATE_DISPLAY', '')}
- Opponent: {game_row.get('OPPONENT', '')}
- Time: {game_row.get('GAME_TIME_DISPLAY', '')}
- Home/Away: {home_away}

IMPORTANT CONTEXT:
{venue_context}

{rule_brief}RULES:
- Do NOT reference segment names, persona names (e.g. "Die-Hard Danny", "Foodie Frank"), or internal labels in any output field.
- Write as if speaking directly to the fan. Use "you" and "your" — never refer to them by a category or persona name.
- The creative MUST reflect whether this is a home or away game.
- Your output should be noticeably better than the rule-based brief — more engaging, more personal, more likely to drive action.

Generate a JSON response with these fields:
{{
  "subject_line": "Compelling subject line (max 60 chars)",
  "preheader": "Preheader text (max 100 chars)",
  "headline": "Email headline",
  "body_copy": "2-3 sentence body copy tailored to the fan's interests and home/away context",
  "cta": "Call-to-action text appropriate for the fan and home/away context",
  "image_concept": "Vivid, specific image/visual concept description — describe a scene, not a category"
}}

Return only valid JSON."""

    config = load_config()
    ollama_timeout = config.get("ollama", {}).get("timeout", 60)
    
    success, result = ollama_service.generate_json(prompt, timeout=ollama_timeout)
    
    if success and result:
        result["type"] = "llm"
        result["segment"] = segment
        result["segment_persona"] = SEGMENT_LABELS[segment]
        return result
    else:
        logger.warning(f"LLM generation failed: {result}")
        return None


def generate_for_game_segment(
    schedule_df: pd.DataFrame,
    fan_df: pd.DataFrame,
    game_date: str,
    segment: str,
    use_llm: bool = False,
    ollama_service: Optional[OllamaService] = None
) -> dict:
    """Generate creative for a specific game and segment."""
    # Find the game
    game_rows = schedule_df[schedule_df["GAME_DATE_DISPLAY"] == game_date]
    if game_rows.empty:
        logger.warning(f"Game not found for date: {game_date}")
        return {"error": "Game not found"}
    
    game_row = game_rows.iloc[0]
    
    # Build segment summary
    summary = build_segment_summary(fan_df, segment)
    
    # Build rule-based creative
    rule_based = build_rule_based_creative(game_row, segment, summary)
    
    # Generate LLM creative if requested — pass rule-based output as a starting brief
    llm_creative = None
    if use_llm and ollama_service:
        llm_creative = build_llm_creative(game_row, segment, summary, ollama_service, rule_based)
    
    return {
        "game_date": game_date,
        "opponent": game_row.get("OPPONENT", ""),
        "segment": segment,
        "segment_persona": SEGMENT_LABELS.get(segment, segment),
        "rule_based": rule_based,
        "llm": llm_creative,
        "summary": summary,
    }


def save_results(results: dict, game_date: str, segment: str) -> Path:
    """Save results to JSON file."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{segment}_{game_date}.json"
    filepath = RESULTS_DIR / filename
    
    with open(filepath, "w") as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"Saved results to {filepath}")
    return filepath


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate Brewers marketing creative")
    parser.add_argument("--segment", choices=list(SEGMENT_LABELS.keys()), help="Segment to generate for")
    parser.add_argument("--game", help="Game date in YYYY-MM-DD format")
    parser.add_argument("--use-llm", action="store_true", help="Generate LLM creative")
    parser.add_argument("--limit", type=int, default=None, help="Max random combinations to generate (default: all)")
    parser.add_argument("--workers", type=int, default=3, help="Number of parallel workers for batch generation (default: 3)")
    
    args = parser.parse_args()
    
    # Load data
    logger.info("Loading data...")
    schedule_df, fan_df = load_data()
    
    # Initialize Ollama if needed
    ollama_service = None
    if args.use_llm:
        config = load_config()
        ollama_config = config.get("ollama", {})
        ollama_service = OllamaService(
            base_url=ollama_config.get("base_url", "http://localhost:11434"),
            model=ollama_config.get("model", "mistral")
        )
        
        if not ollama_service.is_running():
            logger.error("Ollama service is not running!")
            sys.exit(1)
    
    # Generate creative
    if args.segment and args.game:
        # Single specific generation
        logger.info(f"Generating for {args.segment} - {args.game}")
        results = generate_for_game_segment(
            schedule_df, fan_df, args.game, args.segment,
            use_llm=args.use_llm,
            ollama_service=ollama_service
        )
        
        if "error" not in results:
            save_results(results, args.game, args.segment)
            logger.info("Generation complete!")
        else:
            logger.error(results["error"])
    else:
        # Batch generation - random sample or all
        game_dates = [d for d in schedule_df["GAME_DATE_DISPLAY"].unique() if pd.notna(d)]
        segments = list(SEGMENT_LABELS.keys())
        
        # Create all possible combinations
        combinations = [(game_date, segment) for game_date in game_dates for segment in segments]
        
        if args.limit:
            # Random sample up to limit
            sample_size = min(args.limit, len(combinations))
            sampled = random.sample(combinations, sample_size)
            logger.info(f"Generating random sample of {sample_size} combinations with {args.workers} workers...")
        else:
            # All combinations
            sampled = combinations
            sample_size = len(combinations)
            logger.info(f"Generating all {sample_size} combinations with {args.workers} workers...")
        
        # Parallel batch generation
        completed = 0
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {}
            for idx, (game_date, segment) in enumerate(sampled, 1):
                future = executor.submit(
                    generate_for_game_segment,
                    schedule_df, fan_df, game_date, segment,
                    use_llm=args.use_llm,
                    ollama_service=ollama_service
                )
                futures[future] = (idx, game_date, segment, sample_size)
            
            for future in as_completed(futures):
                idx, game_date, segment, total = futures[future]
                try:
                    results = future.result()
                    if "error" not in results:
                        save_results(results, game_date, segment)
                        completed += 1
                        logger.info(f"✓ Completed {completed}/{total}: {segment} - {game_date}")
                    else:
                        logger.warning(f"✗ Error {idx}/{total}: {segment} - {game_date}: {results['error']}")
                except Exception as e:
                    logger.error(f"✗ Exception {idx}/{total}: {segment} - {game_date}: {str(e)}")
        
        logger.info(f"Batch generation complete! Generated {completed}/{sample_size} combinations.")


if __name__ == "__main__":
    main()
