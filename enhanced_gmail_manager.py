import pickle
import os
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class EnhancedGmailManager:
    """Enhanced Gmail manager with read, delete, and management capabilities"""
    
    # Updated scopes to include modification capabilities
    SCOPES = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.modify',
        'https://www.googleapis.com/auth/gmail.labels',
        'https://mail.google.com/'
    ]
    
    def __init__(self, credentials_file: str = 'client_secret.json', token_file: str = 'token.pickle'):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = None
        self.user_email = None
        self.authenticated = False
        # Authenticate on initialization, but allow it to fail gracefully
        try:
            self.authenticate()
        except Exception as e:
            logger.error(f"Initial Gmail authentication failed: {e}")
    
    def authenticate(self):
        """Authenticate with Gmail API using a fixed port"""
        creds = None
        
        # Load existing token
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, 'rb') as token:
                    creds = pickle.load(token)
                logger.info("Loaded existing credentials from token file")
            except Exception as e:
                logger.error(f"Error loading token file {self.token_file}: {e}")
                # Delete corrupted token file
                try:
                    os.remove(self.token_file)
                    logger.info("Deleted corrupted token file")
                except:
                    pass
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            try:
                if creds and creds.expired and creds.refresh_token:
                    logger.info("Refreshing expired credentials...")
                    creds.refresh(Request())
                else:
                    logger.info("Getting new credentials...")
                    if not os.path.exists(self.credentials_file):
                        raise FileNotFoundError(f"Credentials file {self.credentials_file} not found")
                    
                    # Verify credentials file format
                    self._verify_credentials_file()
                    
                    flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
                    
                    # Manual authentication in environments that cannot open a browser
                    auth_url, _ = flow.authorization_url(prompt='consent')
                    logger.info(f"Authentication URL: {auth_url}")
                    # Ask user to visit the URL and provide the authorization code
                    # This will be handled in Streamlit by inputting the code
                    return auth_url  # Return the URL so Streamlit can handle it
                    
                    # If you're not using Streamlit, use this for the browser flow:
                    # creds = flow.run_local_server(port=0)
                
                # Save credentials for next run
                with open(self.token_file, 'wb') as token:
                    pickle.dump(creds, token)
                logger.info("Saved new credentials to token file")
                
            except Exception as e:
                logger.error(f"Authentication failed: {e}")
                raise
        
        try:
            self.service = build('gmail', 'v1', credentials=creds)
            
            # Get user email
            profile = self.service.users().getProfile(userId='me').execute()
            self.user_email = profile['emailAddress']
            self.authenticated = True
            logger.info(f"Gmail API authenticated successfully for {self.user_email}")
            
        except Exception as e:
            logger.error(f"Error initializing Gmail service or getting user profile: {e}")
            self.authenticated = False
            raise
    
    def authenticate_with_code(self, authorization_code: str) -> bool:
        """Authenticate using the provided authorization code"""
        try:
            flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
            
            # Exchange the authorization code for credentials
            creds = flow.fetch_token(authorization_response=authorization_code)
            
            # Save credentials for future use
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)
            logger.info("Saved new credentials to token file")
            
            self.service = build('gmail', 'v1', credentials=creds)
            profile = self.service.users().getProfile(userId='me').execute()
            self.user_email = profile['emailAddress']
            self.authenticated = True
            logger.info(f"Gmail API authenticated successfully for {self.user_email}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to authenticate with the provided code: {e}")
            return False
    
    def is_authenticated(self) -> bool:
        """Check if the Gmail manager is authenticated"""
        return self.authenticated and self.service is not None
    
    def _verify_credentials_file(self):
        """Verify the credentials file has the correct format"""
        try:
            with open(self.credentials_file, 'r') as f:
                creds_data = json.load(f)
            
            # Check if it's a desktop app credentials file
            if 'installed' not in creds_data:
                if 'web' in creds_data:
                    raise ValueError("Credentials file is for a web application. Please create a desktop application in Google Cloud Console.")
                else:
                    raise ValueError("Invalid credentials file format")
            
            required_fields = ['client_id', 'client_secret', 'auth_uri', 'token_uri']
            installed_section = creds_data['installed']
            
            for field in required_fields:
                if field not in installed_section:
                    raise ValueError(f"Missing required field '{field}' in credentials file")
            
            logger.info("Credentials file format verified successfully")
            
        except json.JSONDecodeError:
            raise ValueError("Credentials file is not valid JSON")
        except FileNotFoundError:
            raise FileNotFoundError(f"Credentials file {self.credentials_file} not found")
    
    # Other Gmail API management functions like search_emails, get_email_content, etc.
