import os
import time
import requests
import urllib3
import atexit


# urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class SAPService:
    session_id = None
    session_created_at = None
    SESSION_TIMEOUT = 1800

    @classmethod
    def login(cls):
        base_url = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")
        url = f"{base_url}/Login"

        payload = {
            "UserName": os.getenv("SAP_USERNAME", ""),
            "Password": os.getenv("SAP_PASSWORD", ""),
            "CompanyDB": os.getenv("SAP_COMPANY_DB", ""),
        }

        headers = {"Content-Type": "application/json"}

        resp = requests.post(url, json=payload, headers=headers, verify=False, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        cls.session_id = data.get("SessionId")
        cls.session_created_at = time.time()

        if not cls.session_id:
            raise RuntimeError(f"SAP login did not return SessionId. Response: {data}")

        return cls.session_id

    @classmethod
    def ensure_session(cls):
        if not cls.session_id:
            return cls.login()
        if time.time() - cls.session_created_at > cls.SESSION_TIMEOUT:
            try:
                cls.get_company_info()
            except Exception:
                return cls.login()
        return cls.session_id

    @classmethod
    def get_company_info(cls):
        base_url = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")
        url = f"{base_url}/CompanyService_GetCompanyInfo"
        headers = {
            "Cookie": f"B1SESSION={cls.session_id}",
            "Content-Type": "application/json",
        }

        resp = requests.post(url, headers=headers, json={}, verify=False, timeout=15)
        resp.raise_for_status()
        return resp.json()

    @classmethod
    def logout(cls):
        """Call SAP Logout if session is active"""
        if cls.session_id:
            base_url = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")
            url = f"{base_url}/Logout"
            try:
                requests.post(url, headers={"Cookie": f"B1SESSION={cls.session_id}"}, verify=False, timeout=10)
            except Exception as e:
                print(f"⚠️ SAP logout failed: {e}")
            finally:
                cls.session_id = None
                cls.session_created_at = None
                print("✅ SAP session logged out")


# Register logout on shutdown
atexit.register(SAPService.logout)
