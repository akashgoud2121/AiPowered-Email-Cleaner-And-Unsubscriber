import google.generativeai as genai
import re
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import logging
from datetime import datetime, timedelta
import os

logger = logging.getLogger(__name__)

class EmailCategory(Enum):
    IMPORTANT = "important"
    SPAM = "spam" 
    PROMOTIONS = "promotions"
    NEWSLETTERS = "newsletters"
    SOCIAL = "social"
    OLD_UNIMPORTANT = "old_unimportant"
    RECEIPTS = "receipts"
    NOTIFICATIONS = "notifications"
    PERSONAL = "personal"
    WORK = "work"

class EmailAction(Enum):
    KEEP = "keep"
    DELETE = "delete"
    UNSUBSCRIBE = "unsubscribe"
    ARCHIVE = "archive"
    MARK_IMPORTANT = "mark_important"

@dataclass
class EmailAnalysis:
    """Result of AI email analysis"""
    category: EmailCategory
    action: EmailAction
    confidence: float
    reasoning: str
    priority_score: int  # 1-10, 10 being most important
    has_unsubscribe: bool
    is_automated: bool
    sender_reputation: str  # trusted, unknown, suspicious
    content_summary: str

class AIEmailAnalyzer:
    """AI-powered email content analyzer using Google Gemini"""
    
    def __init__(self, gemini_api_key: str = None):
        """Initialize with Gemini API key"""
        try:
            # Use provided API key or get from environment variable
            if gemini_api_key is None:
                gemini_api_key = os.getenv("GEMINI_API_KEY")
            
            if not gemini_api_key:
                raise ValueError("Gemini API key not provided. Set GEMINI_API_KEY environment variable or pass it to the constructor.")

            genai.configure(api_key=gemini_api_key)
            
            # Initialize the model
            self.model = genai.GenerativeModel("gemini-1.5-flash")
            
            # Test the connection
            test_response = self.model.generate_content(
                "Test message",
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=10,
                    temperature=0.1,
                )
            )
            logger.info("Gemini AI connection successful")
            
        except Exception as e:
            logger.error(f"Failed to initialize Gemini AI: {e}")
            self.model = None
        
        # Define analysis prompt template
        self.analysis_prompt = """
        Analyze this email and provide a JSON response with the following structure:
        {
            "category": "one of: important, spam, promotions, newsletters, social, old_unimportant, receipts, notifications, personal, work",
            "action": "one of: keep, delete, unsubscribe, archive, mark_important", 
            "confidence": 0.85,
            "reasoning": "Brief explanation of why this categorization",
            "priority_score": 7,
            "has_unsubscribe": true,
            "is_automated": true,
            "sender_reputation": "one of: trusted, unknown, suspicious",
            "content_summary": "Brief 1-2 sentence summary of email content"
        }

        Email Details:
        Subject: {subject}
        From: {sender}
        Date: {date}
        Content: {content}
        
        Analysis Guidelines:
        - SPAM: Obvious spam, phishing, suspicious links
        - PROMOTIONS: Marketing emails, sales, deals
        - NEWSLETTERS: Regular updates, blogs, news
        - IMPORTANT: Banking, legal, urgent personal/work
        - OLD_UNIMPORTANT: Emails older than 30 days with low priority
        - RECEIPTS: Purchase confirmations, invoices
        - SOCIAL: Facebook, LinkedIn, social media notifications
        - PERSONAL: Personal conversations, family, friends
        - WORK: Job-related, professional communications
        
        Actions:
        - DELETE: Spam, very old unimportant emails
        - UNSUBSCRIBE: Unwanted marketing/newsletters
        - ARCHIVE: Keep but remove from inbox
        - KEEP: Important emails to keep in inbox
        - MARK_IMPORTANT: Critical emails needing attention
        
        Priority Score (1-10):
        10: Critical (banking, legal, urgent)
        7-9: Important (work, personal important)
        4-6: Medium (newsletters, notifications)
        1-3: Low (promotions, old emails)
        
        Please respond ONLY with valid JSON, no other text.
        """
    
    def analyze_email(self, email_data: Dict) -> EmailAnalysis:
        """Analyze a single email using AI"""
        try:
            # Check if model is available
            if not self.model:
                logger.warning("Gemini model not available, using fallback analysis")
                return self._get_default_analysis(email_data)
            
            # Prepare email content for analysis
            content = self._prepare_content(email_data)
            
            # Create analysis prompt
            prompt = self.analysis_prompt.format(
                subject=email_data.get("subject", ""),
                sender=email_data.get("from", ""),
                date=email_data.get("date", ""),
                content=content[:2000]  # Limit content length
            )
            
            # Call Gemini API with retry logic
            response = self._call_gemini_with_retry(prompt)
            if not response:
                return self._get_default_analysis(email_data)
            
            # Parse response
            analysis_text = response.text.strip()
            
            # Enhanced JSON cleaning
            analysis_text = self._clean_json_response(analysis_text)
            
            # Try to parse JSON
            try:
                analysis_data = json.loads(analysis_text)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing failed: {e}")
                logger.error(f"Response text: {analysis_text}")
                # Return fallback analysis
                return self._get_default_analysis(email_data)
            
            # Validate required fields
            if not self._validate_analysis_data(analysis_data):
                logger.error(f"Invalid analysis data: {analysis_data}")
                return self._get_default_analysis(email_data)
            
            # Create EmailAnalysis object
            return EmailAnalysis(
                category=EmailCategory(analysis_data["category"]),
                action=EmailAction(analysis_data["action"]),
                confidence=float(analysis_data.get("confidence", 0.5)),
                reasoning=analysis_data.get("reasoning", ""),
                priority_score=int(analysis_data.get("priority_score", 5)),
                has_unsubscribe=bool(analysis_data.get("has_unsubscribe", False)),
                is_automated=bool(analysis_data.get("is_automated", False)),
                sender_reputation=analysis_data.get("sender_reputation", "unknown"),
                content_summary=analysis_data.get("content_summary", "")
            )
            
        except Exception as e:
            logger.error(f"Error analyzing email: {e}")
            # Return conservative default analysis
            return self._get_default_analysis(email_data)
    
    def _call_gemini_with_retry(self, prompt: str, max_retries: int = 3):
        """Call Gemini API with retry logic"""
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=500,
                        temperature=0.1,
                    )
                )
                return response
            except Exception as e:
                logger.warning(f"Gemini API call failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error("All Gemini API retry attempts failed")
                    return None
    
    def _clean_json_response(self, response_text: str) -> str:
        """Clean and extract JSON from AI response"""
        # Strip markdown and whitespace
        response_text = response_text.strip().strip("```json").strip("```").strip()

        # Attempt to locate the first and last braces for JSON object
        # This regex is more robust to extra text before/after the JSON
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            response_text = match.group(0)

        # Remove trailing commas (e.g., `"key": "value",}`)
        response_text = re.sub(r',(\s*[}\]])', r'\1', response_text)

        # Escape problematic characters if needed (optional step)
        response_text = response_text.replace('\n', '').replace('\r', '')

        return response_text

    
    def _validate_analysis_data(self, data: Dict) -> bool:
        """Validate that analysis data has required fields and correct enum values"""
        required_fields = ["category", "action"]
        
        for field in required_fields:
            if field not in data:
                logger.error(f"Missing required field: {field}")
                return False
        
        # Normalize and validate enum values
        try:
            data["category"] = data["category"].strip().lower()
            EmailCategory(data["category"])
            
            data["action"] = data["action"].strip().lower()
            EmailAction(data["action"])
        except ValueError as e:
            logger.error(f"Invalid enum value: {e}")
            return False
        
        return True
    
    def analyze_batch(self, emails: List[Dict]) -> List[Tuple[Dict, EmailAnalysis]]:
        """Analyze multiple emails"""
        results = []
        
        for i, email in enumerate(emails):
            logger.info(f"Analyzing email {i+1}/{len(emails)}: {email.get("subject", "")[:50]}")
            
            try:
                analysis = self.analyze_email(email)
                results.append((email, analysis))
                
                # Add small delay to avoid rate limits
                import time
                time.sleep(1)  # Increased delay for better rate limit handling
                
            except Exception as e:
                logger.error(f"Failed to analyze email {i+1}: {e}")
                # Add with default analysis
                results.append((email, self._get_default_analysis(email)))
        
        return results
    
    def _prepare_content(self, email_data: Dict) -> str:
        """Prepare email content for AI analysis"""
        # Combine text and HTML content
        content_parts = []
        
        if email_data.get("body_text"):
            content_parts.append(email_data["body_text"])
        
        if email_data.get("body_html"):
            # Simple HTML to text conversion
            html_text = re.sub(r'<[^>]+>', ' ', email_data["body_html"])
            html_text = re.sub(r'\s+', ' ', html_text).strip()
            content_parts.append(html_text)
        
        # Also include snippet if available
        if email_data.get("snippet"):
            content_parts.append(email_data["snippet"])
        
        return ' '.join(content_parts)
    
    def _get_default_analysis(self, email_data: Dict) -> EmailAnalysis:
        """Return conservative default analysis when AI fails"""
        # Simple rule-based fallback
        subject = email_data.get("subject", "").lower()
        sender = email_data.get("from", "").lower()
        
        # Check for obvious spam indicators
        spam_keywords = ["viagra", "lottery", "winner", "click here", "urgent", "congratulations", "free money", "nigerian prince"]
        if any(keyword in subject for keyword in spam_keywords):
            category = EmailCategory.SPAM
            action = EmailAction.DELETE
            priority = 1
            reasoning = "Detected spam keywords"
        
        # Check for promotional keywords
        elif any(word in subject for word in ["sale", "offer", "deal", "discount", "%", "free", "limited time"]):
            category = EmailCategory.PROMOTIONS
            action = EmailAction.UNSUBSCRIBE
            priority = 3
            reasoning = "Promotional content detected"
        
        # Check for newsletters
        elif any(word in subject for word in ["newsletter", "update", "weekly", "monthly", "digest"]):
            category = EmailCategory.NEWSLETTERS
            action = EmailAction.ARCHIVE
            priority = 4
            reasoning = "Newsletter content detected"
        
        # Check for receipts/confirmations
        elif any(word in subject for word in ["receipt", "confirmation", "order", "invoice", "payment"]):
            category = EmailCategory.RECEIPTS
            action = EmailAction.ARCHIVE
            priority = 6
            reasoning = "Receipt/confirmation detected"
        
        # Check for social media
        elif any(word in sender for word in ["facebook", "linkedin", "twitter", "instagram"]):
            category = EmailCategory.SOCIAL
            action = EmailAction.ARCHIVE
            priority = 4
            reasoning = "Social media notification"
        
        # Default to keep if unsure
        else:
            category = EmailCategory.NOTIFICATIONS
            action = EmailAction.KEEP
            priority = 5
            reasoning = "Rule-based analysis (AI unavailable)"
        
        return EmailAnalysis(
            category=category,
            action=action,
            confidence=0.6,
            reasoning=reasoning,
            priority_score=priority,
            has_unsubscribe=False,
            is_automated=True,
            sender_reputation="unknown",
            content_summary="Content analysis unavailable"
        )
    
    def get_deletion_candidates(self, analyzed_emails: List[Tuple[Dict, EmailAnalysis]], 
                              min_confidence: float = 0.7) -> List[Tuple[Dict, EmailAnalysis]]:
        """Get emails that are safe to delete"""
        candidates = []
        
        for email, analysis in analyzed_emails:
            # Only suggest deletion for high-confidence low-priority emails
            if (analysis.action == EmailAction.DELETE and 
                analysis.confidence >= min_confidence and 
                analysis.priority_score <= 3):
                candidates.append((email, analysis))
        
        return candidates
    
    def get_unsubscribe_candidates(self, analyzed_emails: List[Tuple[Dict, EmailAnalysis]]) -> List[Tuple[Dict, EmailAnalysis]]:
        """Get emails that should be unsubscribed from"""
        candidates = []
        
        for email, analysis in analyzed_emails:
            if (analysis.action == EmailAction.UNSUBSCRIBE and 
                analysis.has_unsubscribe and
                analysis.category in [EmailCategory.PROMOTIONS, EmailCategory.NEWSLETTERS]):
                candidates.append((email, analysis))
        
        return candidates
    
    def generate_summary_report(self, analyzed_emails: List[Tuple[Dict, EmailAnalysis]]) -> Dict:
        """Generate summary statistics"""
        total_emails = len(analyzed_emails)
        if total_emails == 0:
            return {}
        
        # Count by category
        category_counts = {}
        action_counts = {}
        priority_distribution = {i: 0 for i in range(1, 11)}
        
        total_size_estimate = 0  # Rough estimate
        
        for email, analysis in analyzed_emails:
            # Count categories
            cat = analysis.category.value
            category_counts[cat] = category_counts.get(cat, 0) + 1
            
            # Count actions
            act = analysis.action.value
            action_counts[act] = action_counts.get(act, 0) + 1
            
            # Priority distribution
            priority_distribution[analysis.priority_score] += 1
            
            # Estimate size (rough)
            content_length = len(email.get("body_html", "")) + len(email.get("body_text", ""))
            total_size_estimate += content_length * 0.001  # KB estimate
        
        return {
            "total_emails": total_emails,
            "categories": category_counts,
            "actions": action_counts,
            "priority_distribution": priority_distribution,
            "estimated_size_kb": int(total_size_estimate),
            "deletion_candidates": action_counts.get("delete", 0),
            "unsubscribe_candidates": action_counts.get("unsubscribe", 0),
            "avg_confidence": sum(analysis.confidence for _, analysis in analyzed_emails) / total_emails
        }

# Usage example
if __name__ == "__main__":
    # Example usage (requires Gemini API key)
    # Make sure to set the GEMINI_API_KEY environment variable
    analyzer = AIEmailAnalyzer()
    
    # Sample email data
    sample_email = {
        "subject": "Special 50% Off Sale - Limited Time!",
        "from": "marketing@store.com",
        "date": "2024-01-15",
        "body_text": "Get 50% off all items this weekend only! Click here to shop now.",
        "body_html": "<p>Get <b>50% off</b> all items this weekend only!</p>"
    }
    
    try:
        analysis = analyzer.analyze_email(sample_email)
        print(f"Category: {analysis.category.value}")
        print(f"Action: {analysis.action.value}")
        print(f"Priority: {analysis.priority_score}")
        print(f"Reasoning: {analysis.reasoning}")
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure you have installed google-generativeai: pip install google-generativeai")


