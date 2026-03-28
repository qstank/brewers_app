from __future__ import annotations

import json
import logging

import pandas as pd
import streamlit as st

from creative_engine import (
    RESULTS_DIR,
    SEGMENT_LABELS,
    build_crm_export,
    build_ollama_service,
    build_rule_based_creative,
    build_segment_summary,
    generate_for_game_segment,
    load_data,
    save_results,
)

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Brewers Email Marketing Engine", layout="wide")

if "llm_creative" not in st.session_state:
    st.session_state.llm_creative = None

CHART_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f"]


def _render_chart(table_dict: dict, border_style: str = "") -> None:
    """Render vertical colored bars with a color-coded legend below."""
    max_count = 0
    entries = []
    for label, val in table_dict.items():
        count = int(val.split(" ")[0])
        if count > max_count:
            max_count = count
        entries.append((label, val, count))

    bar_height = 70
    bars = []
    for i, (label, val, count) in enumerate(entries):
        color = CHART_COLORS[i % len(CHART_COLORS)]
        pct_height = int((count / max_count) * bar_height) if max_count > 0 else 0
        bars.append(
            f'<div style="display:flex;flex-direction:column;align-items:center;flex:1;">'
            f'<div style="height:{bar_height}px;width:100%;display:flex;align-items:flex-end;justify-content:center;">'
            f'<div style="background:{color};width:60%;height:{pct_height}px;border-radius:2px 2px 0 0;"></div>'
            f'</div>'
            f'</div>'
        )

    legend = []
    for i, (label, val, count) in enumerate(entries):
        color = CHART_COLORS[i % len(CHART_COLORS)]
        legend.append(
            f'<div style="margin-bottom:1px;line-height:1.2;">'
            f'<span style="display:inline-block;width:8px;height:8px;background:{color};border-radius:2px;margin-right:3px;vertical-align:middle;"></span>'
            f'<span style="font-size:10px;vertical-align:middle;">{label}: <b>{val}</b></span>'
            f'</div>'
        )

    st.markdown(
        f'<div style="{border_style}">'
        f'<div style="display:flex;gap:2px;margin-bottom:4px;">{"" .join(bars)}</div>'
        f'{"" .join(legend)}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _display_creative(creative_dict: dict, caption: str = "") -> None:
    """Render a creative output block (subject, preheader, headline, body, CTA, image)."""
    st.markdown(f"**Subject line:** {creative_dict.get('subject_line', '')}")
    st.markdown(f"**Preheader:** {creative_dict.get('preheader', '')}")
    st.markdown(f"**Headline:** {creative_dict.get('headline', '')}")
    st.markdown(f"**Body copy:**\n\n{creative_dict.get('body_copy', '')}")
    st.markdown(f"**CTA:** {creative_dict.get('cta', '')}")
    st.markdown(f"**Image concept:**\n\n{creative_dict.get('image_concept', '')}")
    if caption:
        st.caption(caption)


def load_llm_creative(game_date: str, segment: str) -> dict | None:
    """Load pre-generated LLM creative from batch results JSON file."""
    filename = f"{segment}_{game_date}.json"
    filepath = RESULTS_DIR / filename
    
    if not filepath.exists():
        return None
    
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
        return data.get("llm")  # Return LLM creative if it exists
    except Exception as e:
        logger.warning("Failed to load creative from %s: %s", filepath, e)
        st.error(f"Error loading creative: {e}")
        return None


def run_batch_generation(segment: str, game_date: str, use_llm: bool = True, fan_row=None, extra_notes: str = "") -> tuple[bool, str | None]:
    """Generate creative in-process for the selected game and segment."""
    try:
        schedule_df, fan_df = load_data()
        ollama_service = None

        if use_llm:
            ollama_service = build_ollama_service()
            if not ollama_service.is_running():
                return False, "Ollama is not running. Start it with `ollama serve` and try again."
            if not ollama_service.model_exists():
                return False, f"Ollama model '{ollama_service.model}' is not available. Pull it with `ollama pull {ollama_service.model}`."

        results = generate_for_game_segment(
            schedule_df,
            fan_df,
            game_date,
            segment,
            use_llm=use_llm,
            ollama_service=ollama_service,
            fan_row=fan_row,
            extra_notes=extra_notes,
        )

        if "error" in results:
            return False, results["error"]

        save_results(results, game_date, segment)

        if use_llm and results.get("llm") is None:
            return False, "The model returned a response, but it could not be converted into the expected creative JSON format."

        return True, None
    except Exception as e:
        logger.exception("Generation failed for segment=%s game=%s", segment, game_date)
        return False, f"Generation failed: {e}"


schedule_df, fan_df = load_data()

st.title("Milwaukee Brewers Email Marketing Engine")

with st.sidebar:
    st.header("POC Settings")
    selected_segment = st.selectbox(
        "Target segment",
        options=["Die-hard", "F&B", "Family", "Social"],
        format_func=lambda x: f"{SEGMENT_LABELS[x]} ({x})",
    )
    selected_game_label = st.selectbox("Select upcoming game", options=schedule_df["GAME_LABEL"].tolist())
    selected_game = schedule_df[schedule_df["GAME_LABEL"] == selected_game_label].iloc[0]

    custom_note = st.text_area("Optional campaign note", placeholder="Weekend energy, rivalry angle, giveaway note, etc.")
    show_data_preview = st.checkbox("Show uploaded data preview", value=False)
    st.divider()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Game date", selected_game["GAME_DATE_DISPLAY"])
col2.metric("Opponent", selected_game["OPPONENT"])
col3.metric("Game time", str(selected_game["GAME_TIME_DISPLAY"]))
col4.metric("Home/Away", selected_game["HOME_AWAY"])

segment_summary = build_segment_summary(fan_df, selected_segment)
creative = build_rule_based_creative(selected_game, selected_segment, segment_summary, custom_note)
crm_export = build_crm_export(fan_df, selected_segment, creative, selected_game)


st.subheader("Segment summary")
if segment_summary["sample_size"] == 0:
    st.warning("This segment is not present in the uploaded fan file. The POC uses a manual fallback definition for this persona.")
else:
    n = segment_summary['sample_size']
    st.markdown(f"**{selected_segment}** — {n} fans in segment")
    st.caption(f"Percentages represent share of the {n} fans in the {selected_segment} segment.")

    chart_sections = [
        ("Attendance Patterns", segment_summary.get("attendance_table", {})),
        ("Email Engagement", segment_summary.get("email_table", {})),
        ("Top Interests", segment_summary.get("interests_table", {})),
        ("Behavioral Notes", segment_summary.get("notes_table", {})),
    ]
    all_cols = st.columns(4, gap="small")
    for idx, (title, table) in enumerate(chart_sections):
        with all_cols[idx]:
            border_style = "border-left:1px solid rgba(128,128,128,0.3);padding-left:8px;" if idx > 0 else ""
            st.markdown(f"<div style='{border_style}font-size:12px;font-weight:bold;margin-bottom:4px;'>{title}</div>", unsafe_allow_html=True)
            if table:
                _render_chart(table, border_style)

st.divider()
st.subheader("Generated creative")

# Fan picker — filter by selected segment
segment_fans = fan_df[fan_df["Segment"] == selected_segment].copy()
fan_options = ["None (segment-level)"] + [
    f"Fan #{int(row['Fan_ID'])} — {row['Interests']}, {row['Attendance_Behavior']}"
    for _, row in segment_fans.iterrows()
]
selected_fan_label = st.selectbox("Target specific fan", options=fan_options)
selected_fan_row = None
if selected_fan_label != "None (segment-level)":
    fan_id = int(selected_fan_label.split("#")[1].split(" ")[0])
    selected_fan_row = fan_df[fan_df["Fan_ID"] == fan_id].iloc[0]

# Track current selection and reload LLM creative when game/segment/fan changes
_fan_id = int(selected_fan_row["Fan_ID"]) if selected_fan_row is not None else "all"
current_key = f"{selected_segment}_{selected_game['GAME_DATE_DISPLAY']}_{_fan_id}"
if st.session_state.get("_llm_selection_key") != current_key:
    st.session_state._llm_selection_key = current_key
    st.session_state.llm_creative = load_llm_creative(selected_game["GAME_DATE_DISPLAY"], selected_segment)

if st.button("✨ Generate AI Creative"):
    with st.spinner("Running generation..."):
        success, error_message = run_batch_generation(selected_segment, selected_game["GAME_DATE_DISPLAY"], use_llm=True, fan_row=selected_fan_row, extra_notes=custom_note)
        if success:
            llm_result = load_llm_creative(selected_game["GAME_DATE_DISPLAY"], selected_segment)
            if llm_result:
                st.session_state.llm_creative = llm_result
                st.success("AI creative generated successfully.")
                st.rerun()
        else:
            st.warning(error_message or "Generation completed without usable AI creative.")

# Display rule-based and LLM versions side-by-side
if st.session_state.llm_creative:
    col_rb, col_llm = st.columns([1, 1])

    with col_rb:
        st.write("**Rule-Based Output**")
        _display_creative(creative, "Generated from segment rules and game context")
        if st.button("🖼️ Generate Image from Rule-Based Copy"):
            with st.spinner("Generating image from rule-based copy..."):
                ollama_service = build_ollama_service()
                prompt = creative.get("image_concept", "")
                try:
                    success, img_bytes, err_msg = ollama_service.generate_image(prompt)
                    if success and img_bytes:
                        st.image(img_bytes, caption="Rule-Based Image", use_column_width=True)
                    elif err_msg and "Not enough RAM" in err_msg:
                        st.error("Image generation failed: Not enough RAM for image model. Please close other applications or use a machine with more memory.")
                    else:
                        st.error(f"Image generation failed. {err_msg if err_msg else 'Unknown error'}")
                except Exception as e:
                    st.error(f"Image generation error: {e}")

    with col_llm:
        st.write("**LLM Generated**")
        _display_creative(st.session_state.llm_creative, "Generated by batch script using Ollama")
        if st.button("🖼️ Generate Image from AI Copy"):
            with st.spinner("Generating image from AI copy..."):
                ollama_service = build_ollama_service()
                prompt = st.session_state.llm_creative.get("image_concept", "")
                try:
                    success, img_bytes, err_msg = ollama_service.generate_image(prompt)
                    if success and img_bytes:
                        st.image(img_bytes, caption="AI Copy Image", use_column_width=True)
                    elif err_msg and "Not enough RAM" in err_msg:
                        st.error("Image generation failed: Not enough RAM for image model. Please close other applications or use a machine with more memory.")
                    else:
                        st.error(f"Image generation failed. {err_msg if err_msg else 'Unknown error'}")
                except Exception as e:
                    st.error(f"Image generation error: {e}")
else:
    st.write("**Rule-Based Output** (Click button above to generate AI version)")
    _display_creative(creative, creative["rationale"])


st.divider()
st.subheader("CRM-ready export preview")

if crm_export.empty:
    st.info("No customers in this segment. CRM export is empty.")
else:
    # Use LLM creative in export if available, otherwise rule-based
    export_df = crm_export.copy()
    if st.session_state.llm_creative:
        export_df["Creative_Subject_Line"] = st.session_state.llm_creative.get("subject_line", "")
        export_df["Creative_Headline"] = st.session_state.llm_creative.get("headline", "")
        export_df["Creative_CTA"] = st.session_state.llm_creative.get("cta", "")
        export_df["Creative_Image_Concept"] = st.session_state.llm_creative.get("image_concept", "")

    creative_label = "LLM" if st.session_state.llm_creative else "Rule-Based"
    st.write(f"**{creative_label} Creative — {len(export_df)} customers**")
    st.dataframe(export_df, use_container_width=True, hide_index=True)

    csv_data = export_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Download CRM Export",
        data=csv_data,
        file_name=f"brewers_campaign_{selected_segment.lower().replace('&', 'and')}_{selected_game['GAME_DATE_DISPLAY']}.csv",
        mime="text/csv",
    )


st.divider()
st.subheader("What this POC demonstrates")
st.markdown(
    """
- Business user selects a game and target audience segment.
- App combines schedule data with fan-segment traits.
- System generates differentiated email copy and an image concept.
- App outputs a simple CSV structure for CRM upload / downstream activation.
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
