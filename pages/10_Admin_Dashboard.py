import json
import os
import sys

import pandas as pd
import streamlit as st

# Add root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core.auth import record_admin_login, verify_admin_credentials
from core.config import Config
from core.db import (
    delete_submission,
    get_all_submissions,
    get_submission_by_id,
    update_human_label,
)

st.set_page_config(page_title="Admin Portal", page_icon="🔐", layout="wide")


RULE_WHY = {
    "R001_FILENAME": "A standard naming convention helps ATS and reviewers map role and candidate quickly.",
    "R002_MANDATORY_SECTIONS": "Core sections are required for standardized recruiter review.",
    "R004_MANDATORY_KEYWORDS": "Role-specific technologies must be present for shortlisting.",
    "R006_CERTIFICATIONS": "Relevant certifications improve confidence in role readiness.",
    "R008_DETAIL_DEPTH": "Detailed impact bullets are needed to assess depth of execution.",
    "R009_HIGHLIGHT_CHECK": "Highlighting key skills improves resume scanability.",
}


def _safe_json_loads(value, fallback):
    if isinstance(value, dict):
        return value
    if not value:
        return fallback
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed
        except Exception:
            return fallback
    return fallback


def _prepare_dataframe(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    for col in ["overall_score", "rules_score", "llm_score"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    if "uploaded_at" in df.columns:
        df["uploaded_at"] = pd.to_datetime(df["uploaded_at"], errors="coerce")

    return df


def _violation_counts(df):
    if df.empty or "rule_violations_json" not in df.columns:
        return pd.Series(dtype="int64")

    counts = {}
    for raw in df["rule_violations_json"].tolist():
        violations = _safe_json_loads(raw, [])
        if isinstance(violations, list):
            for v in violations:
                rule_id = v.get("rule_id", "UNKNOWN")
                counts[rule_id] = counts.get(rule_id, 0) + 1

    if not counts:
        return pd.Series(dtype="int64")
    return pd.Series(counts).sort_values(ascending=False)


if "admin_logged_in" not in st.session_state:
    st.session_state["admin_logged_in"] = False

if not st.session_state["admin_logged_in"]:
    st.title("🔐 Admin Login")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")

            if submit:
                if verify_admin_credentials(username, password):
                    st.session_state["admin_logged_in"] = True
                    st.session_state["admin_username"] = username
                    record_admin_login(username)
                    st.success("Login Successful")
                    st.rerun()
                else:
                    st.error("Invalid credentials. Configure ADMIN_PASSWORD_HASH or seed the admins table.")
    st.stop()

with st.sidebar:
    st.write(f"Logged in as {st.session_state.get('admin_username', Config.ADMIN_USERNAME)}")
    if st.button("Logout"):
        st.session_state["admin_logged_in"] = False
        st.session_state.pop("admin_username", None)
        st.rerun()

tab_dashboard, tab_analytics, tab_checklist = st.tabs(["📊 Dashboard", "📈 Analytics", "📝 Checklist Sync"])

rows = get_all_submissions()
df_all = _prepare_dataframe(rows)

with tab_dashboard:
    st.title("📊 Admin Dashboard")

    if df_all.empty:
        st.info("No submissions found.")
    else:
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Submissions", len(df_all))
        k2.metric("Avg Score", f"{df_all['overall_score'].mean():.1f}")
        k3.metric("Compliance", f"{df_all['rules_score'].mean():.1f}")
        k4.metric("Quality", f"{df_all['llm_score'].mean():.1f}")

        st.divider()
        with st.expander("📈 Quick Statistics", expanded=True):
            s1, s2 = st.columns(2)
            with s1:
                st.caption("Score Distribution")
                chart_data = df_all[["candidate_name", "overall_score"]].set_index("candidate_name")
                st.bar_chart(chart_data)
            with s2:
                st.caption("Recent Activity")
                daily = (
                    df_all.dropna(subset=["uploaded_at"])
                    .set_index("uploaded_at")
                    .resample("D")
                    .size()
                )
                st.line_chart(daily)

        st.divider()
        st.subheader("Submission History")

        editable = df_all.copy()
        editable["Select"] = False
        keep_cols = [
            "Select",
            "human_label",
            "uploaded_at",
            "candidate_name",
            "vendor_name",
            "overall_score",
            "id",
        ]
        editable = editable[[c for c in keep_cols if c in editable.columns]]

        edited = st.data_editor(
            editable,
            column_config={
                "Select": st.column_config.CheckboxColumn("Select", default=False),
                "human_label": st.column_config.TextColumn("Rating", help="Admin Feedback"),
                "id": None,
            },
            hide_index=True,
            use_container_width=True,
        )

        labels_before = editable[["id", "human_label"]].set_index("id")
        labels_after = edited[["id", "human_label"]].set_index("id")
        changed_labels = labels_after[labels_after["human_label"] != labels_before["human_label"]]
        if not changed_labels.empty and st.button("💾 Save Ratings"):
            for submission_id, row in changed_labels.iterrows():
                update_human_label(submission_id, row["human_label"])
            st.success(f"Updated {len(changed_labels)} rating(s).")
            st.rerun()

        selected_rows = edited[edited["Select"]]
        if not selected_rows.empty:
            if st.button(f"🗑️ Delete {len(selected_rows)}"):
                for _, row in selected_rows.iterrows():
                    delete_submission(row["id"])
                st.success("Selected submissions deleted.")
                st.rerun()

        st.divider()
        st.subheader("🔍 Deep Dive")
        options = {
            f"{r.get('candidate_name', 'Unknown')} ({r.get('overall_score', 0)})": r["id"]
            for r in rows
        }
        selected = st.selectbox("Select Candidate", options=list(options.keys()))

        if selected:
            detail = get_submission_by_id(options[selected])
            if detail:
                c1, c2 = st.columns([1, 1])
                with c1:
                    st.info(f"File: {detail.get('resume_filename_original', 'N/A')}")
                    st.write(f"Uploaded: {detail.get('uploaded_at', 'N/A')}")
                    st.write(f"Vendor: {detail.get('vendor_name', 'N/A')}")

                    st.subheader("Rule Violations")
                    violations = _safe_json_loads(detail.get("rule_violations_json"), [])
                    if violations:
                        for violation in violations:
                            rule_id = violation.get("rule_id", "UNKNOWN")
                            msg = violation.get("violation_message", "No details")
                            why = RULE_WHY.get(rule_id, "Compliance with this rule is mandatory.")
                            with st.expander(f"{rule_id}", expanded=False):
                                st.error(f"Issue: {msg}")
                                st.info(f"Why this matters: {why}")
                    else:
                        st.success("No violations detected")

                with c2:
                    st.subheader("AI Quality Analysis")
                    llm_output = _safe_json_loads(detail.get("llm_output_json"), {})
                    section_scores = llm_output.get("section_scores", {})
                    if isinstance(section_scores, dict) and section_scores:
                        chart_df = pd.DataFrame(
                            list(section_scores.items()), columns=["Category", "Score"]
                        ).set_index("Category")
                        st.bar_chart(chart_df)
                    else:
                        st.info("No section scores available")

                    with st.expander("View Full AI Output"):
                        st.json(llm_output)

with tab_analytics:
    st.header("📈 Recruitment Analytics")

    if df_all.empty:
        st.info("No data available.")
    else:
        min_date = df_all["uploaded_at"].min().date() if df_all["uploaded_at"].notna().any() else None
        max_date = df_all["uploaded_at"].max().date() if df_all["uploaded_at"].notna().any() else None

        f1, f2, f3 = st.columns(3)
        with f1:
            date_range = st.date_input("Date Range", value=(min_date, max_date) if min_date and max_date else None)
        with f2:
            vendors = sorted([v for v in df_all.get("vendor_name", pd.Series(dtype=str)).dropna().unique().tolist() if v])
            vendor_filter = st.multiselect("Vendor", options=vendors, default=vendors)
        with f3:
            score_min = st.slider("Minimum Overall Score", min_value=0, max_value=100, value=0)

        df_filtered = df_all.copy()

        if isinstance(date_range, tuple) and len(date_range) == 2 and date_range[0] and date_range[1]:
            start_dt = pd.Timestamp(date_range[0])
            end_dt = pd.Timestamp(date_range[1]) + pd.Timedelta(days=1)
            df_filtered = df_filtered[(df_filtered["uploaded_at"] >= start_dt) & (df_filtered["uploaded_at"] < end_dt)]

        if vendor_filter:
            df_filtered = df_filtered[df_filtered["vendor_name"].isin(vendor_filter)]

        df_filtered = df_filtered[df_filtered["overall_score"] >= score_min]

        pass_count = len(df_filtered[df_filtered["overall_score"] >= 70])
        pass_rate = (pass_count / len(df_filtered) * 100) if len(df_filtered) else 0.0
        violations_series = _violation_counts(df_filtered)
        avg_violations = violations_series.sum() / len(df_filtered) if len(df_filtered) else 0.0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Candidates", len(df_filtered))
        k2.metric("Pass Rate", f"{pass_rate:.1f}%")
        k3.metric("Avg Score", f"{df_filtered['overall_score'].mean():.1f}" if len(df_filtered) else "0.0")
        k4.metric("Avg Violations", f"{avg_violations:.1f}")

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Top Violated Rules")
            if not violations_series.empty:
                st.bar_chart(violations_series.head(10))
            else:
                st.info("No violations in filtered data.")

        with c2:
            st.subheader("Vendor Submission Volume")
            if "vendor_name" in df_filtered.columns:
                vendor_counts = df_filtered["vendor_name"].fillna("Unknown").value_counts()
                st.bar_chart(vendor_counts)
            else:
                st.info("Vendor field unavailable.")

        st.divider()

        c3, c4 = st.columns(2)
        with c3:
            st.subheader("📊 Score Distribution")
            if not df_filtered.empty:
                bins = pd.cut(
                    df_filtered["overall_score"],
                    bins=[0, 40, 60, 70, 80, 90, 100],
                    labels=["0–40", "40–60", "60–70", "70–80", "80–90", "90–100"],
                )
                dist_df = (
                    bins.value_counts().sort_index()
                    .rename_axis("Score Range")
                    .reset_index(name="Candidates")
                )
                st.bar_chart(dist_df.set_index("Score Range"))
            else:
                st.info("No data for score distribution.")

        with c4:
            st.subheader("🏢 Avg Score by Vendor")
            if "vendor_name" in df_filtered.columns and not df_filtered.empty:
                vendor_avg = (
                    df_filtered.groupby("vendor_name")["overall_score"]
                    .mean()
                    .sort_values(ascending=False)
                    .rename_axis("Vendor")
                    .reset_index(name="Avg Overall %")
                )
                st.bar_chart(vendor_avg.set_index("Vendor"))
                st.caption("Higher avg = vendor submissions generally score better against the checklist.")
            else:
                st.info("Vendor data unavailable.")

        st.subheader("Filtered Submissions")
        st.dataframe(
            df_filtered[[c for c in ["uploaded_at", "candidate_name", "vendor_name", "rules_score", "llm_score", "overall_score"] if c in df_filtered.columns]],
            use_container_width=True,
        )

        csv = df_filtered.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", csv, "hiresense_data_filtered.csv", "text/csv", use_container_width=True)

with tab_checklist:
    st.header("Checklist Management")
    st.info("Sync the latest rules from the Vision Board Google Doc.")

    if st.button("🔄 Sync Now"):
        with st.spinner("Fetching from Google Docs..."):
            try:
                from checklist.parser_google_doc import GoogleDocParser
                from core.db import save_checklist_version

                parser = GoogleDocParser()
                result = parser.fetch_and_parse()

                if result:
                    save_checklist_version(Config.GOOGLE_DOC_ID, result["rules"], result["hash"])
                    st.success("Rules saved to database and activated.")
                    st.json(result["rules"])
                else:
                    st.error("Failed to fetch Google Doc content.")
            except Exception as e:
                st.error(f"Sync Error: {e}")
