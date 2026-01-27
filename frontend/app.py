import os
import time
from dotenv import load_dotenv
load_dotenv()
import streamlit as st
import boto3
from botocore.exceptions import ClientError
import extra_streamlit_components as stx

import auth_client
from files_handler import upload_to_s3, show_document_sidebar
from api import query_rag_bot
st.set_page_config(page_title="RAG-on-aws", page_icon="🤖")

if 'cognito_client' not in st.session_state:
    st.session_state.cognito_client = boto3.client(
        'cognito-idp',
        region_name=os.getenv("AWS_REGION")
    )

if 's3_client' not in st.session_state:
    st.session_state.s3_client = boto3.client(
        's3',
        region_name = os.getenv("AWS_REGION"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
    )

BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# --- SESSION STATE SETUP ---
if "token" not in st.session_state:
    st.session_state.token = None
if "auth_view" not in st.session_state:
    st.session_state.auth_view = "login"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "announcement" not in st.session_state:
    st.session_state.announcement = ""

# --- HELPER FUNCTIONS ---
cookie_manager = stx.CookieManager(key="cookie_manager")

def switch_view(view_name):
    st.session_state.auth_view = view_name
    st.rerun()

def logout():
    st.session_state.token = None
    st.session_state.user_email = None
    st.session_state.auth_view = "login"
    st.session_state.messages = []
    
    st.session_state['logout_pending'] = True
    
    st.rerun()

def login_view():
    st.subheader("Login")
    
    if st.session_state.announcement:
        st.info(st.session_state.announcement)
        
    email = st.text_input("Email", key="login_email")
    password = st.text_input("Password", type="password", key="login_pass")
    
    col1, col2, col3 = st.columns([1, 1, 1.5])
    
    if col1.button("Login"):        
        if email and password:
            success, result = auth_client.login(email, password)
            if success:
                token = result['AccessToken']

                st.session_state.token = token
                cookie_manager.set('auth_token',token,key="set_auth_token")
                
                st.session_state.user_email = email # Store for S3 folder path
                st.success("Logged in!")
                
                time.sleep(2)
                
                st.rerun() # Trigger reload to show Home Page
            else:
                st.error(result)
        else:
            st.warning("Please fill in all fields")

    if col2.button("Register"): switch_view("register")
    if col3.button("Forgot Password?"): switch_view("forgot")

def register_view():
    st.subheader("Create Account")
    new_email = st.text_input("Email", key="register_email")
    new_pass = st.text_input("Password", type="password", key="register_pass")
    confirm_password = st.text_input("Confirm Password", type="password", key="register_confirm_pass")
    
    if st.button("Sign Up"):
        if new_pass != confirm_password:
            st.warning("Passwords did not match, try again")
        else:
            success, msg = auth_client.register(new_email, new_pass)
            if success:
                st.success(msg)
                st.session_state.pending_email = new_email
                st.session_state.announcement = f"A verification code has been sent to {new_email}"
                switch_view("verify")
            else:
                st.error(msg)
    if st.button("Back"): switch_view("login")

def verify_view():
    st.subheader("Verify Account")
    st.info(st.session_state.announcement)
    email = st.session_state.get("pending_email", "")
    code = st.text_input("Verification Code")
    
    if st.button("Confirm"):
        success, msg = auth_client.verify(email, code)
        if success:
            st.success(msg)
            st.session_state.announcement = f"Your email has been confirmed, you can now log in."
            switch_view("login")
        else:
            st.error(msg)
    if st.button("Back"): switch_view("login")

def forgot_password_view():
    st.subheader("Reset Password")
    email = st.text_input("Email")
    
    if st.button("Send Reset Code"):
        success, msg = auth_client.forgot_password(email)
        if success:
            st.info(msg)
            st.session_state.pending_email = email
            st.session_state.announcement = f"A verification code has been sent to {email}"
            
            switch_view("confirm_forgot")
        else:
            st.error(msg)
    if st.button("Back"): switch_view("login")

def confirm_forgot_view():
    st.subheader("Set New Password")
    st.info(st.session_state.announcement)
    email = st.session_state.get("pending_email", "")
    code = st.text_input("Verification Code")
    new_pass = st.text_input("New Password", type="password")
    confirm_new_pass = st.text_input("Confirm New Password", type="password")
    
    if st.button("Change Password"):
        if new_pass == confirm_new_pass:
            success, msg = auth_client.confirm_forgot_password(email, code, new_pass)
            if success:
                st.success("Password changed! Please login.")
                st.session_state.announcement = f"Your password has been successfully updated."
                switch_view("login")
            else:
                st.error(msg)
    if st.button("Back"): switch_view("login")

def home_page():
    st.sidebar.title("RAG Chatbot")
    st.sidebar.caption(f"User: {st.session_state.get('user_email')}")
    show_document_sidebar()
    
    # --- Sidebar: Upload ---
    st.sidebar.divider()
    st.sidebar.header("Upload Document")
    uploaded_file = st.sidebar.file_uploader("Choose PDF", type="pdf")
    if uploaded_file and st.sidebar.button("Upload"):
        with st.spinner("Uploading..."):
            success, msg = upload_to_s3(uploaded_file)
            if success:
                st.sidebar.success(msg)
            else:
                st.sidebar.error(msg)
            pass
    
    st.sidebar.divider()
    if st.sidebar.button("Logout"):
        logout()

    # --- Main Chat UI ---
    st.title("📚 Document Assistant")

    # Display Chat History
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            # Optional: If you saved references in history, you could show them here too

    # Chat Input
    if prompt := st.chat_input("Ask a question..."):
        # 1. User Message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 2. Bot Response
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.markdown("🔍 *Searching Knowledge Graph & Vector DB...*")
            
            # --- CALL THE API ---
            user_email = st.session_state.get('user_email', 'default_user')
            
            # Pass the full session state messages so the bot has context
            data = query_rag_bot(prompt, user_email, st.session_state.messages)
            
            # --- HANDLE RESPONSE ---
            if "error" in data:
                message_placeholder.error(data["error"])
            else:
                answer = data.get("answer", "No answer found.")
                references = data.get("references", [])
                
                # A. Show the Answer
                message_placeholder.markdown(answer)
                
                # B. Show the Sources (The "Magic" Part)
                if references:
                    with st.expander(f"📚 Cited {len(references)} Sources (Vector + Graph)"):
                        for i, ref in enumerate(references):
                            # Icons for visual flair
                            icon = "🕸️" if ref['type'] == 'graph' else "📄"
                            score_val = float(ref.get('score', 0))
                            color = "green" if score_val > 0.8 else "orange"
                            
                            st.markdown(f"**{i+1}. {icon} {ref['type'].title()}** <span style='color:{color}'>({score_val:.2f})</span>", unsafe_allow_html=True)
                            st.caption(f"Source: *{ref['source']}*")
                            st.code(ref['content'], language="text")
                            st.divider()

                # C. Save to History
                # We save the plain answer to history. 
                # (Saving references to session_state is complex, so we skip it for now)
                st.session_state.messages.append({"role": "assistant", "content": answer})
# --- MAIN ROUTER ---
# CASE A: We are in the middle of a logout
if st.session_state.get('logout_pending'):
    try:
        cookie_manager.delete('auth_token')
    except KeyError:
        pass
    
    del st.session_state['logout_pending']
    
    st.title("RAG on AWS")
    login_view()


# CASE B: We are logged in (Session State exists)
elif st.session_state.token:
    home_page()


# CASE C: We are not logged in, check for cookies (Auto-Login)
else:
    cookies = cookie_manager.get_all()
    cookie_token = cookies.get("auth_token")

    if cookie_token:
        is_valid, email = auth_client.check_token(cookie_token)
        
        if is_valid:
            st.session_state.token = cookie_token
            st.session_state.user_email = email
            st.rerun() # Success! Reload to show Home Page
        else:
            # Token invalid -> Delete it
            try:
                cookie_manager.delete("auth_token")
            except KeyError:
                pass

    # 2. If no valid cookie, show Login
    st.title("RAG on AWS")
    if st.session_state.auth_view == "login":
        login_view()
    elif st.session_state.auth_view == "register":
        register_view()
    elif st.session_state.auth_view == "verify":
        verify_view()
    elif st.session_state.auth_view == "forgot":
        forgot_password_view()
    elif st.session_state.auth_view == "confirm_forgot":
        confirm_forgot_view()