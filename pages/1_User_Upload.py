import streamlit as st
st.set_page_config(page_title="Upload Resume", page_icon="📄", layout="wide")
import uuid
import datetime

# Import core modules
from core.db import save_evaluation
from evaluation.resume_parser import ResumeParser
from evaluation.rules_engine import RulesEngine
from evaluation.llm_evaluator import LLMEvaluator
from core.vector_db import VectorDBClient
from core.scoring import calculate_overall_score, normalize_llm_score

if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.warning("Please log in from the main page to access this feature.")
    st.stop()

st.title("📄 Upload Resume")
st.markdown("Submit a single resume for instant AI evaluation and compliance scoring.")

# ---------- Session State ----------
if 'last_submission' not in st.session_state:
    st.session_state['last_submission'] = None
if 'last_file_bytes' not in st.session_state:
    st.session_state['last_file_bytes'] = None
if 'last_file_ext' not in st.session_state:
    st.session_state['last_file_ext'] = None
if 'last_parsed_data' not in st.session_state:
    st.session_state['last_parsed_data'] = None

# ---------- Score Methodology Info ----------
with st.expander("ℹ️ How is the score calculated?", expanded=False):
    st.markdown("""
    | Component | Weight | Source |
    |-----------|--------|--------|
    | **Checklist / Rules Score** | 40% | Deterministic rules engine — checks filename format, mandatory keywords, section presence, certification mentions, and detail depth |
    | **AI Quality Score** | 60% | GPT-4o holistic review — evaluates narrative quality, impact clarity, technical depth, and overall readiness for the Azure Data Engineer role |

    > The 40/60 split is intentional: compliance is necessary but a technically compelling resume can still score well even with minor formatting gaps.
    """)

# ---------- Upload Form ----------
with st.form("upload_form"):
    col_a, col_b = st.columns(2)
    with col_a:
        candidate_name = st.text_input("Candidate Name *", placeholder="John Doe")
    with col_b:
        vendor_name = st.text_input("Vendor Company", placeholder="Tech Solutions Inc")
    
    uploaded_file = st.file_uploader(
        "Choose a file (PDF, DOCX, PNG, JPG)",
        type=["pdf", "docx", "png", "jpg", "jpeg"]
    )
    submitted = st.form_submit_button("🚀 Analyze Resume", use_container_width=True)

# ---------- Evaluation Logic ----------
def run_evaluation(candidate_name: str, vendor_name: str, file_bytes: bytes, filename: str):
    """Run the full evaluation pipeline and return evaluation_data dict."""
    file_id = str(uuid.uuid4())

    # 1. Parse
    parser = ResumeParser()
    parsed_data = parser.parse(file_bytes, filename=filename)

    # 2. Vector DB Storage
    try:
        vdb = VectorDBClient()
        vdb.add_document(
            text=parsed_data['text_content'],
            metadata={
                "id": file_id,
                "candidate_name": candidate_name,
                "filename": filename,
                "timestamp": str(datetime.datetime.now())
            }
        )
    except Exception as e:
        print(f"Vector DB Error: {e}")

    # 3. Rules Engine
    rules_engine = RulesEngine()
    rules_result = rules_engine.evaluate(parsed_data)

    # 4. LLM Evaluation
    llm_evaluator = LLMEvaluator()
    llm_result = llm_evaluator.evaluate(parsed_data)

    overall_score = calculate_overall_score(rules_result['score'], llm_result.quality_score)

    evaluation_data = {
        "id": file_id,
        "uploaded_at": datetime.datetime.now(),
        "candidate_name": candidate_name,
        "vendor_name": vendor_name or "Direct",
        "filename": filename,
        "file_path": "memory",
        "page_count": parsed_data.get("page_count"),
        "checklist_version_id": rules_result.get('checklist_version_id', 'v1.0-MVP'),
        "rules_score": rules_result['score'],
        "llm_score": normalize_llm_score(llm_result.quality_score),
        "overall_score": overall_score,
        "rule_violations": rules_result['violations'],
        "checklist_scan": rules_result.get('checklist_scan', []),
        "section_scores": llm_result.section_scores,
        "improvements": [i.model_dump() for i in llm_result.improvements],
        "llm_output": llm_result.model_dump(),
        "model_name": "gpt-5",
        "prompt_version": "v1",
        "_parsed_data": parsed_data,  # transient — not saved to DB
    }
    return evaluation_data


if submitted:
    if not candidate_name or not uploaded_file:
        st.error("Please fill in candidate name and upload a file.")
    else:
        with st.spinner("Processing resume… Parsing → Checklist Scan → AI Evaluation (10–15s)"):
            file_bytes = uploaded_file.getvalue()
            try:
                evaluation_data = run_evaluation(
                    candidate_name, vendor_name, file_bytes, uploaded_file.name
                )
                save_evaluation(evaluation_data)
                st.session_state['last_submission'] = evaluation_data
                st.session_state['last_file_bytes'] = file_bytes
                st.session_state['last_file_ext'] = uploaded_file.name.split(".")[-1].lower()
                st.session_state['last_parsed_data'] = evaluation_data.pop('_parsed_data', None)
                st.success("✅ Analysis Complete!")
                st.balloons()
            except Exception as e:
                st.error(f"Error during evaluation: {e}")


# ---------- Re-evaluate Button ----------
if st.session_state.get('last_submission') and st.session_state.get('last_file_bytes'):
    if st.button("🔄 Re-evaluate Same Resume", help="Re-run the full AI evaluation using the cached file — useful if the rules checklist was updated."):
        data = st.session_state['last_submission']
        with st.spinner("Re-evaluating… this runs a fresh GPT-4o pass"):
            try:
                file_bytes = st.session_state['last_file_bytes']
                ext = st.session_state['last_file_ext']
                evaluation_data = run_evaluation(
                    data['candidate_name'],
                    data['vendor_name'],
                    file_bytes,
                    data['filename']
                )
                save_evaluation(evaluation_data)
                st.session_state['last_submission'] = evaluation_data
                st.session_state['last_parsed_data'] = evaluation_data.pop('_parsed_data', None)
                st.success("✅ Re-evaluation complete!")
                st.rerun()
            except Exception as e:
                st.error(f"Re-evaluation failed: {e}")


# ---------- Results Display ----------
if st.session_state['last_submission']:
    data = st.session_state['last_submission']
    st.divider()
    st.header(f"📊 Analysis Result: {data['candidate_name']}")

    # Score callouts
    c1, c2, c3 = st.columns(3)
    with c1:
        score = data['overall_score']
        delta_color = "normal" if score >= 70 else "inverse"
        st.metric("🏆 Overall Score", f"{score:.0f}%",
                  delta="Above Pass Threshold" if score >= 70 else "Below Pass Threshold",
                  delta_color=delta_color)
    with c2:
        st.metric("📋 Checklist (40%)", f"{data['rules_score']:.0f}%")
    with c3:
        st.metric("🧠 AI Quality (60%)", f"{data['llm_score']:.0f}%")

    # PDF Download
    from core.report_generator import generate_pdf_report
    pdf_bytes = generate_pdf_report(data)
    st.download_button(
        "📥 Download PDF Report",
        data=pdf_bytes,
        file_name=f"VisionBoard_ResumeX_Report_{data['candidate_name']}.pdf",
        mime='application/pdf',
        use_container_width=True
    )

    # Document preview + parsed text
    with st.expander("📄 View Uploaded Resume & Parsed Text"):
        tab_visual, tab_text = st.tabs(["📄 Document Preview", "📝 Parsed Text"])

        with tab_visual:
            if st.session_state.get('last_file_bytes'):
                ext = st.session_state.get('last_file_ext', 'pdf')
                if ext == 'pdf':
                    import base64
                    b64 = base64.b64encode(st.session_state['last_file_bytes']).decode('utf-8')
                    st.markdown(
                        f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="800" type="application/pdf"></iframe>',
                        unsafe_allow_html=True
                    )
                elif ext in ['png', 'jpg', 'jpeg']:
                    st.image(st.session_state['last_file_bytes'], use_column_width=True)
                elif ext == 'docx':
                    st.info("DOCX visual preview is not supported. The text has been parsed successfully below.")
            else:
                st.info("File not cached.")

        with tab_text:
            st.caption("This is the raw text extracted from your resume by the parser. Verify it matches what you see in the document.")
            parsed = st.session_state.get('last_parsed_data')
            text_to_show = (
                parsed.get('text_content', '') if parsed
                else data.get('llm_output', {}).get('analysis', 'Parsed text not available — re-upload to view.')
            )
            st.text_area("Extracted Text", value=text_to_show, height=400, disabled=True)

    # Eligibility Checklist
    st.subheader("✅ Eligibility Checklist — Full Scan")
    checklist_scan = data.get('checklist_scan', [])
    violations = data['rule_violations']

    if checklist_scan:
        import pandas as pd
        scan_rows = []
        for row in checklist_scan:
            status = row.get('status', 'UNKNOWN')
            icon = "✅" if status == "PASS" else "❌"
            scan_rows.append({
                "Status": f"{icon} {status}",
                "Rule ID": row.get('rule_id', 'N/A'),
                "Rule": row.get('description', 'N/A'),
                "Details": row.get('details', ''),
            })
        st.dataframe(pd.DataFrame(scan_rows), hide_index=True, use_container_width=True)
    else:
        st.info("No checklist scan available for this run.")

    st.subheader("🚨 Violations Summary")
    if not violations:
        st.success("✅ Clean Pass! No rule violations detected.")
    else:
        for v in violations:
            st.error(f"**{v['rule_id']}**: {v['violation_message']}")

    # AI Intelligence Tabs
    st.subheader("🧠 AI Intelligence")
    t1, t2, t3 = st.tabs(["📊 Scores", "🔍 Insights", "🎯 Coaching"])

    with t1:
        import pandas as pd
        scores_data = data.get('section_scores', {})
        if isinstance(scores_data, dict) and scores_data:
            df_scores = pd.DataFrame(
                list(scores_data.items()), columns=['Category', 'Score (out of 10)']
            ).set_index('Category')
            st.bar_chart(df_scores, use_container_width=True)
            st.caption("Section scores are out of 10, generated by GPT-4o.")
        else:
            st.info("Section scores not available.")

    with t2:
        st.markdown("### 🔍 Model Analysis")
        analysis_text = data['llm_output'].get('analysis', 'No detailed analysis provided.')
        st.write(analysis_text)
        st.divider()
        st.info("**Strengths**")
        for s in data['llm_output'].get('strengths', []):
            st.write(f"• {s}")
        st.warning("**Gaps**")
        for g in data['llm_output'].get('gaps', []):
            st.write(f"• {g}")

    with t3:
        improvements = data.get('improvements', [])
        rewrite_suggestions = data.get('llm_output', {}).get('rewrite_suggestions', {})

        if not improvements:
            st.info("No coaching actions generated.")

        for idx, imp in enumerate(improvements, start=1):
            prio = imp.get('priority', 'Medium')
            section = imp.get('section', 'General')
            issue = imp.get('issue', 'Not specified')
            suggestion = imp.get('suggestion', 'No suggestion provided')
            icon = "🔴" if prio == "High" else ("🟠" if prio == "Medium" else "🟢")

            with st.expander(f"{icon} {idx}. {section} | Priority: {prio}"):
                st.markdown(f"**Issue observed:** {issue}")
                st.markdown(f"**Recommended fix:** {suggestion}")
                rewrite = None
                if isinstance(rewrite_suggestions, dict):
                    rewrite = rewrite_suggestions.get(section) or rewrite_suggestions.get(section.lower())
                if rewrite:
                    st.markdown("**Suggested rewrite:**")
                    st.code(str(rewrite), language="text")
