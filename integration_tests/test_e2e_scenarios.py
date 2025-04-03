"""
End-to-end scenario tests for CollabHub.

This file contains tests that simulate real-world usage scenarios involving multiple components.
"""

import pytest
import time
from datetime import datetime, timedelta

class TestEndToEndScenarios:
    """Test class for end-to-end scenarios in CollabHub."""
    
    def test_team_collaboration_scenario(self, api_client):
        """
        Test a complete team collaboration scenario:
        1. User creates a workspace
        2. User invites team members
        3. Team creates projects and tasks
        4. Members collaborate on tasks
        5. Project completion and reporting
        """
        # Register team members
        admin = {
            "email": "admin@example.com",
            "password": "Admin123!",
            "firstName": "Admin",
            "lastName": "User",
            "username": "adminuser"
        }
        
        developer1 = {
            "email": "dev1@example.com",
            "password": "Dev123!",
            "firstName": "Developer",
            "lastName": "One",
            "username": "dev1"
        }
        
        developer2 = {
            "email": "dev2@example.com",
            "password": "Dev123!",
            "firstName": "Developer",
            "lastName": "Two",
            "username": "dev2"
        }
        
        designer = {
            "email": "designer@example.com",
            "password": "Design123!",
            "firstName": "UI",
            "lastName": "Designer",
            "username": "designer"
        }
        
        # Register admin and login
        api_client.register(admin)
        admin_client = api_client
        
        # Create additional API clients for other team members
        dev1_client = type(api_client)()
        dev1_client.register(developer1)
        
        dev2_client = type(api_client)()
        dev2_client.register(developer2)
        
        designer_client = type(api_client)()
        designer_client.register(designer)
        
        # 1. Admin creates a workspace
        workspace_data = {
            "name": "E2E Test Project",
            "description": "A workspace for our e2e testing scenario"
        }
        
        response = admin_client.post("workspaces", workspace_data)
        assert response.status_code == 201
        workspace = response.json()
        workspace_id = workspace["_id"]
        
        # 2. Admin invites team members to the workspace
        for user_id in [
            dev1_client.post("users/me", include_auth=True).json()["_id"],
            dev2_client.post("users/me", include_auth=True).json()["_id"],
            designer_client.post("users/me", include_auth=True).json()["_id"]
        ]:
            response = admin_client.post(f"workspaces/{workspace_id}/members", {
                "userId": user_id
            })
            assert response.status_code == 200
        
        # 3. Admin creates a project in the workspace
        project_data = {
            "name": "Website Redesign",
            "description": "Complete redesign of company website",
            "startDate": datetime.now().isoformat(),
            "endDate": (datetime.now() + timedelta(days=30)).isoformat()
        }
        
        response = admin_client.post(f"workspaces/{workspace_id}/projects", project_data)
        assert response.status_code == 201
        project = response.json()
        project_id = project["_id"]
        
        # 4. Admin creates tasks and assigns them
        tasks = [
            # Design tasks
            {
                "title": "Create wireframes",
                "description": "Create wireframes for all main pages",
                "priority": "high",
                "status": "todo",
                "dueDate": (datetime.now() + timedelta(days=7)).isoformat(),
                "assignedTo": designer_client.post("users/me", include_auth=True).json()["_id"]
            },
            # Developer tasks
            {
                "title": "Setup project repository",
                "description": "Initialize git repo and project structure",
                "priority": "high",
                "status": "todo",
                "dueDate": (datetime.now() + timedelta(days=3)).isoformat(),
                "assignedTo": dev1_client.post("users/me", include_auth=True).json()["_id"]
            },
            {
                "title": "Implement homepage",
                "description": "Code the homepage based on wireframes",
                "priority": "medium",
                "status": "todo",
                "dueDate": (datetime.now() + timedelta(days=14)).isoformat(),
                "assignedTo": dev2_client.post("users/me", include_auth=True).json()["_id"]
            }
        ]
        
        task_ids = {}
        for task in tasks:
            response = admin_client.post(f"projects/{project_id}/tasks", task)
            assert response.status_code == 201
            task_ids[task["title"]] = response.json()["_id"]
        
        # 5. Designer starts and completes their task
        designer_task_id = task_ids["Create wireframes"]
        
        # Start working on task
        response = designer_client.patch(f"tasks/{designer_task_id}/status", {
            "status": "in-progress"
        })
        assert response.status_code == 200
        
        # Add a comment
        response = designer_client.post(f"tasks/{designer_task_id}/comments", {
            "content": "Started working on wireframes. Will upload drafts soon."
        })
        assert response.status_code == 201
        
        # Upload an attachment (simulated)
        import io
        mock_wireframe = io.BytesIO(b"This is a wireframe file simulation")
        mock_wireframe.name = "homepage_wireframe.png"
        
        files = {
            "file": (mock_wireframe.name, mock_wireframe, "image/png")
        }
        
        response = designer_client.post(f"tasks/{designer_task_id}/attachments", 
            data=None, files=files)
        assert response.status_code == 201
        
        # Complete the task
        response = designer_client.patch(f"tasks/{designer_task_id}/status", {
            "status": "completed"
        })
        assert response.status_code == 200
        
        # 6. Developers work on their tasks
        # Dev1 starts setup task
        dev1_task_id = task_ids["Setup project repository"]
        
        response = dev1_client.patch(f"tasks/{dev1_task_id}/status", {
            "status": "in-progress"
        })
        assert response.status_code == 200
        
        # Dev1 adds a comment
        response = dev1_client.post(f"tasks/{dev1_task_id}/comments", {
            "content": "Repository created at github.com/example/website-redesign"
        })
        assert response.status_code == 201
        
        # Dev1 completes setup
        response = dev1_client.patch(f"tasks/{dev1_task_id}/status", {
            "status": "completed"
        })
        assert response.status_code == 200
        
        # 7. Dev2 waits for wireframes before starting homepage
        dev2_task_id = task_ids["Implement homepage"]
        
        # Dev2 adds a comment asking about wireframes
        response = dev2_client.post(f"tasks/{dev2_task_id}/comments", {
            "content": "Waiting for wireframes before I can start implementation."
        })
        assert response.status_code == 201
        
        # Dev2 checks wireframe attachments on designer's task
        response = dev2_client.get(f"tasks/{designer_task_id}?include=attachments")
        assert response.status_code == 200
        task_with_attachments = response.json()
        assert "attachments" in task_with_attachments
        assert len(task_with_attachments["attachments"]) > 0
        
        # Dev2 starts working on homepage after seeing wireframes
        response = dev2_client.patch(f"tasks/{dev2_task_id}/status", {
            "status": "in-progress"
        })
        assert response.status_code == 200
        
        # 8. Admin monitors progress
        # Get project status
        response = admin_client.get(f"projects/{project_id}/tasks/stats")
        assert response.status_code == 200
        stats = response.json()
        
        # Should have 2 completed tasks, 1 in progress
        assert stats["completed"] == 2
        assert stats["in-progress"] == 1
        assert stats["todo"] == 0
        
        # 9. Project completion
        # Dev2 completes homepage implementation
        response = dev2_client.patch(f"tasks/{dev2_task_id}/status", {
            "status": "completed"
        })
        assert response.status_code == 200
        
        # Admin marks project as completed
        response = admin_client.patch(f"projects/{project_id}", {
            "status": "completed",
            "completionDate": datetime.now().isoformat()
        })
        assert response.status_code == 200
        
        # 10. Admin generates a report (if supported)
        response = admin_client.get(f"projects/{project_id}/report")
        # Either returns a report or a 404 if not implemented
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            report = response.json()
            assert report["totalTasks"] == 3
            assert report["completedTasks"] == 3
            
    def test_workspace_permission_scenario(self, api_client):
        """
        Test workspace permission scenarios:
        1. Owner creates workspace
        2. Members added with different permission levels
        3. Test what each permission level can and cannot do
        """
        # Register users with different roles
        owner = {
            "email": "owner@example.com",
            "password": "Owner123!",
            "firstName": "Workspace",
            "lastName": "Owner",
            "username": "wsowner"
        }
        
        admin = {
            "email": "wsadmin@example.com",
            "password": "Admin123!",
            "firstName": "Workspace",
            "lastName": "Admin",
            "username": "wsadmin"
        }
        
        member = {
            "email": "member@example.com",
            "password": "Member123!",
            "firstName": "Regular",
            "lastName": "Member",
            "username": "regmember"
        }
        
        viewer = {
            "email": "viewer@example.com",
            "password": "Viewer123!",
            "firstName": "View",
            "lastName": "Only",
            "username": "viewonly"
        }
        
        # Register and create API clients
        owner_client = api_client
        owner_client.register(owner)
        
        admin_client = type(api_client)()
        admin_client.register(admin)
        admin_id = admin_client.get("users/me").json()["_id"]
        
        member_client = type(api_client)()
        member_client.register(member)
        member_id = member_client.get("users/me").json()["_id"]
        
        viewer_client = type(api_client)()
        viewer_client.register(viewer)
        viewer_id = viewer_client.get("users/me").json()["_id"]
        
        # 1. Owner creates workspace
        workspace_data = {
            "name": "Permission Test Workspace",
            "description": "Testing different permission levels"
        }
        
        response = owner_client.post("workspaces", workspace_data)
        assert response.status_code == 201
        workspace = response.json()
        workspace_id = workspace["_id"]
        
        # 2. Owner adds members with different permissions
        # Add admin
        response = owner_client.post(f"workspaces/{workspace_id}/members", {
            "userId": admin_id,
            "role": "admin"
        })
        assert response.status_code == 200
        
        # Add regular member
        response = owner_client.post(f"workspaces/{workspace_id}/members", {
            "userId": member_id,
            "role": "member"
        })
        assert response.status_code == 200
        
        # Add viewer
        response = owner_client.post(f"workspaces/{workspace_id}/members", {
            "userId": viewer_id,
            "role": "viewer"
        })
        assert response.status_code == 200
        
        # 3. Test creating projects with different permission levels
        
        # Admin should be able to create a project
        admin_project = {
            "name": "Admin Project",
            "description": "Project created by admin"
        }
        response = admin_client.post(f"workspaces/{workspace_id}/projects", admin_project)
        assert response.status_code == 201
        admin_project_id = response.json()["_id"]
        
        # Regular member should be able to create a project
        member_project = {
            "name": "Member Project",
            "description": "Project created by regular member"
        }
        response = member_client.post(f"workspaces/{workspace_id}/projects", member_project)
        assert response.status_code == 201
        member_project_id = response.json()["_id"]
        
        # Viewer should NOT be able to create a project
        viewer_project = {
            "name": "Viewer Project",
            "description": "Project attempt by viewer"
        }
        response = viewer_client.post(f"workspaces/{workspace_id}/projects", viewer_project)
        assert response.status_code in [403, 401]  # Should be forbidden
        
        # 4. Test workspace modifications
        
        # Admin should be able to update workspace
        response = admin_client.put(f"workspaces/{workspace_id}", {
            "description": "Updated by admin"
        })
        assert response.status_code == 200
        
        # Regular member should NOT be able to update workspace
        response = member_client.put(f"workspaces/{workspace_id}", {
            "description": "Updated by member"
        })
        assert response.status_code in [403, 401]  # Should be forbidden
        
        # 5. Test adding new members (only owner/admin should be able to)
        new_user = {
            "email": "newuser@example.com",
            "password": "NewUser123!",
            "firstName": "New",
            "lastName": "User",
            "username": "newuser"
        }
        
        new_user_client = type(api_client)()
        new_user_client.register(new_user)
        new_user_id = new_user_client.get("users/me").json()["_id"]
        
        # Admin can add members
        response = admin_client.post(f"workspaces/{workspace_id}/members", {
            "userId": new_user_id,
            "role": "viewer"
        })
        assert response.status_code == 200
        
        # Try to remove the user (only owner/admin should be able to)
        response = member_client.delete(f"workspaces/{workspace_id}/members/{new_user_id}")
        assert response.status_code in [403, 401]  # Should be forbidden
        
        # Admin can remove members
        response = admin_client.delete(f"workspaces/{workspace_id}/members/{new_user_id}")
        assert response.status_code == 200
        
        # 6. Test deleting projects
        
        # Member can delete their own project
        response = member_client.delete(f"projects/{member_project_id}")
        assert response.status_code == 200
        
        # But member cannot delete admin's project
        response = member_client.delete(f"projects/{admin_project_id}")
        assert response.status_code in [403, 401]  # Should be forbidden
        
        # Admin can delete any project
        response = admin_client.delete(f"projects/{admin_project_id}")
        assert response.status_code == 200
        
        # 7. Only owner can delete workspace
        response = admin_client.delete(f"workspaces/{workspace_id}")
        assert response.status_code in [403, 401]  # Should be forbidden
        
        response = owner_client.delete(f"workspaces/{workspace_id}")
        assert response.status_code == 200

if __name__ == "__main__":
    pytest.main()