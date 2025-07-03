import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import logging
from typing import List, Dict, Tuple
import time
import os

# Import our custom modules
from enhanced_gmail_manager import EnhancedGmailManager
from ai_email_analyzer import AIEmailAnalyzer, EmailCategory, EmailAction
from smart_unsubscriber import SmartUnsubscriber

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="AI Email Cleaner & Unsubscriber",
    page_icon="🧹",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
.main-header {
    font-size: 2.5rem;
    font-weight: bold;
    color: #2e7d32;  /* deep green */
    text-align: center;
    margin-bottom: 2rem;
}

.metric-card {
    background-color: #f1f8e9;  /* soft green */
    padding: 1rem;
    border-radius: 0.5rem;
    border-left: 5px solid #388e3c;  /* deeper green */
    margin-bottom: 1rem;
    box-shadow: 0 2px 6px rgba(0,0,0,0.1);
}

.danger-zone {
    background-color: #ffebee;
    padding: 1rem;
    border-radius: 0.5rem;
    border-left: 4px solid #f44336;
}

.success-zone {
    background-color: #e8f5e9;
    padding: 1rem;
    border-radius: 0.5rem;
    border-left: 4px solid #4caf50;
}

.warning-zone {
    background-color: #fff3e0;
    padding: 1rem;
    border-radius: 0.5rem;
    border-left: 4px solid #ff9800;
}
</style>
""", unsafe_allow_html=True)


class EmailCleanerDashboard:
    """Streamlit dashboard for AI Email Cleaner"""
    
    def __init__(self):
        self.unsubscriber = SmartUnsubscriber()
        
        # Initialize session state
        if 'analyzed_emails' not in st.session_state:
            st.session_state.analyzed_emails = []
        if 'gmail_connected' not in st.session_state:
            st.session_state.gmail_connected = False
        if 'analysis_complete' not in st.session_state:
            st.session_state.analysis_complete = False
        if 'selected_emails' not in st.session_state:
            st.session_state.selected_emails = []
        # Store the managers in session state to persist across reruns
        if 'gmail_manager' not in st.session_state:
            st.session_state.gmail_manager = None
        if 'ai_analyzer' not in st.session_state:
            st.session_state.ai_analyzer = None
        
    @property
    def gmail_manager(self):
        """Get gmail manager from session state"""
        return st.session_state.gmail_manager
    
    @gmail_manager.setter
    def gmail_manager(self, value):
        """Set gmail manager in session state"""
        st.session_state.gmail_manager = value
    
    @property
    def ai_analyzer(self):
        """Get AI analyzer from session state"""
        return st.session_state.ai_analyzer
    
    @ai_analyzer.setter
    def ai_analyzer(self, value):
        """Set AI analyzer in session state"""
        st.session_state.ai_analyzer = value
        
    def main(self):
        """Main dashboard interface"""
        st.markdown('<h1 class="main-header">🧹 AI Email Cleaner & Unsubscriber</h1>', 
                   unsafe_allow_html=True)
        
        # Sidebar configuration
        self.render_sidebar()
        
        # Main content based on connection status
        if not st.session_state.gmail_connected:
            self.render_setup_page()
        else:
            self.render_main_dashboard()
    
    def render_sidebar(self):
        """Render the sidebar with controls and settings"""
        st.sidebar.title("⚙️ Controls")
        
        # Connection status
        if st.session_state.gmail_connected:
            st.sidebar.success("✅ Gmail Connected")
            if st.sidebar.button("🔌 Disconnect"):
                self.disconnect_gmail()
        else:
            st.sidebar.error("❌ Gmail Not Connected")
        
        st.sidebar.divider()
        
        # Analysis settings
        st.sidebar.subheader("📊 Analysis Settings")
        
        self.max_emails = st.sidebar.slider(
            "Max Emails to Analyze",
            min_value=50,
            max_value=1000,
            value=200,
            step=50,
            help="Higher numbers may take longer to process"
        )
        
        self.days_back = st.sidebar.slider(
            "Days to Look Back",
            min_value=7,
            max_value=365,
            value=30,
            help="How far back to scan for emails"
        )
        
        st.sidebar.divider()
        
        # Filter options
        st.sidebar.subheader("🔍 Filters")
        
        self.filter_categories = st.sidebar.multiselect(
            "Show Categories",
            options=[category.value for category in EmailCategory],
            default=[category.value for category in EmailCategory]
        )
        
        self.filter_actions = st.sidebar.multiselect(
            "Show Actions",
            options=[action.value for action in EmailAction],
            default=[action.value for action in EmailAction]
        )
        
        st.sidebar.divider()
        
        # Danger zone
        st.sidebar.markdown("### ⚠️ Danger Zone")
        if st.sidebar.button("🗑️ Clear All Data", type="secondary"):
            self.clear_all_data()
    
    def render_setup_page(self):
        """Render the initial setup page"""
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            st.markdown("### 🚀 Getting Started")
            
            st.markdown("""
            Welcome to the AI Email Cleaner! This tool will help you:
            
            - 📧 Analyze your Gmail inbox intelligently
            - 🤖 Categorize emails using AI
            - 🗑️ Automatically delete unwanted emails
            - 📈 Provide insights into your email habits
            - 🚫 Unsubscribe from unwanted lists
            """)
            
            st.markdown("### 🔐 Gmail Authentication")
            
            # Option 1: Connect with existing token
            if st.button("🔗 Connect with Existing Token", type="primary"):
                self.connect_gmail_with_token()
            
            st.markdown("---")
            
            # Option 2: Upload credentials file
            st.info("""
            **Alternative**: Upload your Gmail credentials JSON file:
            1. Download credentials from Google Cloud Console
            2. Upload the file below
            3. Authenticate with your Google account
            """)
            
            credentials_file = st.file_uploader(
                "Upload Gmail Credentials JSON",
                type=['json'],
                help="Download this from Google Cloud Console"
            )
            
            if credentials_file is not None:
                if st.button("🔗 Connect with Credentials File", type="secondary"):
                    self.connect_gmail_with_file(credentials_file)
    
    def render_main_dashboard(self):
        """Render the main dashboard after Gmail connection"""
        # Top metrics
        self.render_metrics()
        
        # Analysis controls
        self.render_analysis_controls()
        
        # Results display
        if st.session_state.analysis_complete:
            self.render_analysis_results()
    
    def render_metrics(self):
        """Render top-level metrics"""
        st.markdown("### 📊 Email Metrics")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(
                f'<div class="metric-card">'
                f'<h3>📧 Total Analyzed</h3>'
                f'<h2>{len(st.session_state.analyzed_emails)}</h2>'
                f'</div>',
                unsafe_allow_html=True
            )
        
        with col2:
            spam_count = len([e for e in st.session_state.analyzed_emails 
                            if e.get('category') == EmailCategory.SPAM.value])
            st.markdown(
                f'<div class="metric-card">'
                f'<h3>🚫 Spam/Junk</h3>'
                f'<h2>{spam_count}</h2>'
                f'</div>',
                unsafe_allow_html=True
            )
        
        with col3:
            promo_count = len([e for e in st.session_state.analyzed_emails 
                             if e.get('category') == EmailCategory.PROMOTIONS.value])
            st.markdown(
                f'<div class="metric-card">'
                f'<h3>🏷️ Promotional</h3>'
                f'<h2>{promo_count}</h2>'
                f'</div>',
                unsafe_allow_html=True
            )
        
        with col4:
            delete_count = len([e for e in st.session_state.analyzed_emails 
                              if e.get('action') == EmailAction.DELETE.value])
            st.markdown(
                f'<div class="metric-card">'
                f'<h3>🗑️ To Delete</h3>'
                f'<h2>{delete_count}</h2>'
                f'</div>',
                unsafe_allow_html=True
            )
    
    def render_analysis_controls(self):
        """Render analysis control buttons"""
        st.markdown("### 🔍 Email Analysis")
        
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if st.button("🚀 Start Analysis", type="primary", disabled=st.session_state.analysis_complete):
                self.run_email_analysis()
        
        with col2:
            if st.button("🔄 Refresh Analysis"):
                self.refresh_analysis()
        
        with col3:
            if st.session_state.analysis_complete:
                st.success(f"✅ Analysis complete! Found {len(st.session_state.analyzed_emails)} emails")
    
    def render_analysis_results(self):
        """Render the analysis results"""
        if not st.session_state.analyzed_emails:
            st.warning("No emails found for analysis.")
            return
        
        # Create tabs for different views
        tab1, tab2, tab3, tab4 = st.tabs(["📋 Email List", "📊 Analytics", "🗑️ Bulk Actions", "📈 Charts"])
        
        with tab1:
            self.render_email_list()
        
        with tab2:
            self.render_analytics()
        
        with tab3:
            self.render_bulk_actions()
        
        with tab4:
            self.render_charts()
    
    def render_email_list(self):
        """Render the detailed email list"""
        st.markdown("### 📧 Analyzed Emails")
        
        # Filter emails based on sidebar selections
        filtered_emails = self.filter_emails()
        
        if not filtered_emails:
            st.warning("No emails match the current filters.")
            return
        
        # Display email table
        for idx, email in enumerate(filtered_emails):
            with st.expander(f"📧 {email['subject'][:60]}... | {email['from'][:30]}"):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.write(f"**From:** {email['from']}")
                    st.write(f"**Date:** {email['date']}")
                    st.write(f"**Category:** {email['category']}")
                    st.write(f"**Action:** {email['action']}")
                    st.write(f"**Confidence:** {email['confidence']:.2f}")
                    
                    if email.get('snippet'):
                        st.write(f"**Preview:** {email['snippet'][:200]}...")
                
                with col2:
                    if st.button(f"🗑️ Delete", key=f"delete_{idx}"):
                        self.delete_single_email(email['id'])
                    
                    if st.button(f"🚫 Unsubscribe", key=f"unsub_{idx}"):
                        self.unsubscribe_single_email(email)
    
    def render_analytics(self):
        """Render analytics insights"""
        st.markdown("### 📊 Email Analytics")
        
        # Create DataFrame properly
        emails_df = pd.DataFrame(st.session_state.analyzed_emails)
        
        if emails_df.empty:
            st.warning("No data available for analytics.")
            return
        
        # Convert date column properly
        if 'date' in emails_df.columns:
            # Attempt to parse date, coerce errors to NaT
            emails_df['date'] = pd.to_datetime(emails_df['date'], errors='coerce', utc=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Category distribution
            if 'category' in emails_df.columns:
                category_counts = emails_df['category'].value_counts()
                st.markdown("#### 📈 Category Distribution")
                st.bar_chart(category_counts)
        
        with col2:
            # Action distribution
            if 'action' in emails_df.columns:
                action_counts = emails_df['action'].value_counts()
                st.markdown("#### 🎯 Recommended Actions")
                st.bar_chart(action_counts)
        
        # Top senders
        if 'from' in emails_df.columns:
            st.markdown("#### 📮 Top Senders")
            sender_counts = emails_df['from'].value_counts().head(10)
            st.bar_chart(sender_counts)
        
        # Time-based analysis (if date column exists and is parseable)
        if 'date' in emails_df.columns:
            try:
                st.markdown("#### 📅 Email Timeline")
                # Filter out NaT values
                valid_dates = emails_df.dropna(subset=['date'])
                if not valid_dates.empty:
                    daily_counts = valid_dates.groupby(valid_dates['date'].dt.date).size()
                    st.line_chart(daily_counts)
                else:
                    st.write("No valid dates found for timeline analysis")
            except Exception as e:
                st.write(f"Could not parse dates for timeline analysis: {e}")

    
    def render_bulk_actions(self):
        """Render bulk action controls"""
        st.markdown("### 🗑️ Bulk Actions")
        
        st.markdown(
            '<div class="danger-zone">'
            '<h4>⚠️ Warning: Bulk actions cannot be undone!</h4>'
            '<p>Please review your selections carefully before proceeding.</p>'
            '</div>',
            unsafe_allow_html=True
        )
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("#### 🗑️ Delete Actions")
            # Use string value instead of enum
            delete_emails = [e for e in st.session_state.analyzed_emails 
                        if e['action'] == EmailAction.DELETE.value]
            
            st.write(f"Emails marked for deletion: {len(delete_emails)}")
            
            if st.button("🗑️ Delete All Marked Emails", type="secondary"):
                self.bulk_delete_emails(delete_emails)
        
        with col2:
            st.markdown("#### 🚫 Unsubscribe Actions")
            # Use string value instead of enum
            unsub_emails = [e for e in st.session_state.analyzed_emails 
                        if e['action'] == EmailAction.UNSUBSCRIBE.value]
            
            st.write(f"Emails to unsubscribe: {len(unsub_emails)}")
            
            if st.button("🚫 Unsubscribe All", type="secondary"):
                self.bulk_unsubscribe_emails(unsub_emails)
        
        with col3:
            st.markdown("#### 📧 Archive Actions")
            # Use string value instead of enum
            archive_emails = [e for e in st.session_state.analyzed_emails 
                            if e['action'] == EmailAction.ARCHIVE.value]
            
            st.write(f"Emails to archive: {len(archive_emails)}")
            
            if st.button("📧 Archive All", type="secondary"):
                self.bulk_archive_emails(archive_emails)
    
    def render_charts(self):
        """Render advanced charts and visualizations"""
        st.markdown("### 📈 Advanced Analytics")
        
        emails_df = pd.DataFrame(st.session_state.analyzed_emails)
        
        if emails_df.empty:
            st.warning("No data available for charts.")
            return
        
        # Confidence distribution
        fig_confidence = px.histogram(
            emails_df, 
            x='confidence', 
            title='AI Confidence Distribution',
            nbins=20
        )
        st.plotly_chart(fig_confidence, use_container_width=True)
        
        # Category vs Action heatmap
        category_action = pd.crosstab(emails_df['category'], emails_df['action'])
        fig_heatmap = px.imshow(
            category_action.values,
            x=category_action.columns,
            y=category_action.index,
            title='Category vs Action Heatmap',
            aspect="auto"
        )
        st.plotly_chart(fig_heatmap, use_container_width=True)
        
        # Sender analysis
        top_senders = emails_df['from'].value_counts().head(15)
        fig_senders = px.bar(
            x=top_senders.values,
            y=top_senders.index,
            orientation='h',
            title='Top 15 Email Senders'
        )
        fig_senders.update_layout(height=600)
        st.plotly_chart(fig_senders, use_container_width=True)
    
    def connect_gmail_with_token(self):
        """Connect to Gmail using existing token"""
        try:
            with st.spinner("Connecting to Gmail..."):
                # Initialize Gmail manager and store in session state
                gmail_manager = EnhancedGmailManager()
                
                if gmail_manager.is_authenticated():
                    st.session_state.gmail_manager = gmail_manager
                    
                    # Load Gemini API key from environment variable
                    gemini_api_key = os.getenv("GEMINI_API_KEY")
                    if not gemini_api_key:
                        st.error("GEMINI_API_KEY environment variable not set. Please set it and rerun.")
                        return
                    st.session_state.ai_analyzer = AIEmailAnalyzer(gemini_api_key)
                    
                    st.session_state.gmail_connected = True
                    st.success(f"Connected to Gmail: {gmail_manager.user_email}")
                    st.rerun()
                else:
                    st.error("Failed to authenticate with existing token")
        except Exception as e:
            st.error(f"Failed to connect to Gmail: {str(e)}")
            logger.error(f"Gmail connection error: {e}")

    def connect_gmail_with_file(self, credentials_file):
        """Connect to Gmail using uploaded credentials file"""
        try:
            with st.spinner("Connecting to Gmail..."):
                # Read credentials data
                credentials_data = json.load(credentials_file)
                credentials_json = json.dumps(credentials_data)
                
                # Initialize Gmail manager and store in session state
                gmail_manager = EnhancedGmailManager()
                
                if gmail_manager.authenticate_with_credentials(credentials_json):
                    st.session_state.gmail_manager = gmail_manager
                    
                    # Load Gemini API key from environment variable
                    gemini_api_key = os.getenv("GEMINI_API_KEY")
                    if not gemini_api_key:
                        st.error("GEMINI_API_KEY environment variable not set. Please set it and rerun.")
                        return
                    st.session_state.ai_analyzer = AIEmailAnalyzer(gemini_api_key)
                    
                    st.session_state.gmail_connected = True
                    st.success(f"Connected to Gmail: {gmail_manager.user_email}")
                    st.rerun()
                else:
                    st.error("Failed to authenticate with provided credentials")
        except Exception as e:
            st.error(f"Failed to connect to Gmail: {str(e)}")
            logger.error(f"Gmail connection error: {e}")
    
    def disconnect_gmail(self):
        """Disconnect from Gmail and clear session state"""
        st.session_state.gmail_connected = False
        st.session_state.gmail_manager = None
        st.session_state.ai_analyzer = None
        st.session_state.analyzed_emails = []
        st.session_state.analysis_complete = False
        st.session_state.selected_emails = []
        st.success("Disconnected from Gmail.")
        st.rerun()

    def run_email_analysis(self):
        """Run the email analysis process"""
        # Check if Gmail is connected by checking session state
        if not st.session_state.gmail_connected or not st.session_state.gmail_manager or not st.session_state.ai_analyzer:
            st.error("Gmail not connected! Please connect to Gmail first.")
            return
        
        try:
            with st.spinner("Analyzing emails... This may take a few minutes."):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Fetch emails using the correct method from the session state managers
                status_text.text("Fetching emails from Gmail...")
                
                # Use the correct method name from EnhancedGmailManager
                emails = st.session_state.gmail_manager.get_emails_by_timeframe(
                    days_back=self.days_back,
                    max_results=self.max_emails
                )
                progress_bar.progress(25)
                
                if not emails:
                    st.warning("No emails found in the specified timeframe.")
                    return
                
                # Analyze emails
                status_text.text("Analyzing emails with AI...")
                analyzed_emails = []
                
                for i, email in enumerate(emails):
                    try:
                        analysis = st.session_state.ai_analyzer.analyze_email(email)
                        
                        analyzed_email = {
                            'id': email.get('id'),
                            'subject': email.get('subject', 'No Subject'),
                            'from': email.get('from', 'Unknown'),
                            'date': email.get('date', ''),
                            'snippet': email.get('snippet', ''),
                            'body_html': email.get('body_html', ''), # Add body_html for unsubscriber
                            'body_text': email.get('body_text', ''), # Add body_text for unsubscriber
                            'category': analysis.category.value,
                            'action': analysis.action.value,
                            'confidence': analysis.confidence,
                            'reasoning': analysis.reasoning
                        }
                        analyzed_emails.append(analyzed_email)
                        
                        # Update progress
                        progress = 25 + (i / len(emails)) * 70
                        progress_bar.progress(int(progress))
                        status_text.text(f"Analyzed {i+1}/{len(emails)} emails...")
                        
                    except Exception as e:
                        logger.error(f"Error analyzing email {i}: {e}")
                        continue
                
                # Save results
                st.session_state.analyzed_emails = analyzed_emails
                st.session_state.analysis_complete = True
                
                progress_bar.progress(100)
                status_text.text("Analysis complete!")
                
                st.success(f"Successfully analyzed {len(analyzed_emails)} emails!")
                time.sleep(1)
                st.rerun()
                
        except Exception as e:
            st.error(f"Analysis failed: {str(e)}")
            logger.error(f"Analysis error: {e}")
    
    def refresh_analysis(self):
        """Refresh the email analysis"""
        st.session_state.analysis_complete = False
        st.session_state.analyzed_emails = []
        st.rerun()
    
    def filter_emails(self):
        """Filter emails based on sidebar selections"""
        filtered = []
        for email in st.session_state.analyzed_emails:
            if (email['category'] in self.filter_categories and 
                email['action'] in self.filter_actions):
                filtered.append(email)
        return filtered
    
    def delete_single_email(self, email_id):
        """Delete a single email"""
        try:
            if st.session_state.gmail_manager:
                success = st.session_state.gmail_manager.delete_email(email_id)
                if success:
                    st.success("Email deleted successfully!")
                    # Remove from analyzed emails
                    st.session_state.analyzed_emails = [
                        e for e in st.session_state.analyzed_emails if e['id'] != email_id
                    ]
                    st.rerun()
                else:
                    st.error("Failed to delete email")
            else:
                st.error("Gmail not connected!")
        except Exception as e:
            st.error(f"Failed to delete email: {str(e)}")
    
    def unsubscribe_single_email(self, email_data: Dict):
        """Unsubscribe from a single email"""
        try:
            # Get user's email address from gmail_manager
            user_email_address = st.session_state.gmail_manager.user_email if st.session_state.gmail_manager else None
            if not user_email_address:
                st.warning("Cannot unsubscribe: Gmail user email not available.")
                return

            results = self.unsubscriber.unsubscribe_from_email(email_data, user_email_address)
            
            if any(r.success for r in results):
                st.success("Successfully unsubscribed!")
            else:
                st.warning("Could not find unsubscribe link or failed to unsubscribe.")
                for r in results:
                    if not r.success:
                        st.info(f"Unsubscribe attempt failed: {r.message} (Method: {r.method}, URL: {r.url})")
        except Exception as e:
            st.error(f"Failed to unsubscribe: {str(e)}")
    
    def bulk_delete_emails(self, emails):
        """Delete multiple emails"""
        try:
            with st.spinner(f"Deleting {len(emails)} emails..."):
                email_ids = [email['id'] for email in emails]
                results = st.session_state.gmail_manager.batch_delete_emails(email_ids, permanent=True)
                
                success_count = len(results['success'])
                failed_count = len(results['failed'])
                
                st.success(f"Successfully deleted {success_count} emails!")
                if failed_count > 0:
                    st.warning(f"Failed to delete {failed_count} emails")
                
                # Remove deleted emails from session state
                deleted_ids = set(results['success'])
                st.session_state.analyzed_emails = [
                    e for e in st.session_state.analyzed_emails 
                    if e['id'] not in deleted_ids
                ]
                st.rerun()
                
        except Exception as e:
            st.error(f"Bulk delete failed: {str(e)}")
    
    def bulk_unsubscribe_emails(self, emails):
        """Unsubscribe from multiple emails"""
        try:
            with st.spinner(f"Unsubscribing from {len(emails)} senders..."):
                success_count = 0
                # Get user's email address from gmail_manager
                user_email_address = st.session_state.gmail_manager.user_email if st.session_state.gmail_manager else None
                if not user_email_address:
                    st.warning("Cannot perform bulk unsubscribe: Gmail user email not available.")
                    return

                for email_data in emails:
                    try:
                        results = self.unsubscriber.unsubscribe_from_email(email_data, user_email_address)
                        if any(r.success for r in results):
                            success_count += 1
                        else:
                            logger.warning(f"Failed to unsubscribe from {email_data.get('from', 'Unknown Sender')}. Details: {results}")
                    except Exception as e:
                        logger.error(f"Failed to unsubscribe from {email_data.get('from', 'Unknown Sender')}: {e}")
                
                st.success(f"Successfully unsubscribed from {success_count} senders!")
                
        except Exception as e:
            st.error(f"Bulk unsubscribe failed: {str(e)}")
    
    def bulk_archive_emails(self, emails):
        """Archive multiple emails"""
        try:
            with st.spinner(f"Archiving {len(emails)} emails..."):
                archived_count = 0
                for email in emails:
                    try:
                        if st.session_state.gmail_manager.archive_email(email['id']):
                            archived_count += 1
                    except Exception as e:
                        logger.error(f"Failed to archive email {email['id']}: {e}")
                
                st.success(f"Successfully archived {archived_count} emails!")
                
                # Remove archived emails from session state
                archived_ids = [email['id'] for email in emails[:archived_count]]
                st.session_state.analyzed_emails = [
                    e for e in st.session_state.analyzed_emails 
                    if e['id'] not in archived_ids
                ]
                st.rerun()
                
        except Exception as e:
            st.error(f"Bulk archive failed: {str(e)}")
    
    def clear_all_data(self):
        """Clear all stored data"""
        st.session_state.analyzed_emails = []
        st.session_state.analysis_complete = False
        st.session_state.selected_emails = []
        st.success("All data cleared!")
        st.rerun()

# Main execution
if __name__ == "__main__":
    dashboard = EmailCleanerDashboard()
    dashboard.main()

