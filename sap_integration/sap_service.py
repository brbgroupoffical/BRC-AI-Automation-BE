import os
import time
import requests
import urllib3
import atexit
import logging

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SAPService:
    session = None  # Changed: Use requests.Session object
    session_id = None
    session_created_at = None
    SESSION_TIMEOUT = 1800

    @classmethod
    def _get_session(cls):
        """Initialize session if not exists"""
        if cls.session is None:
            cls.session = requests.Session()
        return cls.session

    @classmethod
    def login(cls):
        """Login to SAP Service Layer and establish session"""
        # Validate environment variables
        base_url = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")
        username = os.getenv("SAP_USERNAME", "")
        password = os.getenv("SAP_PASSWORD", "")
        company_db = os.getenv("SAP_COMPANY_DB", "")

        if not all([base_url, username, password, company_db]):
            raise ValueError(
                "Missing required environment variables: "
                "SAP_SERVICE_LAYER_URL, SAP_USERNAME, SAP_PASSWORD, SAP_COMPANY_DB"
            )

        url = f"{base_url}/Login"
        payload = {
            "UserName": username,
            "Password": password,
            "CompanyDB": company_db,
        }
        headers = {"Content-Type": "application/json"}

        try:
            # Use session object to maintain cookies
            session = cls._get_session()
            
            logger.info(f"Attempting login to SAP at {base_url}")
            resp = session.post(url, json=payload, headers=headers, verify=False, timeout=15)
            resp.raise_for_status()
            
            data = resp.json()
            cls.session_id = data.get("SessionId")
            cls.session_created_at = time.time()

            if not cls.session_id:
                raise RuntimeError(f"SAP login did not return SessionId. Response: {data}")

            logger.info(f"✅ SAP login successful. SessionId: {cls.session_id}")
            
            # Log cookies for debugging
            logger.debug(f"Session cookies: {session.cookies.get_dict()}")
            
            return cls.session_id

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ SAP login failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            raise

    @classmethod
    def ensure_session(cls):
        """Ensure valid session exists, refresh if needed"""
        # If no session exists, login
        if not cls.session_id:
            logger.info("No active session, logging in...")
            return cls.login()

        # Check if session has timed out
        if time.time() - cls.session_created_at > cls.SESSION_TIMEOUT:
            logger.info("Session timeout reached, validating session...")
            try:
                cls.get_company_info()
                logger.info("Session still valid")
            except Exception as e:
                logger.warning(f"Session validation failed: {e}. Re-logging in...")
                return cls.login()

        return cls.session_id

    @classmethod
    def get_company_info(cls):
        """Test API call to validate session"""
        if not cls.session_id:
            raise RuntimeError("No active session. Call login() first.")

        base_url = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")
        url = f"{base_url}/CompanyService_GetCompanyInfo"
        
        try:
            # Use the session object - cookies are automatically included
            session = cls._get_session()
            resp = session.post(url, json={}, verify=False, timeout=15)
            resp.raise_for_status()
            
            logger.debug("Company info retrieved successfully")
            return resp.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get company info: {e}")
            raise

    @classmethod
    def make_request(cls, method, endpoint, **kwargs):
        """
        Make an authenticated request to SAP Service Layer
        
        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint (e.g., '/Items', '/BusinessPartners')
            **kwargs: Additional arguments to pass to requests
            
        Returns:
            Response object
        """
        cls.ensure_session()
        
        base_url = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")
        url = f"{base_url}{endpoint}"
        
        # Use the session object
        session = cls._get_session()
        
        # Set default headers if not provided
        if 'headers' not in kwargs:
            kwargs['headers'] = {}
        if 'Content-Type' not in kwargs['headers']:
            kwargs['headers']['Content-Type'] = 'application/json'
        
        # Ensure verify=False is set
        kwargs['verify'] = False
        
        try:
            resp = session.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {method} {endpoint} - {e}")
            raise

    @classmethod
    def logout(cls):
        """Call SAP Logout if session is active"""
        if cls.session_id:
            base_url = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")
            url = f"{base_url}/Logout"
            
            try:
                session = cls._get_session()
                session.post(url, verify=False, timeout=10)
                logger.info("✅ SAP session logged out successfully")
            except Exception as e:
                logger.warning(f"⚠️ SAP logout failed: {e}")
            finally:
                cls.session_id = None
                cls.session_created_at = None
                if cls.session:
                    cls.session.close()
                    cls.session = None


# Register logout on shutdown
atexit.register(SAPService.logout)


# Example usage
if __name__ == "__main__":
    # Set environment variables (for testing)
    # os.environ["SAP_SERVICE_LAYER_URL"] = "https://your-server:50000/b1s/v1"
    # os.environ["SAP_USERNAME"] = "manager"
    # os.environ["SAP_PASSWORD"] = "your_password"
    # os.environ["SAP_COMPANY_DB"] = "SBODemoUS"
    
    try:
        # Login
        SAPService.login()
        
        # Test company info
        info = SAPService.get_company_info()
        print(f"Company Info: {info}")
        
        # Example: Make a custom request
        # response = SAPService.make_request('GET', '/Items?$top=5')
        # print(response.json())
        
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        SAPService.logout()