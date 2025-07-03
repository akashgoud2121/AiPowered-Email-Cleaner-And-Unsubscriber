import requests
import re
import time
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Tuple
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class UnsubscribeResult:
    """Result of an unsubscribe attempt"""
    success: bool
    message: str
    method: str
    url: str

class SmartUnsubscriber:
    """Enhanced unsubscriber that can handle various unsubscribe mechanisms"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Common unsubscribe link patterns
        self.unsubscribe_patterns = [
            r'unsubscribe',
            r'opt[\-_]?out',
            r'remove[\-_]?me',
            r'stop[\-_]?emails',
            r'email[\-_]?preferences',
            r'manage[\-_]?subscription',
            r'leave[\-_]?list',
            r'cancel[\-_]?subscription'
        ]
        
        # Common form field patterns for unsubscribe
        self.form_field_patterns = [
            r'email',
            r'address',
            r'unsubscribe',
            r'remove',
            r'opt[\-_]?out'
        ]
        
        # Confirmation button patterns
        self.confirmation_patterns = [
            r'unsubscribe',
            r'confirm',
            r'yes',
            r'remove',
            r'opt[\-_]?out',
            r'continue',
            r'proceed'
        ]
    
    def extract_unsubscribe_links(self, email_content: str) -> List[str]:
        """Extract potential unsubscribe links from email content"""
        soup = BeautifulSoup(email_content, 'html.parser')
        links = []
        
        # Find all links
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            link_text = link.get_text().lower().strip()
            
            # Check if link text matches unsubscribe patterns
            for pattern in self.unsubscribe_patterns:
                if re.search(pattern, link_text, re.IGNORECASE) or re.search(pattern, href, re.IGNORECASE):
                    links.append(href)
                    break
        
        # Also check for List-Unsubscribe header links if provided
        list_unsubscribe_pattern = r'<(https?://[^>]+)>'
        matches = re.findall(list_unsubscribe_pattern, email_content)
        links.extend(matches)
        
        return list(set(links))  # Remove duplicates
    
    def visit_unsubscribe_page(self, url: str) -> Tuple[BeautifulSoup, requests.Response]:
        """Visit the unsubscribe page and return parsed content"""
        try:
            response = self.session.get(url, timeout=30, allow_redirects=True)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            return soup, response
        except Exception as e:
            logger.error(f"Error visiting unsubscribe page {url}: {e}")
            raise
    
    def find_unsubscribe_form(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Find and analyze unsubscribe forms on the page"""
        forms = soup.find_all('form')
        
        for form in forms:
            form_action = form.get('action', '')
            form_method = form.get('method', 'get').lower()
            
            # Check if form looks like an unsubscribe form
            form_text = form.get_text().lower()
            is_unsubscribe_form = any(
                re.search(pattern, form_text, re.IGNORECASE) 
                for pattern in self.unsubscribe_patterns
            )
            
            if is_unsubscribe_form:
                # Extract form fields
                fields = {}
                for input_field in form.find_all(['input', 'select', 'textarea']):
                    field_name = input_field.get('name')
                    field_type = input_field.get('type', 'text')
                    field_value = input_field.get('value', '')
                    
                    if field_name:
                        fields[field_name] = {
                            'type': field_type,
                            'value': field_value,
                            'required': input_field.get('required') is not None
                        }
                
                return {
                    'action': form_action,
                    'method': form_method,
                    'fields': fields,
                    'form_element': form
                }
        
        return None
    
    def find_unsubscribe_buttons(self, soup: BeautifulSoup) -> List[Dict]:
        """Find clickable unsubscribe buttons or links"""
        buttons = []
        
        # Find button elements
        for button in soup.find_all(['button', 'input']):
            button_text = button.get_text().lower().strip()
            button_value = button.get('value', '').lower().strip()
            button_type = button.get('type', '')
            
            text_to_check = f"{button_text} {button_value}"
            
            if any(re.search(pattern, text_to_check, re.IGNORECASE) for pattern in self.confirmation_patterns):
                buttons.append({
                    'element': button,
                    'text': button_text or button_value,
                    'type': button_type,
                    'name': button.get('name'),
                    'value': button.get('value', '')
                })
        
        # Find clickable links that might be unsubscribe buttons
        for link in soup.find_all('a', href=True):
            link_text = link.get_text().lower().strip()
            if any(re.search(pattern, link_text, re.IGNORECASE) for pattern in self.confirmation_patterns):
                buttons.append({
                    'element': link,
                    'text': link_text,
                    'type': 'link',
                    'href': link.get('href')
                })
        
        return buttons
    
    def attempt_form_unsubscribe(self, form_data: Dict, base_url: str, email: str = None) -> UnsubscribeResult:
        """Attempt to unsubscribe using a form"""
        try:
            action_url = urljoin(base_url, form_data['action'])
            method = form_data['method']
            
            # Prepare form data
            data = {}
            for field_name, field_info in form_data['fields'].items():
                if field_info['type'] == 'hidden':
                    data[field_name] = field_info['value']
                elif field_info['type'] == 'email' and email:
                    data[field_name] = email
                elif any(re.search(pattern, field_name, re.IGNORECASE) for pattern in self.form_field_patterns):
                    if email and ('email' in field_name.lower() or 'address' in field_name.lower()):
                        data[field_name] = email
                    elif field_info['value']:
                        data[field_name] = field_info['value']
                elif field_info['type'] in ['submit', 'button']:
                    if field_info['value']:
                        data[field_name] = field_info['value']
            
            # Submit form
            if method == 'post':
                response = self.session.post(action_url, data=data, timeout=30)
            else:
                response = self.session.get(action_url, params=data, timeout=30)
            
            response.raise_for_status()
            
            # Check if unsubscribe was successful
            success_indicators = [
                'successfully unsubscribed',
                'removed from list',
                'unsubscribed',
                'opt out successful',
                'email preferences updated'
            ]
            
            response_text = response.text.lower()
            success = any(indicator in response_text for indicator in success_indicators)
            
            return UnsubscribeResult(
                success=success,
                message=f"Form submission completed. Status: {response.status_code}",
                method="form",
                url=action_url
            )
            
        except Exception as e:
            logger.error(f"Error during form unsubscribe: {e}")
            return UnsubscribeResult(
                success=False,
                message=f"Error: {str(e)}",
                method="form",
                url=action_url if 'action_url' in locals() else ""
            )
    
    def attempt_link_unsubscribe(self, link_data: Dict, base_url: str) -> UnsubscribeResult:
        """Attempt to unsubscribe by clicking a link"""
        try:
            if link_data['type'] == 'link':
                url = urljoin(base_url, link_data['href'])
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                # Check response for success indicators
                success_indicators = [
                    'successfully unsubscribed',
                    'removed from list',
                    'unsubscribed',
                    'opt out successful'
                ]
                
                response_text = response.text.lower()
                success = any(indicator in response_text for indicator in success_indicators)
                
                return UnsubscribeResult(
                    success=success,
                    message=f"Link clicked. Status: {response.status_code}",
                    method="link",
                    url=url
                )
            
        except Exception as e:
            logger.error(f"Error during link unsubscribe: {e}")
            return UnsubscribeResult(
                success=False,
                message=f"Error: {str(e)}",
                method="link",
                url=link_data.get('href', '')
            )
    
    def unsubscribe_from_email(self, email_data: Dict, user_email_address: str = None) -> List[UnsubscribeResult]:
        """Main method to attempt unsubscribe from an email"""
        results = []
        
        # Extract email content from the email_data dictionary
        email_content = email_data.get('body_html') or email_data.get('body_text')
        if not email_content:
            results.append(UnsubscribeResult(
                success=False,
                message="No email content (HTML or text) found for unsubscribe.",
                method="none",
                url=""
            ))
            return results

        # Extract unsubscribe links
        unsubscribe_links = self.extract_unsubscribe_links(email_content)
        
        if not unsubscribe_links:
            results.append(UnsubscribeResult(
                success=False,
                message="No unsubscribe links found in email",
                method="none",
                url=""
            ))
            return results
        
        # Try each unsubscribe link
        for link in unsubscribe_links:
            try:
                logger.info(f"Attempting unsubscribe via: {link}")
                
                # Visit the unsubscribe page
                soup, response = self.visit_unsubscribe_page(link)
                base_url = response.url
                
                # Look for forms first
                form_data = self.find_unsubscribe_form(soup)
                if form_data:
                    result = self.attempt_form_unsubscribe(form_data, base_url, user_email_address)
                    results.append(result)
                    if result.success:
                        break  # Success, no need to try other methods
                
                # If no form or form failed, look for buttons/links
                buttons = self.find_unsubscribe_buttons(soup)
                for button in buttons:
                    result = self.attempt_link_unsubscribe(button, base_url)
                    results.append(result)
                    if result.success:
                        break
                
                # Add delay between attempts
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Error processing unsubscribe link {link}: {e}")
                results.append(UnsubscribeResult(
                    success=False,
                    message=f"Error processing link: {str(e)}",
                    method="error",
                    url=link
                ))
        
        return results

# Usage example
def main():
    # Example usage
    unsubscriber = SmartUnsubscriber()
    
    # Sample email data with unsubscribe link
    sample_email_data = {
        'subject': 'Newsletter',
        'from': 'newsletter@example.com',
        'body_html': """
    <html>
    <body>
        <p>Thank you for subscribing to our newsletter!</p>
        <p>If you no longer wish to receive these emails, 
           <a href="https://example.com/unsubscribe?token=abc123">click here to unsubscribe</a>
        </p>
    </body>
    </html>
    """,
        'body_text': "Thank you for subscribing! To unsubscribe: https://example.com/unsubscribe?token=abc123"
    }
    
    results = unsubscriber.unsubscribe_from_email(sample_email_data, "user@example.com")
    
    for result in results:
        print(f"Method: {result.method}")
        print(f"Success: {result.success}")
        print(f"Message: {result.message}")
        print(f"URL: {result.url}")
        print("-" * 50)

if __name__ == "__main__":
    main()


