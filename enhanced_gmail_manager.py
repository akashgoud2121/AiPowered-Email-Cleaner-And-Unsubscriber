import pickle
import os
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import json
from datetime import datetime,timedelta
import base64
from typing import List, Dict, Optional, Tuple
import tempfile
logger = logging.getLogger(__name__)

class EnhancedGmailManager:
    """Enhanced Gmail manager with read, delete, and management capabilities"""
    
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
        try:
            self.authenticate()
        except Exception as e:
            logger.error(f"Initial Gmail authentication failed: {e}")
    
    def authenticate(self):
        """Authenticate with Gmail API using existing token or credentials file"""
        creds = None
        
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, 'rb') as token:
                    creds = pickle.load(token)
                logger.info("Loaded existing credentials from token file")
            except Exception as e:
                logger.error(f"Error loading token file {self.token_file}: {e}")
                try:
                    os.remove(self.token_file)
                    logger.info("Deleted corrupted token file")
                except:
                    pass
        
        if not creds or not creds.valid:
            try:
                if creds and creds.expired and creds.refresh_token:
                    logger.info("Refreshing expired credentials...")
                    creds.refresh(Request())
                    
                    # Save refreshed credentials
                    with open(self.token_file, 'wb') as token:
                        pickle.dump(creds, token)
                    logger.info("Refreshed and saved credentials")
                    
                else:
                    logger.info("Need new credentials...")
                    if not os.path.exists(self.credentials_file):
                        logger.warning(f"Credentials file {self.credentials_file} not found")
                        raise FileNotFoundError(f"Credentials file {self.credentials_file} not found")
                    
                    self._verify_credentials_file()
                    flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
                    auth_url, _ = flow.authorization_url(prompt='consent')
                    logger.info(f"Authentication URL: {auth_url}")
                    return auth_url  # Return the URL for manual authentication
                    
            except Exception as e:
                logger.error(f"Authentication failed: {e}")
                raise
        
        try:
            self.service = build('gmail', 'v1', credentials=creds)
            profile = self.service.users().getProfile(userId='me').execute()
            self.user_email = profile['emailAddress']
            self.authenticated = True
            logger.info(f"Gmail API authenticated successfully for {self.user_email}")
            
        except Exception as e:
            logger.error(f"Error initializing Gmail service or getting user profile: {e}")
            self.authenticated = False
            raise

    def authenticate_with_credentials(self, credentials_json: str) -> bool:
        """Authenticate using credentials JSON string"""
        try:
            # Parse the credentials JSON
            credentials_data = json.loads(credentials_json)
            
            # Create a temporary file for the credentials
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
                json.dump(credentials_data, temp_file)
                temp_credentials_file = temp_file.name
            
            try:
                # Verify the credentials format
                self._verify_credentials_file(temp_credentials_file)
                
                # Create flow and get authorization URL
                flow = InstalledAppFlow.from_client_secrets_file(temp_credentials_file, self.SCOPES)
                auth_url, _ = flow.authorization_url(prompt='consent')
                
                logger.info(f"Authentication URL generated: {auth_url}")
                
                # Store the temp file path and flow for later use
                self.temp_credentials_file = temp_credentials_file
                self.auth_flow = flow
                
                return auth_url
                
            finally:
                # Clean up temp file if we're done with it
                if hasattr(self, 'temp_credentials_file') and os.path.exists(temp_credentials_file):
                    # Don't delete yet - we need it for the flow
                    pass
                    
        except Exception as e:
            logger.error(f"Failed to authenticate with credentials: {e}")
            return False

    def complete_authentication_with_code(self, authorization_code: str) -> bool:
        """Complete authentication using the authorization code"""
        try:
            if not hasattr(self, 'auth_flow'):
                logger.error("No authentication flow found. Please call authenticate_with_credentials first.")
                return False
            
            # Exchange authorization code for credentials
            self.auth_flow.fetch_token(authorization_response=authorization_code)
            creds = self.auth_flow.credentials
            
            # Save credentials
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)
            logger.info("Saved new credentials to token file")
            
            # Initialize service
            self.service = build('gmail', 'v1', credentials=creds)
            profile = self.service.users().getProfile(userId='me').execute()
            self.user_email = profile['emailAddress']
            self.authenticated = True
            
            # Clean up temp file
            if hasattr(self, 'temp_credentials_file') and os.path.exists(self.temp_credentials_file):
                os.unlink(self.temp_credentials_file)
                delattr(self, 'temp_credentials_file')
            
            logger.info(f"Gmail API authenticated successfully for {self.user_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to complete authentication: {e}")
            return False

    def authenticate_with_code(self, authorization_code: str) -> bool:
        """Authenticate using the provided authorization code (legacy method)"""
        try:
            if not os.path.exists(self.credentials_file):
                logger.error(f"Credentials file {self.credentials_file} not found")
                return False
                
            flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
            flow.fetch_token(authorization_response=authorization_code)
            creds = flow.credentials
            
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
    
    def _verify_credentials_file(self, credentials_file: str = None):
        """Verify the credentials file has the correct format"""
        file_to_check = credentials_file or self.credentials_file
        
        try:
            with open(file_to_check, 'r') as f:
                creds_data = json.load(f)
            
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
            raise FileNotFoundError(f"Credentials file {file_to_check} not found")
    
    # Gmail API management functions
    def search_emails(self, query: str, max_results: int = 100) -> List[str]:
        """Search for emails matching the query"""
        if not self.is_authenticated():
            logger.error("Gmail manager is not authenticated")
            return []
            
        try:
            results = self.service.users().messages().list(
                userId='me', q=query, maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            return [msg['id'] for msg in messages]
            
        except Exception as e:
            logger.error(f"Error searching emails: {e}")
            return []

    def get_email_content(self, message_id: str) -> Dict:
        """Get full email content including headers and body"""
        if not self.is_authenticated():
            logger.error("Gmail manager is not authenticated")
            return {}
            
        try:
            message = self.service.users().messages().get(
                userId='me', id=message_id, format='full'
            ).execute()
            
            headers = {}
            for header in message['payload'].get('headers', []):
                headers[header['name'].lower()] = header['value']
            
            # Extract body
            body = self._extract_body(message['payload'])
            
            # Get email size and labels
            size_estimate = message.get('sizeEstimate', 0)
            labels = message.get('labelIds', [])
            
            return {
                'id': message_id,
                'thread_id': message.get('threadId'),
                'subject': headers.get('subject', ''),
                'from': headers.get('from', ''),
                'to': headers.get('to', ''),
                'date': headers.get('date', ''),
                'list_unsubscribe': headers.get('list-unsubscribe', ''),
                'body_html': body.get('html', ''),
                'body_text': body.get('text', ''),
                'headers': headers,
                'size_estimate': size_estimate,
                'labels': labels,
                'snippet': message.get('snippet', '')
            }
            
        except Exception as e:
            logger.error(f"Error getting email content: {e}")
            return {}
    
    def _extract_body(self, payload: Dict) -> Dict:
        """Extract HTML and text body from email payload"""
        body = {'html': '', 'text': ''}

        def extract_parts(part):
            if part.get('mimeType') == 'text/html':
                data = part.get('body', {}).get('data', '')
                if data:
                    try:
                        body['html'] += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    except Exception as e:
                        logger.error(f"Error decoding HTML body: {e}")
            
            elif part.get('mimeType') == 'text/plain':
                data = part.get('body', {}).get('data', '')
                if data:
                    try:
                        body['text'] += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    except Exception as e:
                        logger.error(f"Error decoding text body: {e}")
            
            # Handle multipart
            if 'parts' in part:
                for subpart in part['parts']:
                    extract_parts(subpart)

        extract_parts(payload)
        return body

    def get_emails_by_timeframe(self, days_back: int = 30, max_results: int = 500) -> List[Dict]:
        """Get emails from a specific timeframe"""
        if not self.is_authenticated():
            logger.error("Gmail manager is not authenticated")
            return []
            
        # Create date query
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # Gmail date format: YYYY/MM/DD
        date_query = f"after:{start_date.strftime('%Y/%m/%d')} before:{end_date.strftime('%Y/%m/%d')}"
        
        message_ids = self.search_emails(date_query, max_results)
        
        emails = []
        for i, msg_id in enumerate(message_ids):
            if i % 50 == 0:  # Progress logging
                logger.info(f"Fetching email {i+1}/{len(message_ids)}")
            
            email_content = self.get_email_content(msg_id)
            if email_content:
                emails.append(email_content)
        
        return emails
    
    def get_promotional_emails(self, days_back: int = 30, max_results: int = 200) -> List[Dict]:
        """Get promotional/marketing emails"""
        if not self.is_authenticated():
            logger.error("Gmail manager is not authenticated")
            return []
            
        queries = [
            f'category:promotions newer_than:{days_back}d',
            f'unsubscribe newer_than:{days_back}d',
            f'(marketing OR newsletter OR promotion) newer_than:{days_back}d'
        ]
        
        all_emails = []
        seen_ids = set()
        
        for query in queries:
            message_ids = self.search_emails(query, max_results // len(queries))
            
            for msg_id in message_ids:
                if msg_id not in seen_ids:
                    email_content = self.get_email_content(msg_id)
                    if email_content:
                        all_emails.append(email_content)
                        seen_ids.add(msg_id)
            
            if len(all_emails) >= max_results:
                break
        
        return all_emails[:max_results]
    
    def delete_email(self, message_id: str) -> bool:
        """Permanently delete an email"""
        if not self.is_authenticated():
            logger.error("Gmail manager is not authenticated")
            return False
            
        try:
            self.service.users().messages().delete(userId='me', id=message_id).execute()
            logger.info(f"Deleted email {message_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting email {message_id}: {e}")
            return False
    
    def trash_email(self, message_id: str) -> bool:
        """Move email to trash (can be recovered)"""
        if not self.is_authenticated():
            logger.error("Gmail manager is not authenticated")
            return False
            
        try:
            self.service.users().messages().trash(userId='me', id=message_id).execute()
            logger.info(f"Moved email {message_id} to trash")
            return True
        except Exception as e:
            logger.error(f"Error trashing email {message_id}: {e}")
            return False
    
    def batch_delete_emails(self, message_ids: List[str], permanent: bool = False) -> Dict:
        """Delete multiple emails in batch"""
        if not self.is_authenticated():
            logger.error("Gmail manager is not authenticated")
            return {'success': [], 'failed': message_ids}
            
        results = {'success': [], 'failed': []}
        
        for i, msg_id in enumerate(message_ids):
            if i % 10 == 0:  # Progress logging
                logger.info(f"Deleting email {i+1}/{len(message_ids)}")
            
            try:
                if permanent:
                    success = self.delete_email(msg_id)
                else:
                    success = self.trash_email(msg_id)
                
                if success:
                    results['success'].append(msg_id)
                else:
                    results['failed'].append(msg_id)
            except Exception as e:
                logger.error(f"Error processing email {msg_id}: {e}")
                results['failed'].append(msg_id)
        
        logger.info(f"Batch delete completed: {len(results['success'])} success, {len(results['failed'])} failed")
        return results
    
    def archive_email(self, message_id: str) -> bool:
        """Archive an email (remove from inbox)"""
        if not self.is_authenticated():
            logger.error("Gmail manager is not authenticated")
            return False
            
        try:
            self.service.users().messages().modify(
                userId='me', 
                id=message_id,
                body={'removeLabelIds': ['INBOX']}
            ).execute()
            logger.info(f"Archived email {message_id}")
            return True
        except Exception as e:
            logger.error(f"Error archiving email {message_id}: {e}")
            return False
    
    def mark_as_important(self, message_id: str) -> bool:
        """Mark email as important"""
        if not self.is_authenticated():
            logger.error("Gmail manager is not authenticated")
            return False
            
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'addLabelIds': ['IMPORTANT']}
            ).execute()
            logger.info(f"Marked email {message_id} as important")
            return True
        except Exception as e:
            logger.error(f"Error marking email {message_id} as important: {e}")
            return False
    
    def get_inbox_stats(self) -> Dict:
        """Get inbox statistics"""
        if not self.is_authenticated():
            logger.error("Gmail manager is not authenticated")
            return {}
            
        try:
            # Get total messages
            profile = self.service.users().getProfile(userId='me').execute()
            total_messages = profile.get('messagesTotal', 0)
            total_threads = profile.get('threadsTotal', 0)
            
            # Get inbox count
            inbox_query = 'in:inbox'
            inbox_messages = self.search_emails(inbox_query, max_results=1000)
            inbox_count = len(inbox_messages)
            
            # Get unread count
            unread_query = 'is:unread'
            unread_messages = self.search_emails(unread_query, max_results=1000)
            unread_count = len(unread_messages)
            
            # Get promotional count
            promo_query = 'category:promotions'
            promo_messages = self.search_emails(promo_query, max_results=1000)
            promo_count = len(promo_messages)
            
            return {
                'total_messages': total_messages,
                'total_threads': total_threads,
                'inbox_count': inbox_count,
                'unread_count': unread_count,
                'promotional_count': promo_count,
                'user_email': self.user_email
            }
            
        except Exception as e:
            logger.error(f"Error getting inbox stats: {e}")
            return {}
    
    def create_backup_label(self, label_name: str = "AI_CLEANER_BACKUP") -> str:
        """Create a backup label for emails before deletion"""
        if not self.is_authenticated():
            logger.error("Gmail manager is not authenticated")
            return None
            
        try:
            # Check if label exists
            labels = self.service.users().labels().list(userId='me').execute()
            for label in labels.get('labels', []):
                if label['name'] == label_name:
                    return label['id']
            
            # Create new label
            label_object = {
                'name': label_name,
                'messageListVisibility': 'show',
                'labelListVisibility': 'labelShow'
            }
            
            created_label = self.service.users().labels().create(
                userId='me', body=label_object
            ).execute()
            
            logger.info(f"Created backup label: {label_name}")
            return created_label['id']
            
        except Exception as e:
            logger.error(f"Error creating backup label: {e}")
            return None
    
    def backup_before_delete(self, message_ids: List[str], backup_file: str = None) -> bool:
        """Backup email data before deletion"""
        if not self.is_authenticated():
            logger.error("Gmail manager is not authenticated")
            return False
            
        try:
            if not backup_file:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = f"email_backup_{timestamp}.json"
            
            backup_data = []
            
            for msg_id in message_ids:
                email_content = self.get_email_content(msg_id)
                if email_content:
                    backup_data.append(email_content)
            
            # Save to file
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Backed up {len(backup_data)} emails to {backup_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return False