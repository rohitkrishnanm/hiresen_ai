"""
Batch Resume Upload — Vision Board Resume X
Upload a ZIP archive or multiple individual files at once.
Evaluates all resumes in parallel (ThreadPoolExecutor, max 3 workers)
and displays a ranked leaderboard with export options.
"""
import io
import zipfile
import datetime
import uuid
import concurrent.futures
from typing import List, Optional, Tuple

import pandas as pd
import streamlit as st
st.set_page_config(page_title="Batch Upload", page_icon="📦", layout="wide")

from core.db import save_evaluation
from core.scoring import calculate_overall_score, normalize_llm_score
from evaluation.llm_evaluator import LLMEvaluator
from evaluation.resume_parser import ResumeParser
from evaluation.rules_engine import RulesEngine
from core.vector_db import VectorDBClient
from core.report_generator import generate_pdf_report

if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.warning("Please log in from the main page to access this feature.")
    st.stop()

# ── Constants ──────────────────────────────────────────────────────────────────
MAX_FILES = 25
ALLOWED_EXTS = {".pdf", ".docx", ".png", ".jpg", ".jpeg"}
MAGIC_BYTES = {
    b"\x25\x50\x44\x46": "pdf",                          # %PDF
    b"\x50\x4b\x03\x04": "docx",                         # ZIP (docx)
    b"\xff\xd8\xff": "jpeg",                              # JPEG
    b"\x89\x50\x4e\x47": "png",                          # PNG
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def detect_mime(data: bytes) -> Optional[str]:
    for magic, fmt in MAGIC_BYTES.items():
        if data[:len(magic)] == magic:
            return fmt
    return None


def ext_ok(filename: str) -> bool:
    return any(filename.lower().endswith(ext) for ext in ALLOWED_EXTS)


def files_from_zip(zip_bytes: bytes) -> List[Tuple[str, bytes]]:
    """Extract (filename, bytes) pairs from a ZIP, skipping Mac metadata."""
    results = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if name.startswith("__MACOSX") or name.startswith("."):
                continue
            if ext_ok(name):
                results.append((name.split("/")[-1], zf.read(name)))
    return results


def evaluate_one(candidate_name: str, vendor_name: str, filename: str, file_bytes: bytes) -> dict:
    """Full evaluation pipeline for a single resume. Thread-safe."""
    file_id = str(uuid.uuid4())
    parser = ResumeParser()
    parsed_data = parser.parse(file_bytes, filename=filename)

    # Vector DB (best-effort)
    try:
        vdb = VectorDBClient()
        vdb.add_document(
            text=parsed_data["text_content"],
            metadata={"id": file_id, "candidate_name": candidate_name, "filename": filename,
                      "timestamp": str(datetime.datetime.now())},
        )
    except Exception:
        pass

    rules_engine = RulesEngine()
    rules_result = rules_engine.evaluate(parsed_data)

    llm_evaluator = LLMEvaluator()
    llm_result = llm_evaluator.evaluate(parsed_data)

    overall = calculate_overall_score(rules_result["score"], llm_result.quality_score)

    evaluation_data = {
        "id": file_id,
        "uploaded_at": datetime.datetime.now(),
        "candidate_name": candidate_name,
        "vendor_name": vendor_name or "Direct",
        "filename": filename,
        "file_path": "memory",
        "page_count": parsed_data.get("page_count", 0),
        "checklist_version_id": rules_result.get("checklist_version_id", "v1.0-MVP"),
        "rules_score": rules_result["score"],
        "llm_score": normalize_llm_score(llm_result.quality_score),
        "overall_score": overall,
        "rule_violations": rules_result["violations"],
        "checklist_scan": rules_result.get("checklist_scan", []),
        "section_scores": llm_result.section_scores,
        "improvements": [i.model_dump() for i in llm_result.improvements],
        "llm_output": llm_result.model_dump(),
        "model_name": "gpt-5",
        "prompt_version": "v1",
    }
    return evaluation_data


# ── Page UI ────────────────────────────────────────────────────────────────────

st.title("📦 Batch Resume Upload")
st.markdown(
    "Upload up to **25 resumes** at once — as a ZIP archive or individual files. "
    "All resumes are evaluated in parallel and ranked by overall score."
)

# Session state
if "batch_results" not in st.session_state:
    st.session_state["batch_results"] = []

# ── Upload form ────────────────────────────────────────────────────────────────
vendor_name = st.text_input("Vendor / Company (applied to all)", placeholder="Tech Solutions Inc")

upload_mode = st.radio(
    "Upload mode",
    ["📁 Multiple individual files", "🗜️ ZIP archive"],
    horizontal=True,
)

if upload_mode == "📁 Multiple individual files":
    uploaded_files = st.file_uploader(
        f"Select up to {MAX_FILES} resume files",
        type=["pdf", "docx", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )
    zip_file = None
else:
    zip_file = st.file_uploader("Upload a ZIP archive of resumes", type=["zip"])
    uploaded_files = []

st.caption(
    "💡 Candidate names are inferred from filenames "
    "(e.g. `John_Doe_Resume.pdf` → *John Doe*). "
    "You can rename them in the leaderboard before saving."
)

submitted = st.button("🚀 Evaluate All Resumes", use_container_width=True)


# ── Resolve file list ──────────────────────────────────────────────────────────
def infer_name(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    stem = stem.replace("_", " ").replace("-", " ")
    # Drop common suffixes
    for suffix in ["Resume", "CV", "resume", "cv", "2025", "2026", "final", "Final", "updated"]:
        stem = stem.replace(suffix, "")
    return " ".join(stem.split()).strip() or stem


if submitted:
    file_list: List[Tuple[str, bytes]] = []

    if zip_file is not None:
        try:
            file_list = files_from_zip(zip_file.getvalue())
            if not file_list:
                st.error("No valid resume files found inside the ZIP. Check that files have PDF/DOCX/image extensions.")
                st.stop()
        except zipfile.BadZipFile:
            st.error("Uploaded file is not a valid ZIP archive.")
            st.stop()
    elif uploaded_files:
        for f in uploaded_files:
            if ext_ok(f.name):
                file_list.append((f.name, f.getvalue()))
    else:
        st.warning("Please upload at least one file.")
        st.stop()

    # Validate file extension
    valid_list = []
    skipped = []
    for fname, fbytes in file_list:
        if ext_ok(fname):
            valid_list.append((fname, fbytes))
        else:
            skipped.append(fname)

    if skipped:
        st.warning(f"⚠️ Skipped {len(skipped)} file(s) with invalid extensions: {', '.join(skipped)}")

    if not valid_list:
        st.error("No processable files remain after validation.")
        st.stop()

    if len(valid_list) > MAX_FILES:
        st.warning(f"Capping at {MAX_FILES} files. {len(valid_list) - MAX_FILES} file(s) were dropped.")
        valid_list = valid_list[:MAX_FILES]

    # ── Parallel Evaluation ────────────────────────────────────────────────────
    st.info(f"🔄 Evaluating **{len(valid_list)}** resume(s) using GPT-5 (3 parallel workers)…")
    progress_bar = st.progress(0, text="Starting…")
    status_placeholder = st.empty()

    results = []
    completed = 0
    errors = []

    def eval_task(args):
        fname, fbytes = args
        cname = infer_name(fname)
        return evaluate_one(cname, vendor_name, fname, fbytes)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_map = {executor.submit(eval_task, item): item[0] for item in valid_list}
        for future in concurrent.futures.as_completed(future_map):
            fname = future_map[future]
            completed += 1
            pct = int(completed / len(valid_list) * 100)
            progress_bar.progress(pct, text=f"Evaluated {completed}/{len(valid_list)} — {fname}")
            status_placeholder.caption(f"✅ Done: `{fname}`")
            try:
                result = future.result()
                results.append(result)
                save_evaluation(result)
            except Exception as exc:
                errors.append((fname, str(exc)))

    progress_bar.progress(100, text="All evaluations complete!")
    status_placeholder.empty()

    if errors:
        for fname, err in errors:
            st.error(f"❌ `{fname}` failed: {err}")

    st.session_state["batch_results"] = results
    st.success(f"✅ {len(results)} resume(s) evaluated and saved successfully!")
    st.balloons()


# ── Leaderboard ────────────────────────────────────────────────────────────────
if st.session_state["batch_results"]:
    results = st.session_state["batch_results"]

    st.divider()
    st.header("🏆 Candidate Leaderboard")

    leaderboard_rows = []
    for r in results:
        violations_count = len(r.get("rule_violations", []))
        rank_color = "🟢" if r["overall_score"] >= 80 else ("🟡" if r["overall_score"] >= 60 else "🔴")
        leaderboard_rows.append({
            "Rank": rank_color,
            "Candidate": r["candidate_name"],
            "Overall %": r["overall_score"],
            "Checklist %": r["rules_score"],
            "AI Quality %": r["llm_score"],
            "Violations": violations_count,
            "Pages": r.get("page_count", "—"),
            "File": r["filename"],
            "_id": r["id"],
        })

    df_lb = pd.DataFrame(leaderboard_rows).sort_values("Overall %", ascending=False).reset_index(drop=True)
    df_lb.index += 1  # Rank starts at 1

    # Display without internal ID
    st.dataframe(
        df_lb.drop(columns=["_id"]),
        use_container_width=True,
        column_config={
            "Overall %": st.column_config.ProgressColumn("Overall %", min_value=0, max_value=100, format="%.0f%%"),
            "Checklist %": st.column_config.ProgressColumn("Checklist %", min_value=0, max_value=100, format="%.0f%%"),
            "AI Quality %": st.column_config.ProgressColumn("AI Quality %", min_value=0, max_value=100, format="%.0f%%"),
        },
    )

    # Quick stats
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Top Score", f"{df_lb['Overall %'].max():.0f}%")
    col2.metric("Average Score", f"{df_lb['Overall %'].mean():.1f}%")
    col3.metric("Pass Rate (≥70%)", f"{(df_lb['Overall %'] >= 70).mean() * 100:.0f}%")
    col4.metric("Candidates", len(df_lb))

    # Score distribution bar chart
    st.subheader("📊 Score Distribution")
    bins = pd.cut(df_lb["Overall %"], bins=[0, 40, 60, 70, 80, 90, 100],
                  labels=["0–40", "40–60", "60–70", "70–80", "80–90", "90–100"])
    dist_df = bins.value_counts().sort_index().rename_axis("Score Range").reset_index(name="Count")
    st.bar_chart(dist_df.set_index("Score Range"))

    # ── Export options ─────────────────────────────────────────────────────────
    st.subheader("📥 Export")
    col_e1, col_e2 = st.columns(2)

    with col_e1:
        csv_bytes = df_lb.drop(columns=["_id"]).to_csv(index=True).encode("utf-8")
        st.download_button(
            "📊 Download Leaderboard CSV",
            data=csv_bytes,
            file_name=f"VisionBoard_ResumeX_Batch_{datetime.date.today()}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with col_e2:
        st.info("To download individual PDF reports, use the selector below.")

    # ── Per-candidate PDF download ─────────────────────────────────────────────
    st.subheader("📄 Individual Reports")
    candidate_map = {r["candidate_name"]: r for r in results}
    selected_cand = st.selectbox("Select candidate for PDF report", list(candidate_map.keys()))
    if selected_cand:
        sel_data = candidate_map[selected_cand]
        pdf_bytes = generate_pdf_report(sel_data)
        st.download_button(
            f"📥 Download PDF — {selected_cand}",
            data=pdf_bytes,
            file_name=f"VisionBoard_ResumeX_Report_{selected_cand}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

        # Show violations for selected candidate
        with st.expander(f"🚨 Violations for {selected_cand}"):
            viols = sel_data.get("rule_violations", [])
            if not viols:
                st.success("No violations detected.")
            else:
                for v in viols:
                    st.error(f"**{v['rule_id']}**: {v['violation_message']}")
