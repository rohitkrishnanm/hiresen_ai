"""
Side-by-Side Candidate Comparison — Vision Board Resume X
Select 2–3 candidates from the database and compare their scores,
section breakdowns, and violations in a structured view.
"""
import json
import datetime

import pandas as pd
import streamlit as st
st.set_page_config(page_title="Compare Candidates", page_icon="⚖️", layout="wide")

from core.db import get_all_submissions

if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.warning("Please log in from the main page to access this feature.")
    st.stop()

# ── Helpers ─────────────────────────────────────────────────────────────────────

def _safe_json(value, fallback):
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def score_color(score: float) -> str:
    if score >= 80:
        return "🟢"
    elif score >= 60:
        return "🟡"
    return "🔴"


# ── Page Header ─────────────────────────────────────────────────────────────────
st.title("⚖️ Side-by-Side Candidate Comparison")
st.markdown(
    "Select **2 or 3 candidates** from previous submissions to compare scores, "
    "rule violations, and AI section breakdowns."
)

# ── Load Submissions ─────────────────────────────────────────────────────────────
rows = get_all_submissions()

if not rows:
    st.info("No submissions found. Upload resumes first using the Upload or Batch Upload pages.")
    st.stop()

# Build label → row map (sorted by score descending for convenience)
rows_sorted = sorted(rows, key=lambda r: r.get("overall_score", 0), reverse=True)
label_map = {
    f"{r['candidate_name']}  —  {r.get('overall_score', 0):.0f}%  ({r.get('uploaded_at', '')[:10]})": r
    for r in rows_sorted
}

# ── Candidate Selector ───────────────────────────────────────────────────────────
selected_labels = st.multiselect(
    "Choose candidates to compare (2–3)",
    options=list(label_map.keys()),
    max_selections=3,
    placeholder="Start typing a name…",
)

if len(selected_labels) < 2:
    st.info("👆 Select at least 2 candidates to start the comparison.")
    st.stop()

candidates = [label_map[lbl] for lbl in selected_labels]

st.divider()

# ── Score Overview Table ──────────────────────────────────────────────────────────
st.subheader("📊 Score Overview")

overview_rows = []
for c in candidates:
    viols = _safe_json(c.get("rule_violations_json"), [])
    overview_rows.append({
        "Candidate": c["candidate_name"],
        "Overall %": c.get("overall_score", 0),
        "Checklist %": c.get("rules_score", 0),
        "AI Quality %": c.get("llm_score", 0),
        "Violations": len(viols) if isinstance(viols, list) else 0,
        "Pages": c.get("page_count", "—"),
        "Vendor": c.get("vendor_name", "—"),
        "Date": str(c.get("uploaded_at", ""))[:10],
    })

df_overview = pd.DataFrame(overview_rows)

# Highlight winner
max_overall = df_overview["Overall %"].max()

def highlight_winner(row):
    if row["Overall %"] == max_overall:
        return ["background-color: #1a4731; color: #4ade80; font-weight: bold"] * len(row)
    return [""] * len(row)

st.dataframe(
    df_overview.style.apply(highlight_winner, axis=1),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Overall %": st.column_config.ProgressColumn("Overall %", min_value=0, max_value=100, format="%.0f%%"),
        "Checklist %": st.column_config.ProgressColumn("Checklist %", min_value=0, max_value=100, format="%.0f%%"),
        "AI Quality %": st.column_config.ProgressColumn("AI Quality %", min_value=0, max_value=100, format="%.0f%%"),
    },
)

winner_name = df_overview.loc[df_overview["Overall %"].idxmax(), "Candidate"]
st.success(f"🏆 **Top Candidate:** {winner_name} with **{max_overall:.0f}%** overall score")

st.divider()

# ── Section Score Comparison Chart ────────────────────────────────────────────────
st.subheader("🧠 AI Section Score Comparison (out of 10)")

section_data = {}
for c in candidates:
    llm_output = _safe_json(c.get("llm_output_json"), {})
    scores = llm_output.get("section_scores", {})
    if isinstance(scores, dict):
        section_data[c["candidate_name"]] = scores

if section_data:
    df_sections = pd.DataFrame(section_data).fillna(0)
    st.bar_chart(df_sections, use_container_width=True)
    st.caption("Each bar group represents one section category. Taller = stronger in that area.")
else:
    st.info("Section score data unavailable for the selected candidates.")

st.divider()

# ── Metric Cards per Candidate ───────────────────────────────────────────────────
st.subheader("🔬 Detailed Breakdown")

cols = st.columns(len(candidates))
for col, c in zip(cols, candidates):
    with col:
        score = c.get("overall_score", 0)
        icon = score_color(score)
        st.markdown(f"### {icon} {c['candidate_name']}")
        st.metric("Overall Score", f"{score:.0f}%")
        st.metric("Checklist", f"{c.get('rules_score', 0):.0f}%")
        st.metric("AI Quality", f"{c.get('llm_score', 0):.0f}%")

        llm_output = _safe_json(c.get("llm_output_json"), {})

        # Strengths
        with st.expander("✅ Strengths"):
            strengths = llm_output.get("strengths", [])
            if strengths:
                for s in strengths:
                    st.write(f"• {s}")
            else:
                st.info("No strengths recorded.")

        # Gaps
        with st.expander("⚠️ Gaps"):
            gaps = llm_output.get("gaps", [])
            if gaps:
                for g in gaps:
                    st.write(f"• {g}")
            else:
                st.success("No gaps recorded.")

        # Rule Violations
        with st.expander("🚨 Violations"):
            viols = _safe_json(c.get("rule_violations_json"), [])
            if isinstance(viols, list) and viols:
                for v in viols:
                    st.error(f"**{v.get('rule_id', '?')}**: {v.get('violation_message', '')}")
            else:
                st.success("No violations.")

        # Top Coaching Actions
        with st.expander("🎯 Top Coaching Actions"):
            improvements = _safe_json(c.get("improvements_json"), [])
            if isinstance(improvements, list) and improvements:
                for imp in improvements[:3]:
                    prio = imp.get("priority", "Medium")
                    icon_p = "🔴" if prio == "High" else ("🟠" if prio == "Medium" else "🟢")
                    st.markdown(
                        f"{icon_p} **{imp.get('section', '—')}**: {imp.get('suggestion', '—')}"
                    )
            else:
                st.info("No coaching actions.")


st.divider()

# ── Violations Side-by-Side Table ────────────────────────────────────────────────
st.subheader("📋 Violations Cross-Reference")

all_rule_ids = set()
viol_by_candidate: dict = {}
for c in candidates:
    viols = _safe_json(c.get("rule_violations_json"), [])
    vmap = {}
    if isinstance(viols, list):
        for v in viols:
            rid = v.get("rule_id", "?")
            vmap[rid] = v.get("violation_message", "")
            all_rule_ids.add(rid)
    viol_by_candidate[c["candidate_name"]] = vmap

if all_rule_ids:
    xref_rows = []
    for rid in sorted(all_rule_ids):
        row = {"Rule ID": rid}
        for c in candidates:
            cname = c["candidate_name"]
            msg = viol_by_candidate[cname].get(rid)
            row[cname] = f"❌ {msg}" if msg else "✅ Pass"
        xref_rows.append(row)

    df_xref = pd.DataFrame(xref_rows)
    st.dataframe(df_xref, use_container_width=True, hide_index=True)
else:
    st.success("No rule violations found across all selected candidates.")

st.divider()

# ── Export ────────────────────────────────────────────────────────────────────────
st.subheader("📥 Export Comparison")

export_df = df_overview.copy()
# Add violations detail
for c in candidates:
    viols = _safe_json(c.get("rule_violations_json"), [])
    ids = ", ".join(v.get("rule_id", "") for v in viols) if isinstance(viols, list) else ""
    export_df.loc[export_df["Candidate"] == c["candidate_name"], "Violated Rules"] = ids

csv = export_df.to_csv(index=False).encode("utf-8")
st.download_button(
    "📊 Download Comparison CSV",
    data=csv,
    file_name=f"VisionBoard_ResumeX_Comparison_{datetime.date.today()}.csv",
    mime="text/csv",
    use_container_width=True,
)
