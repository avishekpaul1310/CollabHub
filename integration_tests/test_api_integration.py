"""
Integration tests for CollabHub API endpoints.

This file contains comprehensive integration tests covering user authentication,
workspace management, project and task functionality, and search capabilities.
"""

import unittest
import json
import time
from datetime import datetime, timedelta
import requests
from unittest import mock

# Base URL for API requests
BASE_URL = "http://localhost:5000/api"

class CollabHubIntegrationTest(unittest.TestCase):
    """Test class for CollabHub API integration testing."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment before running any tests."""
        # Clear test database or use a separate test database
        # This would typically involve a direct database connection or a special API endpoint
        try:
            requests.post(f"{BASE_URL}/testing/reset")
        except:
            print("Warning: Could not reset test database. Tests may fail due to existing data.")
            
        # Test user data
        cls.test_user1 = {
            "email": "testuser1@example.com",
            "password": "SecurePass123!",
            "firstName": "Test",
            "lastName": "User1",
            "username": "testuser1"
        }
        
        cls.test_user2 = {
            "email": "testuser2@example.com",
            "password": "SecurePass123!",
            "firstName": "Test",
            "lastName": "User2",
            "username": "testuser2"
        }
        
        cls.test_workspace = {
            "name": "Test Workspace",
            "description": "A workspace created for testing"
        }
        
        cls.test_project = {
            "name": "Test Project",
            "description": "A project created for testing"
        }
        
        cls.test_task = {
            "title": "Test Task",
            "description": "A task created for testing",
            "priority": "high",
            "status": "todo",
            "dueDate": (datetime.now() + timedelta(days=3)).isoformat()
        }
    
    def setUp(self):
        """Set up before each test method."""
        # Register and login first user
        response = requests.post(f"{BASE_URL}/users/register", json=self.test_user1)
        self.assertEqual(response.status_code, 201)
        self.user1_data = response.json()
        self.user1_token = self.user1_data["token"]
        self.user1_id = self.user1_data["user"]["_id"]
        
        # Register and login second user
        response = requests.post(f"{BASE_URL}/users/register", json=self.test_user2)
        self.assertEqual(response.status_code, 201)
        self.user2_data = response.json()
        self.user2_token = self.user2_data["token"]
        self.user2_id = self.user2_data["user"]["_id"]
        
        # Create a workspace
        headers = {"Authorization": f"Bearer {self.user1_token}"}
        response = requests.post(f"{BASE_URL}/workspaces", json=self.test_workspace, headers=headers)
        self.assertEqual(response.status_code, 201)
        self.workspace_data = response.json()
        self.workspace_id = self.workspace_data["_id"]
        
        # Create a project
        response = requests.post(
            f"{BASE_URL}/workspaces/{self.workspace_id}/projects", 
            json=self.test_project,
            headers=headers
        )
        self.assertEqual(response.status_code, 201)
        self.project_data = response.json()
        self.project_id = self.project_data["_id"]

    def test_user_authentication_flow(self):
        """Test complete user authentication flow including registration, login, and profile access."""
        # Test data
        test_user = {
            "email": "authtest@example.com",
            "password": "AuthTest123!",
            "firstName": "Auth",
            "lastName": "Test",
            "username": "authtest"
        }
        
        # 1. Register new user
        response = requests.post(f"{BASE_URL}/users/register", json=test_user)
        self.assertEqual(response.status_code, 201)
        user_data = response.json()
        self.assertIn("token", user_data)
        self.assertIn("user", user_data)
        self.assertEqual(user_data["user"]["email"], test_user["email"])
        
        # 2. Logout (if applicable)
        # Note: JWT-based auth typically doesn't have explicit logout on server side
        token = user_data["token"]
        
        # 3. Login with credentials
        login_data = {
            "email": test_user["email"],
            "password": test_user["password"]
        }
        response = requests.post(f"{BASE_URL}/users/login", json=login_data)
        self.assertEqual(response.status_code, 200)
        login_response = response.json()
        self.assertIn("token", login_response)
        
        # 4. Access profile with token
        headers = {"Authorization": f"Bearer {login_response['token']}"}
        response = requests.get(f"{BASE_URL}/users/me", headers=headers)
        self.assertEqual(response.status_code, 200)
        profile = response.json()
        self.assertEqual(profile["email"], test_user["email"])
        
        # 5. Test incorrect password
        wrong_login = {
            "email": test_user["email"],
            "password": "WrongPassword123!"
        }
        response = requests.post(f"{BASE_URL}/users/login", json=wrong_login)
        self.assertEqual(response.status_code, 401)
        
        # 6. Test invalid token
        headers = {"Authorization": "Bearer invalidtoken"}
        response = requests.get(f"{BASE_URL}/users/me", headers=headers)
        self.assertEqual(response.status_code, 401)
        
        # 7. Test registration with existing email
        response = requests.post(f"{BASE_URL}/users/register", json=test_user)
        self.assertEqual(response.status_code, 400)  # Should fail with existing email

    def test_workspace_management(self):
        """Test workspace creation, update, and member management."""
        headers = {"Authorization": f"Bearer {self.user1_token}"}
        
        # 1. Create a new workspace
        new_workspace = {
            "name": "Another Test Workspace",
            "description": "Another workspace for testing purposes"
        }
        response = requests.post(f"{BASE_URL}/workspaces", json=new_workspace, headers=headers)
        self.assertEqual(response.status_code, 201)
        workspace_id = response.json()["_id"]
        
        # 2. Get all workspaces for user
        response = requests.get(f"{BASE_URL}/workspaces", headers=headers)
        self.assertEqual(response.status_code, 200)
        workspaces = response.json()
        self.assertGreaterEqual(len(workspaces), 2)  # At least the two we've created
        
        # 3. Update workspace
        update_data = {
            "name": "Updated Workspace Name",
            "description": "This description has been updated"
        }
        response = requests.put(f"{BASE_URL}/workspaces/{workspace_id}", json=update_data, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], update_data["name"])
        
        # 4. Add member to workspace
        response = requests.post(
            f"{BASE_URL}/workspaces/{workspace_id}/members", 
            json={"userId": self.user2_id}, 
            headers=headers
        )
        self.assertEqual(response.status_code, 200)
        
        # 5. Verify member has access
        headers2 = {"Authorization": f"Bearer {self.user2_token}"}
        response = requests.get(f"{BASE_URL}/workspaces/{workspace_id}", headers=headers2)
        self.assertEqual(response.status_code, 200)
        
        # 6. Remove member from workspace
        response = requests.delete(
            f"{BASE_URL}/workspaces/{workspace_id}/members/{self.user2_id}", 
            headers=headers
        )
        self.assertEqual(response.status_code, 200)
        
        # 7. Verify member no longer has access
        response = requests.get(f"{BASE_URL}/workspaces/{workspace_id}", headers=headers2)
        self.assertEqual(response.status_code, 403)
        
        # 8. Delete workspace
        response = requests.delete(f"{BASE_URL}/workspaces/{workspace_id}", headers=headers)
        self.assertEqual(response.status_code, 200)
        
        # 9. Verify workspace is gone
        response = requests.get(f"{BASE_URL}/workspaces/{workspace_id}", headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_project_management(self):
        """Test project creation, update, and management."""
        headers = {"Authorization": f"Bearer {self.user1_token}"}
        
        # 1. Create multiple projects in a workspace
        project2 = {
            "name": "Second Project",
            "description": "Another project in the workspace"
        }
        response = requests.post(
            f"{BASE_URL}/workspaces/{self.workspace_id}/projects", 
            json=project2,
            headers=headers
        )
        self.assertEqual(response.status_code, 201)
        project2_id = response.json()["_id"]
        
        # 2. Get all projects in workspace
        response = requests.get(f"{BASE_URL}/workspaces/{self.workspace_id}/projects", headers=headers)
        self.assertEqual(response.status_code, 200)
        projects = response.json()
        self.assertEqual(len(projects), 2)  # Should have two projects
        
        # 3. Update project
        update_data = {
            "name": "Updated Project",
            "description": "This project has been updated"
        }
        response = requests.put(f"{BASE_URL}/projects/{self.project_id}", json=update_data, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], update_data["name"])
        
        # 4. Add team member to workspace
        response = requests.post(
            f"{BASE_URL}/workspaces/{self.workspace_id}/members", 
            json={"userId": self.user2_id}, 
            headers=headers
        )
        self.assertEqual(response.status_code, 200)
        
        # 5. Set project permissions
        permissions = {
            "userId": self.user2_id,
            "role": "editor"  # Assuming roles like viewer, editor, admin
        }
        response = requests.post(
            f"{BASE_URL}/projects/{self.project_id}/permissions", 
            json=permissions,
            headers=headers
        )
        self.assertEqual(response.status_code, 200)
        
        # 6. Verify user2 can access the project
        headers2 = {"Authorization": f"Bearer {self.user2_token}"}
        response = requests.get(f"{BASE_URL}/projects/{self.project_id}", headers=headers2)
        self.assertEqual(response.status_code, 200)
        
        # 7. Archive project
        response = requests.patch(f"{BASE_URL}/projects/{project2_id}/archive", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["archived"])
        
        # 8. Get only active projects
        response = requests.get(
            f"{BASE_URL}/workspaces/{self.workspace_id}/projects?status=active", 
            headers=headers
        )
        self.assertEqual(response.status_code, 200)
        active_projects = response.json()
        self.assertEqual(len(active_projects), 1)  # Only one active project

    def test_task_management(self):
        """Test task creation, updates, assignment, and status changes."""
        headers = {"Authorization": f"Bearer {self.user1_token}"}
        
        # 1. Create a task
        response = requests.post(
            f"{BASE_URL}/projects/{self.project_id}/tasks", 
            json=self.test_task,
            headers=headers
        )
        self.assertEqual(response.status_code, 201)
        task_data = response.json()
        task_id = task_data["_id"]
        
        # 2. Create multiple tasks
        for i in range(3):
            task = {
                "title": f"Additional Task {i+1}",
                "description": f"Description for task {i+1}",
                "priority": "medium",
                "status": "todo"
            }
            response = requests.post(
                f"{BASE_URL}/projects/{self.project_id}/tasks", 
                json=task,
                headers=headers
            )
            self.assertEqual(response.status_code, 201)
        
        # 3. Get all tasks in project
        response = requests.get(f"{BASE_URL}/projects/{self.project_id}/tasks", headers=headers)
        self.assertEqual(response.status_code, 200)
        tasks = response.json()
        self.assertEqual(len(tasks), 4)  # Should have 4 tasks
        
        # 4. Update task
        update_data = {
            "title": "Updated Task Title",
            "priority": "critical"
        }
        response = requests.put(f"{BASE_URL}/tasks/{task_id}", json=update_data, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], update_data["title"])
        self.assertEqual(response.json()["priority"], update_data["priority"])
        
        # 5. Assign task to user2
        response = requests.patch(
            f"{BASE_URL}/tasks/{task_id}/assign", 
            json={"userId": self.user2_id},
            headers=headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["assignedTo"], self.user2_id)
        
        # 6. Add user2 to workspace (if not already added)
        requests.post(
            f"{BASE_URL}/workspaces/{self.workspace_id}/members", 
            json={"userId": self.user2_id}, 
            headers=headers
        )
        
        # 7. User2 updates task status
        headers2 = {"Authorization": f"Bearer {self.user2_token}"}
        response = requests.patch(
            f"{BASE_URL}/tasks/{task_id}/status", 
            json={"status": "in-progress"},
            headers=headers2
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "in-progress")
        
        # 8. User2 adds a comment to task
        comment = {
            "content": "Working on this task now"
        }
        response = requests.post(
            f"{BASE_URL}/tasks/{task_id}/comments", 
            json=comment,
            headers=headers2
        )
        self.assertEqual(response.status_code, 201)
        
        # 9. Get task with comments
        response = requests.get(f"{BASE_URL}/tasks/{task_id}?include=comments", headers=headers)
        self.assertEqual(response.status_code, 200)
        task_with_comments = response.json()
        self.assertIn("comments", task_with_comments)
        self.assertEqual(len(task_with_comments["comments"]), 1)
        
        # 10. Complete task
        response = requests.patch(
            f"{BASE_URL}/tasks/{task_id}/status", 
            json={"status": "completed"},
            headers=headers2
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")
        
        # 11. Filter tasks by status
        response = requests.get(
            f"{BASE_URL}/projects/{self.project_id}/tasks?status=completed", 
            headers=headers
        )
        self.assertEqual(response.status_code, 200)
        completed_tasks = response.json()
        self.assertEqual(len(completed_tasks), 1)  # Only one completed task

    def test_search_functionality(self):
        """Test search functionality across different entities."""
        headers = {"Authorization": f"Bearer {self.user1_token}"}
        
        # Create some content to search for
        # 1. Create unique tasks with specific keywords
        task_with_keyword = {
            "title": "Important API Documentation",
            "description": "We need to document our REST API endpoints",
            "priority": "high",
            "status": "todo"
        }
        response = requests.post(
            f"{BASE_URL}/projects/{self.project_id}/tasks", 
            json=task_with_keyword,
            headers=headers
        )
        self.assertEqual(response.status_code, 201)
        
        # 2. Create another project with a keyword
        project_with_keyword = {
            "name": "API Development",
            "description": "This project is about developing our REST API"
        }
        response = requests.post(
            f"{BASE_URL}/workspaces/{self.workspace_id}/projects", 
            json=project_with_keyword,
            headers=headers
        )
        self.assertEqual(response.status_code, 201)
        
        # 3. Search for "API" across all content
        response = requests.get(f"{BASE_URL}/search?q=API&workspaceId={self.workspace_id}", headers=headers)
        self.assertEqual(response.status_code, 200)
        results = response.json()
        
        # Should find both the task and project
        self.assertIn("tasks", results)
        self.assertIn("projects", results)
        self.assertGreaterEqual(len(results["tasks"]), 1)
        self.assertGreaterEqual(len(results["projects"]), 1)
        
        # 4. Search only in tasks
        response = requests.get(
            f"{BASE_URL}/search?q=API&workspaceId={self.workspace_id}&type=task", 
            headers=headers
        )
        self.assertEqual(response.status_code, 200)
        results = response.json()
        self.assertGreaterEqual(len(results), 1)
        
        # 5. Search with no results
        response = requests.get(
            f"{BASE_URL}/search?q=NonExistentKeyword&workspaceId={self.workspace_id}", 
            headers=headers
        )
        self.assertEqual(response.status_code, 200)
        results = response.json()
        # Should have empty arrays for all entity types
        self.assertEqual(len(results["tasks"]), 0)
        self.assertEqual(len(results["projects"]), 0)
        
        # 6. Test search with partial matching
        response = requests.get(f"{BASE_URL}/search?q=doc&workspaceId={self.workspace_id}", headers=headers)
        self.assertEqual(response.status_code, 200)
        results = response.json()
        # Should find the task with "documentation"
        self.assertGreaterEqual(len(results["tasks"]), 1)

    def test_edge_cases(self):
        """Test various edge cases and error scenarios."""
        headers = {"Authorization": f"Bearer {self.user1_token}"}
        
        # 1. Test with invalid workspace ID
        response = requests.get(f"{BASE_URL}/workspaces/invalidid", headers=headers)
        self.assertEqual(response.status_code, 400)  # Bad request for invalid ID format
        
        # 2. Test with non-existent but valid format workspace ID
        valid_nonexistent_id = "60a1c2e68f491e001d3e9999"  # Valid MongoDB ObjectId format
        response = requests.get(f"{BASE_URL}/workspaces/{valid_nonexistent_id}", headers=headers)
        self.assertEqual(response.status_code, 404)  # Not found
        
        # 3. Test authentication edge cases
        
        # Expired token (this is a simulation as we can't actually expire the token on demand)
        with mock.patch('jwt.decode', side_effect=Exception("Token expired")):
            headers_expired = {"Authorization": f"Bearer {self.user1_token}"}
            response = requests.get(f"{BASE_URL}/workspaces", headers=headers_expired)
            self.assertEqual(response.status_code, 401)
        
        # Invalid token format
        headers_invalid = {"Authorization": "Bearer invalid.token.format"}
        response = requests.get(f"{BASE_URL}/workspaces", headers=headers_invalid)
        self.assertEqual(response.status_code, 401)
        
        # Missing authorization header
        response = requests.get(f"{BASE_URL}/workspaces")
        self.assertEqual(response.status_code, 401)
        
        # 4. Test with very large payload
        large_description = "a" * 100000  # 100KB description
        large_task = {
            "title": "Large Task",
            "description": large_description,
            "priority": "medium",
            "status": "todo"
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/projects/{self.project_id}/tasks", 
                json=large_task,
                headers=headers
            )
            # Either it succeeds or returns a payload too large error
            self.assertIn(response.status_code, [201, 413])
        except requests.exceptions.RequestException:
            # Request might fail at the HTTP client level for very large payloads
            pass
        
        # 5. Test concurrency (approximate simulation)
        task_data = {
            "title": "Concurrency Test Task",
            "description": "Testing concurrent updates",
            "priority": "high",
            "status": "todo"
        }
        
        # Create a task to test with
        response = requests.post(
            f"{BASE_URL}/projects/{self.project_id}/tasks", 
            json=task_data,
            headers=headers
        )
        self.assertEqual(response.status_code, 201)
        concurrent_task_id = response.json()["_id"]
        
        # Add user2 to workspace if not already
        requests.post(
            f"{BASE_URL}/workspaces/{self.workspace_id}/members", 
            json={"userId": self.user2_id}, 
            headers=headers
        )
        
        # Simulate concurrent updates from two users
        update1 = {"status": "in-progress"}
        update2 = {"priority": "critical"}
        
        headers2 = {"Authorization": f"Bearer {self.user2_token}"}
        
        # Start both requests at nearly the same time
        import threading
        
        results = {"user1": None, "user2": None}
        
        def update_as_user1():
            results["user1"] = requests.patch(
                f"{BASE_URL}/tasks/{concurrent_task_id}", 
                json=update1,
                headers=headers
            )
        
        def update_as_user2():
            results["user2"] = requests.patch(
                f"{BASE_URL}/tasks/{concurrent_task_id}", 
                json=update2,
                headers=headers2
            )
        
        t1 = threading.Thread(target=update_as_user1)
        t2 = threading.Thread(target=update_as_user2)
        
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        
        # Both should succeed
        self.assertEqual(results["user1"].status_code, 200)
        self.assertEqual(results["user2"].status_code, 200)
        
        # Final state should have both updates
        response = requests.get(f"{BASE_URL}/tasks/{concurrent_task_id}", headers=headers)
        self.assertEqual(response.status_code, 200)
        final_task = response.json()
        self.assertEqual(final_task["status"], "in-progress")
        self.assertEqual(final_task["priority"], "critical")

    def test_cross_component_integration(self):
        """Test integration between multiple components in complex workflows."""
        headers = {"Authorization": f"Bearer {self.user1_token}"}
        headers2 = {"Authorization": f"Bearer {self.user2_token}"}
        
        # 1. Full workflow: Workspace -> Project -> Tasks -> Assignment -> Completion
        
        # Add user2 to workspace
        requests.post(
            f"{BASE_URL}/workspaces/{self.workspace_id}/members", 
            json={"userId": self.user2_id}, 
            headers=headers
        )
        
        # Create a task
        complex_task = {
            "title": "Complex Integration Task",
            "description": "This task tests full integration flow",
            "priority": "high",
            "status": "todo",
            "dueDate": (datetime.now() + timedelta(days=2)).isoformat()
        }
        
        response = requests.post(
            f"{BASE_URL}/projects/{self.project_id}/tasks", 
            json=complex_task,
            headers=headers
        )
        self.assertEqual(response.status_code, 201)
        task_id = response.json()["_id"]
        
        # Assign to user2
        response = requests.patch(
            f"{BASE_URL}/tasks/{task_id}/assign", 
            json={"userId": self.user2_id},
            headers=headers
        )
        self.assertEqual(response.status_code, 200)
        
        # User2 updates status to in-progress
        response = requests.patch(
            f"{BASE_URL}/tasks/{task_id}/status", 
            json={"status": "in-progress"},
            headers=headers2
        )
        self.assertEqual(response.status_code, 200)
        
        # User2 adds a comment
        response = requests.post(
            f"{BASE_URL}/tasks/{task_id}/comments", 
            json={"content": "Working on this now"},
            headers=headers2
        )
        self.assertEqual(response.status_code, 201)
        
        # User2 completes task
        response = requests.patch(
            f"{BASE_URL}/tasks/{task_id}/status", 
            json={"status": "completed"},
            headers=headers2
        )
        self.assertEqual(response.status_code, 200)
        
        # User1 verifies task completion
        response = requests.get(f"{BASE_URL}/tasks/{task_id}", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")
        
        # 2. Test search after content creation
        time.sleep(1)  # Give search indexing time to update
        
        # Search for the task by title
        response = requests.get(
            f"{BASE_URL}/search?q=Complex%20Integration&workspaceId={self.workspace_id}", 
            headers=headers
        )
        self.assertEqual(response.status_code, 200)
        results = response.json()
        self.assertGreaterEqual(len(results["tasks"]), 1)
        
        # 3. Test cascading deletions
        
        # Create a project that will be deleted with the workspace
        project_to_delete = {
            "name": "Project To Delete",
            "description": "This project will be deleted with its workspace"
        }
        
        # Create a new workspace for deletion test
        temp_workspace = {
            "name": "Temp Workspace",
            "description": "This workspace will be deleted"
        }
        response = requests.post(f"{BASE_URL}/workspaces", json=temp_workspace, headers=headers)
        self.assertEqual(response.status_code, 201)
        temp_workspace_id = response.json()["_id"]
        
        # Create project in temp workspace
        response = requests.post(
            f"{BASE_URL}/workspaces/{temp_workspace_id}/projects", 
            json=project_to_delete,
            headers=headers
        )
        self.assertEqual(response.status_code, 201)
        temp_project_id = response.json()["_id"]
        
        # Create task in temp project
        task_to_delete = {
            "title": "Task To Delete",
            "description": "This task will be deleted with cascading delete",
            "priority": "medium",
            "status": "todo"
        }
        response = requests.post(
            f"{BASE_URL}/projects/{temp_project_id}/tasks", 
            json=task_to_delete,
            headers=headers
        )
        self.assertEqual(response.status_code, 201)
        temp_task_id = response.json()["_id"]
        
        # Check that all resources exist
        response = requests.get(f"{BASE_URL}/workspaces/{temp_workspace_id}", headers=headers)
        self.assertEqual(response.status_code, 200)
        
        response = requests.get(f"{BASE_URL}/projects/{temp_project_id}", headers=headers)
        self.assertEqual(response.status_code, 200)
        
        response = requests.get(f"{BASE_URL}/tasks/{temp_task_id}", headers=headers)
        self.assertEqual(response.status_code, 200)
        
        # Delete the workspace
        response = requests.delete(f"{BASE_URL}/workspaces/{temp_workspace_id}", headers=headers)
        self.assertEqual(response.status_code, 200)
        
        # Verify cascading deletion - all resources should be gone
        response = requests.get(f"{BASE_URL}/workspaces/{temp_workspace_id}", headers=headers)
        self.assertEqual(response.status_code, 404)
        
        response = requests.get(f"{BASE_URL}/projects/{temp_project_id}", headers=headers)
        self.assertEqual(response.status_code, 404)
        
        response = requests.get(f"{BASE_URL}/tasks/{temp_task_id}", headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_real_time_notifications(self):
        """Test real-time notification system if implemented."""
        headers = {"Authorization": f"Bearer {self.user1_token}"}
        headers2 = {"Authorization": f"Bearer {self.user2_token}"}
        
        # Add user2 to workspace
        requests.post(
            f"{BASE_URL}/workspaces/{self.workspace_id}/members", 
            json={"userId": self.user2_id}, 
            headers=headers
        )
        
        # Create a task assigned to user2
        task_data = {
            "title": "Notification Test Task",
            "description": "This task should trigger a notification",
            "priority": "high",
            "status": "todo",
            "assignedTo": self.user2_id
        }
        
        response = requests.post(
            f"{BASE_URL}/projects/{self.project_id}/tasks", 
            json=task_data,
            headers=headers
        )
        self.assertEqual(response.status_code, 201)
        task_id = response.json()["_id"]
        
        # Check for notifications for user2
        response = requests.get(f"{BASE_URL}/users/notifications", headers=headers2)
        self.assertEqual(response.status_code, 200)
        notifications = response.json()
        
        # There should be at least one notification about the task assignment
        self.assertGreaterEqual(len(notifications), 1)
        
        # Mark notification as read
        if len(notifications) > 0:
            notification_id = notifications[0]["_id"]
            response = requests.patch(
                f"{BASE_URL}/users/notifications/{notification_id}/read", 
                headers=headers2
            )
            self.assertEqual(response.status_code, 200)
            
            # Verify notification is marked as read
            response = requests.get(f"{BASE_URL}/users/notifications?status=read", headers=headers2)
            self.assertEqual(response.status_code, 200)
            read_notifications = response.json()
            self.assertGreaterEqual(len(read_notifications), 1)

    def test_file_attachments(self):
        """Test file attachment functionality if implemented."""
        headers = {"Authorization": f"Bearer {self.user1_token}"}
        
        # Create a task
        response = requests.post(
            f"{BASE_URL}/projects/{self.project_id}/tasks", 
            json=self.test_task,
            headers=headers
        )
        self.assertEqual(response.status_code, 201)
        task_id = response.json()["_id"]
        
        # Create a small test file
        import io
        test_file = io.BytesIO(b"This is test file content")
        test_file.name = "test_file.txt"
        
        # Upload file attachment to task
        files = {
            "file": (test_file.name, test_file, "text/plain")
        }
        
        response = requests.post(
            f"{BASE_URL}/tasks/{task_id}/attachments", 
            headers=headers,
            files=files
        )
        self.assertEqual(response.status_code, 201)
        attachment_id = response.json()["_id"]
        
        # Get task with attachments
        response = requests.get(f"{BASE_URL}/tasks/{task_id}?include=attachments", headers=headers)
        self.assertEqual(response.status_code, 200)
        task_with_attachments = response.json()
        self.assertIn("attachments", task_with_attachments)
        self.assertEqual(len(task_with_attachments["attachments"]), 1)
        
        # Download attachment
        response = requests.get(f"{BASE_URL}/attachments/{attachment_id}", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"This is test file content")
        
        # Delete attachment
        response = requests.delete(f"{BASE_URL}/attachments/{attachment_id}", headers=headers)
        self.assertEqual(response.status_code, 200)
        
        # Verify attachment is gone
        response = requests.get(f"{BASE_URL}/tasks/{task_id}?include=attachments", headers=headers)
        self.assertEqual(response.status_code, 200)
        task_after_delete = response.json()
        self.assertIn("attachments", task_after_delete)
        self.assertEqual(len(task_after_delete["attachments"]), 0)

if __name__ == "__main__":
    unittest.main()