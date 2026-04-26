import streamlit as st
import time

st.set_page_config(
    page_title="Vision Board Resume X",
    page_icon="🧠",
    layout="wide"
)

# Custom CSS — explicit colours prevent invisible text on Streamlit Cloud
st.markdown("""
    <style>
    /* Force a readable background and text colour regardless of Cloud theme */
    .stApp {
        background-color: #f7f9fc;
    }
    .stApp, .stApp p, .stApp li, .stApp label, .stApp span,
    .stMarkdown, .stMarkdown p, .stMarkdown li {
        color: #1a1a1a !important;
    }
    h1, h2, h3, h4, h5, h6 {
        color: #1a1a1a !important;
    }
    /* Green submit / action buttons */
    .stButton>button, .stFormSubmitButton>button {
        background-color: #4CAF50;
        color: #ffffff !important;
        border-radius: 8px;
        border: none;
    }
    .stButton>button:hover, .stFormSubmitButton>button:hover {
        background-color: #43a047;
        color: #ffffff !important;
    }
    /* Info / warning / success boxes */
    .stAlert p { color: #1a1a1a !important; }
    /* Page link labels */
    [data-testid="stPageLink"] span { color: #1a1a1a !important; }
    /* Metric labels */
    [data-testid="stMetricLabel"] { color: #444 !important; }
    [data-testid="stMetricValue"] { color: #1a1a1a !important; }
    </style>
    """, unsafe_allow_html=True)

# --- Splash Screen Logic ---
if "splash_done" not in st.session_state:
    st.session_state.splash_done = False

if not st.session_state.splash_done:
    st.markdown("<br><br><br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.image("logo.jpg", width=250)
        st.markdown("<h2 style='text-align: center;'>Loading Vision Board Resume X...</h2>", unsafe_allow_html=True)
        with st.spinner("Initializing models..."):
            time.sleep(2.5)
    st.session_state.splash_done = True
    st.rerun()

# --- Authentication Logic ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "show_forgot_password" not in st.session_state:
    st.session_state.show_forgot_password = False

def login():
    # Accept any demo credentials for now
    if st.session_state.username and st.session_state.password:
        st.session_state.logged_in = True
    else:
        st.error("Please enter both username and password")

def logout():
    st.session_state.logged_in = False
    st.session_state.show_forgot_password = False

def toggle_forgot_password():
    st.session_state.show_forgot_password = not st.session_state.show_forgot_password

def send_reset_link():
    if st.session_state.reset_email:
        st.success(f"Password reset link sent to {st.session_state.reset_email}")
        time.sleep(2)
        st.session_state.show_forgot_password = False
    else:
        st.error("Please enter a valid email address.")

if not st.session_state.logged_in:
    # Display Auth Flow
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image("logo.jpg", width=150)
        st.title("Vision Board Resume X")
        st.markdown("### Login to access the Evaluation Engine")
        
        if not st.session_state.show_forgot_password:
            # Login Form
            with st.form("login_form"):
                st.text_input("Username", key="username")
                st.text_input("Password", type="password", key="password")
                col_submit, col_forgot = st.columns([1, 1])
                with col_submit:
                    st.form_submit_button("Login", on_click=login, use_container_width=True)
            st.button("Forgot Password?", on_click=toggle_forgot_password, use_container_width=True)
        else:
            # Forgot Password Form
            st.info("Enter your email address to receive a password reset link.")
            with st.form("forgot_password_form"):
                st.text_input("Email Address", key="reset_email")
                st.form_submit_button("Send Reset Link", on_click=send_reset_link, use_container_width=True)
            st.button("Back to Login", on_click=toggle_forgot_password, use_container_width=True)
else:
    # --- Main Application Dashboard ---
    col_title, col_logout = st.columns([4, 1])
    with col_title:
        st.image("logo.jpg", width=100)
        st.title("Vision Board Resume X")
        st.markdown("### Intelligent Resume Evaluation & Compliance Engine")
    with col_logout:
        st.button("Logout", on_click=logout, use_container_width=True)

    st.info("Welcome to the automated resume auditor for Vision Board candidates.")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 📄 For HR & Recruiters")
        st.write("Upload and evaluate resumes instantly against the Azure Data Engineer compliance checklist.")

        st.page_link("pages/1_User_Upload.py",  label="🚀 Single Upload",  icon="📄")
        st.page_link("pages/2_Batch_Upload.py", label="📦 Batch Upload (ZIP / Multi-file)", icon="📦")
        st.page_link("pages/3_Compare_Candidates.py", label="⚖️ Compare Candidates Side-by-Side", icon="⚖️")

    with col2:
        st.markdown("#### 🔐 For Admins")
        st.write("Monitor submissions, analyze violation trends, manage compliance rules, and export data.")
        st.page_link("pages/10_Admin_Dashboard.py", label="🔐 Admin Portal", icon="📊")

    st.divider()
    st.caption("Powered by GPT-5 + Deterministic Rules Engine | v1.1 — Batch Upload · Comparison · WAL Mode")
