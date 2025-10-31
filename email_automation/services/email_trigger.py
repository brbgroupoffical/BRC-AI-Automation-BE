import msal
import requests
from flask import Flask, request
from datetime import datetime, timedelta, timezone
import os
import time
from threading import Thread
import base64
import json
from .gemini_classifier import classify_pdf_case
from .partner_api import PartnerAPIClient
import io
from django.conf import settings

# Configuration from Django settings
CLIENT_ID = settings.EMAIL_AUTOMATION['CLIENT_ID']
TENANT_ID = settings.EMAIL_AUTOMATION['TENANT_ID']
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://graph.microsoft.com/Mail.Read", "https://graph.microsoft.com/User.Read"]
WEBHOOK_URL = settings.EMAIL_AUTOMATION['WEBHOOK_URL']

# Token cache file location - store in Django project root
BASE_DIR = settings.BASE_DIR
TOKEN_CACHE_FILE = os.path.join(BASE_DIR, '.msal_token_cache.bin')

app = Flask(__name__)


class TokenCache:
    """Persistent token cache that saves to Django project directory"""
    
    def __init__(self, cache_file):
        self.cache_file = cache_file
        self.cache = msal.SerializableTokenCache()
        
        # Load existing cache if it exists
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    self.cache.deserialize(f.read())
                print(f"[CACHE] Loaded token cache from {self.cache_file}")
            except Exception as e:
                print(f"[CACHE] Could not load cache: {e}")
    
    def save(self):
        """Save cache to file if it has changed"""
        if self.cache.has_state_changed:
            try:
                with open(self.cache_file, 'w') as f:
                    f.write(self.cache.serialize())
                # Set secure permissions (read/write for owner only)
                os.chmod(self.cache_file, 0o600)
                print(f"[CACHE] Saved token cache to {self.cache_file}")
            except Exception as e:
                print(f"[CACHE] Could not save cache: {e}")
    
    def get_cache(self):
        return self.cache


class EmailTrigger:
    def __init__(self):
        # Initialize token cache
        self.token_cache = TokenCache(TOKEN_CACHE_FILE)
        
        # Initialize MSAL app with persistent cache
        self.app = msal.PublicClientApplication(
            CLIENT_ID, 
            authority=AUTHORITY,
            token_cache=self.token_cache.get_cache()
        )
        
        self.access_token = None
        self.token_expiry = None
        self.subscription_id = None
        self.user_email = None
        self.account = None
        
        self.processed_messages = set()
        self.processing_in_progress = set()
        
        self.last_classification_time = None
        self.min_classification_interval = 30
        
        self.api_client = PartnerAPIClient()
        
    def is_token_expired(self):
        if not self.token_expiry:
            return True
        return datetime.now() >= (self.token_expiry - timedelta(minutes=5))
    
    def refresh_token(self):
        """Refresh token using cached refresh token"""
        if not self.account:
            print(f"[AUTH] No account stored, need full authentication")
            return False
        
        try:
            print(f"[AUTH] Refreshing access token from cache...")
            result = self.app.acquire_token_silent(SCOPES, account=self.account)
            
            if result and "access_token" in result:
                self.access_token = result["access_token"]
                self.token_expiry = datetime.now() + timedelta(hours=1)
                
                # Save updated cache
                self.token_cache.save()
                
                print(f"[AUTH] ✓ Token refreshed successfully")
                print(f"[AUTH] Expires at: {self.token_expiry.strftime('%Y-%m-%d %H:%M:%S')}")
                return True
            else:
                print(f"[AUTH] ✗ Token refresh failed")
                print(f"[AUTH] Need to re-authenticate (device code)")
                return False
                
        except Exception as e:
            print(f"[AUTH] ✗ Token refresh exception: {str(e)}")
            return False
    
    def ensure_token_valid(self):
        """Ensure we have a valid token, refresh if needed"""
        if self.is_token_expired():
            print(f"[AUTH] Token expired, attempting refresh...")
            if not self.refresh_token():
                print(f"[AUTH] ✗ CRITICAL: Token refresh failed!")
                print(f"[AUTH] System will attempt to use cached refresh token on next request")
                return False
        return True
        
    def authenticate(self):
        """Authenticate - uses cached token if available, otherwise device code"""
        
        print(f"[AUTH] Checking for cached tokens in: {TOKEN_CACHE_FILE}")
        
        # Try to use cached token first
        accounts = self.app.get_accounts()
        
        if accounts:
            self.account = accounts[0]
            print(f"[AUTH] Found cached account: {self.account['username']}")
            
            # Try silent token acquisition
            result = self.app.acquire_token_silent(SCOPES, account=self.account)
            
            if result and "access_token" in result:
                self.access_token = result["access_token"]
                self.user_email = self.account['username']
                self.token_expiry = datetime.now() + timedelta(hours=1)
                
                print(f"[AUTH] ✓ Using cached token for: {self.user_email}")
                print(f"[AUTH] Token expires at: {self.token_expiry.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"[AUTH] No device code needed! 🎉")
                
                # Save cache (in case it was updated)
                self.token_cache.save()
                
                return True
            else:
                print(f"[AUTH] Cached token expired, attempting refresh...")
                # Try refresh
                if self.refresh_token():
                    return True
        
        # No cached token or refresh failed - need device code authentication
        print("\n" + "="*60)
        print("[AUTH] FIRST TIME SETUP - Device Code Authentication")
        print("="*60)
        print("This is a ONE-TIME setup. Token will be saved for future use.")
        print("="*60)
        
        flow = self.app.initiate_device_flow(scopes=SCOPES)
        
        if "user_code" not in flow:
            print(f"[AUTH] Failed to create device flow")
            return False
        
        print(f"\n{flow['message']}")
        print("\n📱 Authentication Steps:")
        print(f"1. Open browser: {flow['verification_uri']}")
        print(f"2. Enter code: {flow['user_code']}")
        print(f"3. Sign in with: ai@brc.com.sa")
        print(f"4. Wait for confirmation below...")
        print("="*60 + "\n")
        
        result = self.app.acquire_token_by_device_flow(flow)
        
        if "access_token" in result:
            self.access_token = result["access_token"]
            self.token_expiry = datetime.now() + timedelta(hours=1)
            
            # Get and store account
            accounts = self.app.get_accounts()
            if accounts:
                self.account = accounts[0]
            
            # Get user info
            user_info = requests.get(
                "https://graph.microsoft.com/v1.0/me", 
                headers={"Authorization": f"Bearer {self.access_token}"}
            ).json()
            
            self.user_email = user_info.get('mail') or user_info.get('userPrincipalName')
            
            # IMPORTANT: Save token to cache file
            self.token_cache.save()
            
            print("\n" + "="*60)
            print("[AUTH] ✓ AUTHENTICATION SUCCESSFUL!")
            print("="*60)
            print(f"Logged in as: {self.user_email}")
            print(f"Token expires: {self.token_expiry.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Token saved to: {TOKEN_CACHE_FILE}")
            print("\n✅ You will NOT need to authenticate again!")
            print("✅ Token will auto-refresh for ~90 days")
            print("="*60 + "\n")
            
            return True
        else:
            print(f"[AUTH] ✗ Authentication failed")
            return False
    
    def get_email_details(self, message_id):
        if not self.ensure_token_valid():
            return None
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}"
        params = {"$select": "id,subject,from,receivedDateTime,hasAttachments"}
        
        try:
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 401:
                print(f"[AUTH] 401 error, attempting token refresh...")
                if self.refresh_token():
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    response = requests.get(url, headers=headers, params=params)
            
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            print(f"Error getting email: {e}")
            return None
    
    def check_pdf_attachments(self, message_id):
        if not self.ensure_token_valid():
            return []

        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments"

        try:
            response = requests.get(url, headers=headers)
            
            if response.status_code == 401:
                if self.refresh_token():
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                attachments = response.json().get("value", [])
                return [
                    {
                        'id': att.get('id'),
                        'name': att.get('name'),
                        'size': att.get('size')
                    }
                    for att in attachments
                    if att.get("@odata.type") == "#microsoft.graph.fileAttachment"
                    and att.get("name", "").lower().endswith('.pdf')
                ]
            return []
        except Exception as e:
            print(f"Error checking attachments: {e}")
            return []
    
    def download_pdf_content(self, message_id, pdf_attachment):
        if not self.ensure_token_valid():
            return None
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments/{pdf_attachment['id']}"
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 401:
                if self.refresh_token():
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                content_bytes = response.json().get("contentBytes")
                if content_bytes:
                    return base64.b64decode(content_bytes)
            return None
        except Exception as e:
            print(f"Error downloading PDF: {e}")
            return None
    
    def process_email(self, message_id):
        """Process single email"""
        print(f"\n{'='*80}")
        print(f"Processing email: {message_id[:20]}...")
        
        email_details = self.get_email_details(message_id)
        if not email_details or not email_details.get('hasAttachments'):
            print("No attachments")
            return
        
        pdf_attachments = self.check_pdf_attachments(message_id)
        if not pdf_attachments:
            print("No PDF attachments")
            return
        
        print(f"Found {len(pdf_attachments)} PDF(s)")
        
        for pdf_att in pdf_attachments:
            pdf_binary = self.download_pdf_content(message_id, pdf_att)
            if not pdf_binary:
                continue
            
            # Classify
            classification = classify_pdf_case(pdf_binary, pdf_att['name'])
            if not classification:
                continue
            
            print(f"[CLASSIFY] Case {classification['case_number']}: {classification['case_name']}")
            
            # Upload to partner API
            result = self.api_client.upload_pdf(
                case_number=classification['case_number'],
                pdf_binary=pdf_binary,
                pdf_name=pdf_att['name']
            )
            
            if result['success']:
                print(f"[UPLOAD] ✓ Success")
            else:
                print(f"[UPLOAD] ✗ Failed: {result.get('error')}")
    
    def create_subscription(self):
        if not self.ensure_token_valid():
            return None
        
        expiration = datetime.now(timezone.utc) + timedelta(days=3)
        subscription_data = {
            "changeType": "created,updated",
            "notificationUrl": WEBHOOK_URL,
            "resource": "me/messages",
            "expirationDateTime": expiration.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        }
        
        response = requests.post(
            "https://graph.microsoft.com/v1.0/subscriptions",
            headers={"Authorization": f"Bearer {self.access_token}"},
            json=subscription_data
        )
        
        if response.status_code == 201:
            self.subscription_id = response.json()["id"]
            print(f"[SUBSCRIPTION] ✓ Created: {self.subscription_id}")
            return self.subscription_id
        else:
            print(f"[SUBSCRIPTION] ✗ Failed: {response.status_code}")
            return None


email_trigger = EmailTrigger()


@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET' or request.args.get('validationToken'):
        return request.args.get('validationToken'), 200
    
    if request.method == 'POST':
        try:
            data = request.get_json(force=True)
            if data and 'value' in data:
                for notification in data['value']:
                    resource = notification.get('resource', '')
                    if 'Messages/' in resource:
                        message_id = resource.split('Messages/')[-1]
                        
                        if message_id not in email_trigger.processed_messages:
                            email_trigger.processed_messages.add(message_id)
                            email_trigger.process_email(message_id)
        except Exception as e:
            print(f"[WEBHOOK] Error: {e}")
        
        return '', 202


@app.route('/status', methods=['GET'])
def status():
    return {
        'status': 'running',
        'monitoring': email_trigger.user_email,
        'processed_count': len(email_trigger.processed_messages),
        'token_valid': not email_trigger.is_token_expired(),
        'token_cache_file': TOKEN_CACHE_FILE,
        'cache_exists': os.path.exists(TOKEN_CACHE_FILE)
    }


def token_refresh_worker():
    """Background token refresh every 50 minutes"""
    while True:
        try:
            time.sleep(3000)  # 50 minutes
            print(f"\n[BACKGROUND] Periodic token refresh check...")
            if email_trigger.is_token_expired():
                print(f"[BACKGROUND] Token expired, refreshing...")
                email_trigger.refresh_token()
            else:
                print(f"[BACKGROUND] Token still valid until {email_trigger.token_expiry.strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"[BACKGROUND] Error: {e}")


def start_webhook_server():
    """Start Flask webhook server"""
    print(f"[STARTUP] Token cache location: {TOKEN_CACHE_FILE}")
    
    # Authenticate (will use cache if available)
    if not email_trigger.authenticate():
        print("[ERROR] Authentication failed")
        return
    
    # Start token refresh background worker
    refresh_thread = Thread(target=token_refresh_worker, daemon=True)
    refresh_thread.start()
    print("[STARTUP] ✓ Token auto-refresh enabled (every 50 minutes)")
    
    # Create subscription
    if not email_trigger.create_subscription():
        print("[ERROR] Subscription failed")
        return
    
    print(f"\n{'='*60}")
    print(f"[WEBHOOK] Server starting on port 5000...")
    print(f"[WEBHOOK] Monitoring: {email_trigger.user_email}")
    print(f"[WEBHOOK] Token cache: {TOKEN_CACHE_FILE}")
    print(f"{'='*60}\n")
    
    # Start Flask
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
