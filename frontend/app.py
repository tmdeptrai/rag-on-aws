import os
import time
from dotenv import load_dotenv
load_dotenv()
import streamlit as st
import boto3
from botocore.exceptions import ClientError
import extra_streamlit_components as stx

import auth_client

# # --- CONFIGURATION ---
# # Replace with your actual Lambda URL (from your deployment)
# API_BASE_URL = "https://example-id.lambda-url.us-east-1.on.aws/" 
# BUCKET_NAME = "your-bucket-name" # Update this!

st.set_page_config(page_title="RAG-on-aws", page_icon="🤖")

if 'cognito_client' not in st.session_state:
    st.session_state.cognito_client = boto3.client(
        'cognito-idp',
        region_name=os.getenv("AWS_REGION")
    )

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

# def upload_to_s3(file_obj):
#     """Uploads file using direct S3 access (easiest for V1)"""
#     try:
#         s3 = boto3.client('s3', region_name=st.secrets["AWS_REGION"])
#         user_email = st.session_state.get('user_email', 'unknown')
#         # Structure: documents/email/filename
#         key = f"documents/{user_email}/{file_obj.name}"
        
#         s3.upload_fileobj(file_obj, BUCKET_NAME, key)
#         return True, "File uploaded! AI is processing it..."
#     except Exception as e:
#         return False, str(e)

# --- VIEWS ---

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
    
    # --- Sidebar: Upload ---
    st.sidebar.divider()
    st.sidebar.header("Upload Document")
    uploaded_file = st.sidebar.file_uploader("Choose PDF", type="pdf")
    if uploaded_file and st.sidebar.button("Upload"):
        with st.spinner("Uploading..."):
            # success, msg = upload_to_s3(uploaded_file)
            # if success:
            #     st.sidebar.success(msg)
            # else:
            #     st.sidebar.error(msg)
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

    # Chat Input
    if prompt := st.chat_input("Ask a question..."):
        # 1. User Message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 2. Bot Response (Simulated)
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Thinking...")
            
            try:
                # UNCOMMENT THIS WHEN LAMBDA IS READY
                # response = requests.post(
                #     API_BASE_URL,
                #     json={"question": prompt},
                #     headers={"Authorization": f"Bearer {st.session_state.token}"}
                # )
                # answer = response.json().get("answer", "Error from API")
                
                # Mock response for UI testing
                import time
                time.sleep(1) 
                answer = "I am a placeholder bot. Connect your Lambda API to make me smart!" 
                
                message_placeholder.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except Exception as e:
                message_placeholder.error(f"Connection Error: {e}")

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
            st.rerun()
        else:
            # Token invalid -> Delete it
            try:
                cookie_manager.delete("auth_token")
            except KeyError:
                pass

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