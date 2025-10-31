import requests
from datetime import datetime, timedelta
import io
from django.conf import settings

PARTNER_API_BASE = settings.EMAIL_AUTOMATION['PARTNER_API_BASE']
PARTNER_USERNAME = settings.EMAIL_AUTOMATION['PARTNER_USERNAME']
PARTNER_PASSWORD = settings.EMAIL_AUTOMATION['PARTNER_PASSWORD']

CASE_API_MAPPING = {
    1: f"{PARTNER_API_BASE}/automation/upload/one-to-one/",
    2: f"{PARTNER_API_BASE}/automation/upload/one-to-many/",
    3: f"{PARTNER_API_BASE}/automation/upload/many-to-many/",
}


class PartnerAPIClient:
    def __init__(self):
        self.access_token = None
        self.token_expires_at = None
        
    def login(self):
        try:
            response = requests.post(
                f"{PARTNER_API_BASE}/auth/login/",
                json={"username": PARTNER_USERNAME, "password": PARTNER_PASSWORD},
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get("access")
                self.token_expires_at = datetime.now() + timedelta(minutes=45)
                return True
            return False
        except:
            return False
    
    def ensure_authenticated(self):
        if not self.access_token or datetime.now() >= (self.token_expires_at - timedelta(minutes=5)):
            return self.login()
        return True
    
    def upload_pdf(self, case_number, pdf_binary, pdf_name, metadata=None):
        if not self.ensure_authenticated():
            return {"success": False, "error": "Authentication failed"}
        
        api_url = CASE_API_MAPPING.get(case_number)
        if not api_url:
            return {"success": False, "error": "Invalid case number"}
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            files = {'file': (pdf_name, io.BytesIO(pdf_binary), 'application/pdf')}
            
            response = requests.post(api_url, headers=headers, files=files, timeout=360)
            
            if response.status_code in [200, 201]:
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "response": response.json() if response.text else {}
                }
            elif response.status_code == 401:
                # Retry once
                if self.login():
                    headers = {"Authorization": f"Bearer {self.access_token}"}
                    response = requests.post(api_url, headers=headers, files=files, timeout=360)
                    if response.status_code in [200, 201]:
                        return {"success": True, "status_code": response.status_code}
            
            return {"success": False, "error": f"Status {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}