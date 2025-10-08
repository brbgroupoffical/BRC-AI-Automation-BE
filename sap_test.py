"""
SAP Service Layer Authentication Module

This module provides functionality to authenticate with SAP Business One Service Layer.
Includes proper error handling, SSL verification management, and session management.
"""

import requests
import urllib3
from typing import Optional, Dict, Any
import logging
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class SAPCredentials:
    """Data class to hold SAP Service Layer credentials."""
    url: str
    database: str
    username: str
    password: str
    
    def __post_init__(self):
        """Validate credentials after initialization."""
        if not all([self.url, self.database, self.username, self.password]):
            raise ValueError("All credentials must be provided")
        
        # Ensure URL doesn't end with a slash
        self.url = self.url.rstrip('/')


class SAPServiceLayerAuth:
    """
    Handles authentication with SAP Business One Service Layer.
    
    Attributes:
        credentials: SAPCredentials object containing connection details
        session: requests.Session object for maintaining connection
        session_id: Current session ID from SAP
        verify_ssl: Boolean to control SSL verification
    """
    
    def __init__(self, credentials: SAPCredentials, verify_ssl: bool = True):
        """
        Initialize the SAP Service Layer authentication handler.
        
        Args:
            credentials: SAPCredentials object with connection details
            verify_ssl: Whether to verify SSL certificates (default: True)
        """
        self.credentials = credentials
        self.session = requests.Session()
        self.session_id: Optional[str] = None
        self.verify_ssl = verify_ssl
        
        # Disable SSL warnings if verification is disabled
        if not self.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            logger.warning(
                "SSL verification is disabled. This is not recommended for production environments. "
                "Your connection may be vulnerable to man-in-the-middle attacks."
            )
    
    def login(self) -> bool:
        """
        Authenticate with SAP Service Layer and establish a session.
        
        Returns:
            bool: True if login successful, False otherwise
            
        Raises:
            requests.exceptions.RequestException: For network-related errors
            ValueError: For invalid credentials or response format
        """
        login_url = f"{self.credentials.url}/Login"
        
        payload = {
            "CompanyDB": self.credentials.database,
            "UserName": self.credentials.username,
            "Password": self.credentials.password
        }
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        try:
            logger.info(f"Attempting to login to SAP Service Layer at {self.credentials.url}")
            
            response = self.session.post(
                login_url,
                json=payload,
                headers=headers,
                verify=self.verify_ssl,
                timeout=30
            )
            
            # Check if request was successful
            response.raise_for_status()
            
            # Parse response
            response_data = response.json()
            
            # Extract session ID
            self.session_id = response_data.get('SessionId')
            
            if not self.session_id:
                logger.error("Login response did not contain SessionId")
                return False
            
            # Store session cookies
            logger.info(f"Successfully logged in. Session ID: {self.session_id}")
            return True
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error during login: {e}")
            if e.response is not None:
                try:
                    error_detail = e.response.json()
                    logger.error(f"Error details: {error_detail}")
                except ValueError:
                    logger.error(f"Response text: {e.response.text}")
            return False
            
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: Unable to connect to {self.credentials.url}")
            logger.error(f"Details: {e}")
            return False
            
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout error: Request took too long to complete")
            logger.error(f"Details: {e}")
            return False
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error during login: {e}")
            return False
            
        except ValueError as e:
            logger.error(f"Invalid JSON response: {e}")
            return False
            
        except Exception as e:
            logger.error(f"Unexpected error during login: {e}")
            return False
    
    def logout(self) -> bool:
        """
        Logout from SAP Service Layer and close the session.
        
        Returns:
            bool: True if logout successful, False otherwise
        """
        if not self.session_id:
            logger.warning("No active session to logout from")
            return False
        
        logout_url = f"{self.credentials.url}/Logout"
        
        try:
            logger.info("Logging out from SAP Service Layer")
            
            response = self.session.post(
                logout_url,
                verify=self.verify_ssl,
                timeout=30
            )
            
            response.raise_for_status()
            
            logger.info("Successfully logged out")
            self.session_id = None
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error during logout: {e}")
            return False
    
    def get_session(self) -> requests.Session:
        """
        Get the authenticated session object.
        
        Returns:
            requests.Session: The authenticated session
            
        Raises:
            RuntimeError: If no active session exists
        """
        if not self.session_id:
            raise RuntimeError("No active session. Please login first.")
        
        return self.session
    
    def __enter__(self):
        """Context manager entry."""
        self.login()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.logout()


def main():
    """Example usage of the SAP Service Layer authentication."""
    
    # Configuration
    credentials = SAPCredentials(
        url="https://10.10.10.32:50000/b1s/v2",
        database="TEST",
        username="HOFT1",
        password="s@p9510"
    )
    
    # Example 1: Using context manager (recommended)
    try:
        with SAPServiceLayerAuth(credentials, verify_ssl=False) as sap:
            print(f"Session ID: {sap.session_id}")
            # You can now use sap.get_session() to make API calls
            
    except Exception as e:
        logger.error(f"Login failed: {e}")
    
    # Example 2: Manual login/logout
    sap_auth = SAPServiceLayerAuth(credentials, verify_ssl=False)
    
    if sap_auth.login():
        print(f"Login successful! Session ID: {sap_auth.session_id}")
        
        # Perform your API operations here
        # session = sap_auth.get_session()
        # response = session.get(f"{credentials.url}/Items", verify=False)
        
        sap_auth.logout()
    else:
        print("Login failed. Check logs for details.")


if __name__ == "__main__":
    main()