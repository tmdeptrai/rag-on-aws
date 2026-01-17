import boto3
from botocore.exceptions import ClientError
import streamlit as st
import os
from dotenv import load_dotenv
load_dotenv()

if 'cognito_client' not in st.session_state:
    st.session_state.cognito_client = boto3.client(
        'cognito-idp',
        region_name=os.getenv("AWS_REGION")
    )

CLIENT_ID = os.getenv("COGNITO_APP_CLIENT_ID")

def register(email, password) -> list[bool, str]:
    try:
        st.session_state.cognito_client.sign_up(
            ClientId=CLIENT_ID,
            Username=email,
            Password=password,
            UserAttributes=[{'Name': 'email', 'Value': email}]
        )
        return True, "Success! Check email for code."
    except ClientError as e:
        return False, e.response['Error']['Message']

def verify(email, code) -> list[bool, str]:
    try:
        st.session_state.cognito_client.confirm_sign_up(
            ClientId=CLIENT_ID,
            Username=email,
            ConfirmationCode=code
        )
        return True, "Account verified! You can now log in."
    except ClientError as e:
        return False, e.response['Error']['Message']

def login(email, password) -> list[bool, str]:
    try:
        response = st.session_state.cognito_client.initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters={'USERNAME': email, 'PASSWORD': password}
        )
        # Store tokens securely in session state
        return True, response['AuthenticationResult']
    except ClientError as e:
        return False, e.response['Error']['Message']

def forgot_password(email) -> list[bool, str]:
    try:
        st.session_state.cognito_client.forgot_password(
            ClientId=CLIENT_ID,
            Username=email
        )
        return True, "Password reset code sent."
    except ClientError as e:
        return False, e.response['Error']['Message']

def confirm_forgot_password(email, code, new_password) -> list[bool, str]:
    try:
        st.session_state.cognito_client.confirm_forgot_password(
            ClientId=CLIENT_ID,
            Username=email,
            ConfirmationCode=code,
            Password=new_password
        )
        return True, "Password changed successfully."
    except ClientError as e:
        return False, e.response['Error']['Message']