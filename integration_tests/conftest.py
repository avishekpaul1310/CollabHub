"""
Configuration for pytest-based integration tests for CollabHub.

This file sets up fixtures and test environment configuration for integration testing.
"""

import pytest
import requests
import time
import os
import subprocess
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# Base URL for API requests during testing
BASE_URL = os.getenv("TEST_API_URL", "http://localhost:5000/api")

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up the test environment before all tests run."""
    # Check if we should start the server locally for testing
    should_start_server = os.getenv("START_SERVER_FOR_TESTS", "false").lower() == "true"
    
    server_process = None
    
    if should_start_server:
        print("Starting the server for tests...")
        # Start the server in a separate process
        server_process = subprocess.Popen(
            ["python", "app.py", "--test"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Give the server some time to start up
        time.sleep(5)
        
        # Verify the server is responding
        max_retries = 5
        for i in range(max_retries):
            try:
                response = requests.get(f"{BASE_URL}/health")
                if response.status_code == 200:
                    print("Server is ready for tests.")
                    break
            except requests.exceptions.ConnectionError:
                if i < max_retries - 1:
                    print(f"Server not ready yet, retrying in 2 seconds...")
                    time.sleep(2)
                else:
                    print("Server failed to start.")
                    if server_process:
                        server_process.terminate()
                        stdout, stderr = server_process.communicate()
                        print(f"Server stdout: {stdout.decode()}")
                        print(f"Server stderr: {stderr.decode()}")
                    pytest.fail("Server failed to start")
    
    # Reset the test database
    try:
        requests.post(f"{BASE_URL}/testing/reset")
        print("Test database reset successfully.")
    except:
        print("Warning: Could not reset test database. Tests may fail due to existing data.")
    
    # Return from setup
    yield
    
    # Cleanup after all tests
    if server_process:
        print("Stopping test server...")
        server_process.terminate()
        server_process.wait()

@pytest.fixture
def api_client():
    """Create an API client for making requests during tests."""
    class APIClient:
        def __init__(self):
            self.base_url = BASE_URL
            self.token = None
        
        def register(self, user_data):
            """Register a new user and store the token."""
            response = requests.post(f"{self.base_url}/users/register", json=user_data)
            if response.status_code == 201:
                self.token = response.json().get("token")
            return response
        
        def login(self, credentials):
            """Login and store the token."""
            response = requests.post(f"{self.base_url}/users/login", json=credentials)
            if response.status_code == 200:
                self.token = response.json().get("token")
            return response
        
        def get(self, endpoint, params=None, include_auth=True):
            """Make a GET request to the API."""
            headers = {}
            if include_auth and self.token:
                headers["Authorization"] = f"Bearer {self.token}"
                
            return requests.get(f"{self.base_url}/{endpoint}", params=params, headers=headers)
        
        def post(self, endpoint, data=None, files=None, include_auth=True):
            """Make a POST request to the API."""
            headers = {}
            if include_auth and self.token:
                headers["Authorization"] = f"Bearer {self.token}"
                
            return requests.post(f"{self.base_url}/{endpoint}", json=data, files=files, headers=headers)
        
        def put(self, endpoint, data=None, include_auth=True):
            """Make a PUT request to the API."""
            headers = {}
            if include_auth and self.token:
                headers["Authorization"] = f"Bearer {self.token}"
                
            return requests.put(f"{self.base_url}/{endpoint}", json=data, headers=headers)
        
        def patch(self, endpoint, data=None, include_auth=True):
            """Make a PATCH request to the API."""
            headers = {}
            if include_auth and self.token:
                headers["Authorization"] = f"Bearer {self.token}"
                
            return requests.patch(f"{self.base_url}/{endpoint}", json=data, headers=headers)
        
        def delete(self, endpoint, include_auth=True):
            """Make a DELETE request to the API."""
            headers = {}
            if include_auth and self.token:
                headers["Authorization"] = f"Bearer {self.token}"
                
            return requests.delete(f"{self.base_url}/{endpoint}", headers=headers)
    
    return APIClient()

@pytest.fixture
def test_user1():
    """Fixture providing test user 1 data."""
    return {
        "email": "testuser1@example.com",
        "password": "SecurePass123!",
        "firstName": "Test",
        "lastName": "User1",
        "username": "testuser1"
    }

@pytest.fixture
def test_user2():
    """Fixture providing test user 2 data."""
    return {
        "email": "testuser2@example.com",
        "password": "SecurePass123!",
        "firstName": "Test",
        "lastName": "User2",
        "username": "testuser2"
    }

@pytest.fixture
def authenticated_user1(api_client, test_user1):
    """Fixture providing an authenticated user 1."""
    api_client.register(test_user1)
    return api_client

@pytest.fixture
def authenticated_user2(api_client, test_user2):
    """Fixture providing an authenticated user 2."""
    api_client.register(test_user2)
    return api_client