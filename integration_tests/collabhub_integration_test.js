/**
 * CollabHub Integration Tests
 * 
 * This file contains comprehensive integration tests for the CollabHub application,
 * testing the interactions between the main components: users, workspace, search, and core functionality.
 */

const request = require('supertest');
const mongoose = require('mongoose');
const { MongoMemoryServer } = require('mongodb-memory-server');
const app = require('../app');
const User = require('../users/models/User');
const Workspace = require('../workspace/models/Workspace');
const Project = require('../workspace/models/Project');
const Task = require('../workspace/models/Task');

let mongoServer;

// Test data
const testUser1 = {
  email: 'test1@example.com',
  password: 'Password123!',
  firstName: 'Test',
  lastName: 'User',
  username: 'testuser1'
};

const testUser2 = {
  email: 'test2@example.com',
  password: 'Password123!',
  firstName: 'Another',
  lastName: 'User',
  username: 'testuser2'
};

const testWorkspace = {
  name: 'Test Workspace',
  description: 'A workspace for testing purposes'
};

const testProject = {
  name: 'Test Project',
  description: 'A project for testing purposes'
};

const testTask = {
  title: 'Test Task',
  description: 'A task for testing purposes',
  priority: 'high',
  status: 'todo',
  dueDate: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000) // 7 days from now
};

// Setup and Teardown
beforeAll(async () => {
  mongoServer = await MongoMemoryServer.create();
  const uri = mongoServer.getUri();
  await mongoose.connect(uri, {
    useNewUrlParser: true,
    useUnifiedTopology: true,
  });
});

afterAll(async () => {
  await mongoose.disconnect();
  await mongoServer.stop();
});

beforeEach(async () => {
  // Clear all collections before each test
  await User.deleteMany({});
  await Workspace.deleteMany({});
  await Project.deleteMany({});
  await Task.deleteMany({});
});

describe('User Registration and Authentication', () => {
  test('Should register a new user', async () => {
    const response = await request(app)
      .post('/api/users/register')
      .send(testUser1);
    
    expect(response.status).toBe(201);
    expect(response.body).toHaveProperty('token');
    expect(response.body.user).toHaveProperty('email', testUser1.email);
  });

  test('Should not register a user with existing email', async () => {
    // First registration
    await request(app)
      .post('/api/users/register')
      .send(testUser1);
    
    // Attempt to register with same email
    const response = await request(app)
      .post('/api/users/register')
      .send({ ...testUser2, email: testUser1.email });
    
    expect(response.status).toBe(400);
    expect(response.body).toHaveProperty('errors');
  });

  test('Should not register a user with invalid email format', async () => {
    const response = await request(app)
      .post('/api/users/register')
      .send({ ...testUser1, email: 'invalidemail' });
    
    expect(response.status).toBe(400);
    expect(response.body).toHaveProperty('errors');
  });

  test('Should login an existing user', async () => {
    // Register user first
    await request(app)
      .post('/api/users/register')
      .send(testUser1);
    
    // Attempt login
    const response = await request(app)
      .post('/api/users/login')
      .send({
        email: testUser1.email,
        password: testUser1.password
      });
    
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty('token');
  });

  test('Should not login with incorrect password', async () => {
    // Register user first
    await request(app)
      .post('/api/users/register')
      .send(testUser1);
    
    // Attempt login with wrong password
    const response = await request(app)
      .post('/api/users/login')
      .send({
        email: testUser1.email,
        password: 'wrongpassword'
      });
    
    expect(response.status).toBe(401);
    expect(response.body).toHaveProperty('message', 'Invalid credentials');
  });

  test('Should get user profile with valid token', async () => {
    // Register user first
    const registerRes = await request(app)
      .post('/api/users/register')
      .send(testUser1);
    
    const token = registerRes.body.token;
    
    // Get profile
    const response = await request(app)
      .get('/api/users/me')
      .set('Authorization', `Bearer ${token}`);
    
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty('email', testUser1.email);
  });
});

describe('Workspace Management', () => {
  let token, userId;

  beforeEach(async () => {
    // Register user and get token
    const registerRes = await request(app)
      .post('/api/users/register')
      .send(testUser1);
    
    token = registerRes.body.token;
    userId = registerRes.body.user._id;
  });

  test('Should create a new workspace', async () => {
    const response = await request(app)
      .post('/api/workspaces')
      .set('Authorization', `Bearer ${token}`)
      .send(testWorkspace);
    
    expect(response.status).toBe(201);
    expect(response.body).toHaveProperty('name', testWorkspace.name);
    expect(response.body).toHaveProperty('owner', userId);
  });

  test('Should not create workspace without authentication', async () => {
    const response = await request(app)
      .post('/api/workspaces')
      .send(testWorkspace);
    
    expect(response.status).toBe(401);
  });

  test('Should get all workspaces for a user', async () => {
    // Create a workspace first
    await request(app)
      .post('/api/workspaces')
      .set('Authorization', `Bearer ${token}`)
      .send(testWorkspace);
    
    // Get all workspaces
    const response = await request(app)
      .get('/api/workspaces')
      .set('Authorization', `Bearer ${token}`);
    
    expect(response.status).toBe(200);
    expect(Array.isArray(response.body)).toBe(true);
    expect(response.body.length).toBe(1);
    expect(response.body[0]).toHaveProperty('name', testWorkspace.name);
  });

  test('Should update a workspace', async () => {
    // Create a workspace first
    const createRes = await request(app)
      .post('/api/workspaces')
      .set('Authorization', `Bearer ${token}`)
      .send(testWorkspace);
    
    const workspaceId = createRes.body._id;
    const updatedData = {
      name: 'Updated Workspace Name',
      description: 'Updated description'
    };
    
    // Update workspace
    const response = await request(app)
      .put(`/api/workspaces/${workspaceId}`)
      .set('Authorization', `Bearer ${token}`)
      .send(updatedData);
    
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty('name', updatedData.name);
    expect(response.body).toHaveProperty('description', updatedData.description);
  });

  test('Should not update workspace without permission', async () => {
    // Create first user's workspace
    const createRes = await request(app)
      .post('/api/workspaces')
      .set('Authorization', `Bearer ${token}`)
      .send(testWorkspace);
    
    const workspaceId = createRes.body._id;
    
    // Register second user
    const registerRes2 = await request(app)
      .post('/api/users/register')
      .send(testUser2);
    
    const token2 = registerRes2.body.token;
    
    // Try to update with second user
    const response = await request(app)
      .put(`/api/workspaces/${workspaceId}`)
      .set('Authorization', `Bearer ${token2}`)
      .send({ name: 'Should not update' });
    
    expect(response.status).toBe(403);
  });

  test('Should add a member to workspace', async () => {
    // Create workspace
    const createRes = await request(app)
      .post('/api/workspaces')
      .set('Authorization', `Bearer ${token}`)
      .send(testWorkspace);
    
    const workspaceId = createRes.body._id;
    
    // Register second user
    const registerRes2 = await request(app)
      .post('/api/users/register')
      .send(testUser2);
    
    const user2Id = registerRes2.body.user._id;
    
    // Add second user to workspace
    const response = await request(app)
      .post(`/api/workspaces/${workspaceId}/members`)
      .set('Authorization', `Bearer ${token}`)
      .send({ userId: user2Id });
    
    expect(response.status).toBe(200);
    expect(response.body.members).toContain(user2Id);
  });
});

describe('Project Management', () => {
  let token, workspaceId;

  beforeEach(async () => {
    // Register user and get token
    const registerRes = await request(app)
      .post('/api/users/register')
      .send(testUser1);
    
    token = registerRes.body.token;
    
    // Create workspace
    const workspaceRes = await request(app)
      .post('/api/workspaces')
      .set('Authorization', `Bearer ${token}`)
      .send(testWorkspace);
    
    workspaceId = workspaceRes.body._id;
  });

  test('Should create a new project in workspace', async () => {
    const response = await request(app)
      .post(`/api/workspaces/${workspaceId}/projects`)
      .set('Authorization', `Bearer ${token}`)
      .send(testProject);
    
    expect(response.status).toBe(201);
    expect(response.body).toHaveProperty('name', testProject.name);
    expect(response.body).toHaveProperty('workspace', workspaceId);
  });

  test('Should get all projects in a workspace', async () => {
    // Create a project first
    await request(app)
      .post(`/api/workspaces/${workspaceId}/projects`)
      .set('Authorization', `Bearer ${token}`)
      .send(testProject);
    
    // Get all projects
    const response = await request(app)
      .get(`/api/workspaces/${workspaceId}/projects`)
      .set('Authorization', `Bearer ${token}`);
    
    expect(response.status).toBe(200);
    expect(Array.isArray(response.body)).toBe(true);
    expect(response.body.length).toBe(1);
    expect(response.body[0]).toHaveProperty('name', testProject.name);
  });

  test('Should update a project', async () => {
    // Create a project first
    const createRes = await request(app)
      .post(`/api/workspaces/${workspaceId}/projects`)
      .set('Authorization', `Bearer ${token}`)
      .send(testProject);
    
    const projectId = createRes.body._id;
    const updatedData = {
      name: 'Updated Project Name',
      description: 'Updated project description'
    };
    
    // Update project
    const response = await request(app)
      .put(`/api/projects/${projectId}`)
      .set('Authorization', `Bearer ${token}`)
      .send(updatedData);
    
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty('name', updatedData.name);
    expect(response.body).toHaveProperty('description', updatedData.description);
  });

  test('Should archive a project', async () => {
    // Create a project first
    const createRes = await request(app)
      .post(`/api/workspaces/${workspaceId}/projects`)
      .set('Authorization', `Bearer ${token}`)
      .send(testProject);
    
    const projectId = createRes.body._id;
    
    // Archive project
    const response = await request(app)
      .patch(`/api/projects/${projectId}/archive`)
      .set('Authorization', `Bearer ${token}`);
    
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty('archived', true);
  });
});

describe('Task Management', () => {
  let token, projectId;

  beforeEach(async () => {
    // Register user and get token
    const registerRes = await request(app)
      .post('/api/users/register')
      .send(testUser1);
    
    token = registerRes.body.token;
    
    // Create workspace
    const workspaceRes = await request(app)
      .post('/api/workspaces')
      .set('Authorization', `Bearer ${token}`)
      .send(testWorkspace);
    
    const workspaceId = workspaceRes.body._id;
    
    // Create project
    const projectRes = await request(app)
      .post(`/api/workspaces/${workspaceId}/projects`)
      .set('Authorization', `Bearer ${token}`)
      .send(testProject);
    
    projectId = projectRes.body._id;
  });

  test('Should create a new task in project', async () => {
    const response = await request(app)
      .post(`/api/projects/${projectId}/tasks`)
      .set('Authorization', `Bearer ${token}`)
      .send(testTask);
    
    expect(response.status).toBe(201);
    expect(response.body).toHaveProperty('title', testTask.title);
    expect(response.body).toHaveProperty('project', projectId);
  });

  test('Should get all tasks in a project', async () => {
    // Create a task first
    await request(app)
      .post(`/api/projects/${projectId}/tasks`)
      .set('Authorization', `Bearer ${token}`)
      .send(testTask);
    
    // Get all tasks
    const response = await request(app)
      .get(`/api/projects/${projectId}/tasks`)
      .set('Authorization', `Bearer ${token}`);
    
    expect(response.status).toBe(200);
    expect(Array.isArray(response.body)).toBe(true);
    expect(response.body.length).toBe(1);
    expect(response.body[0]).toHaveProperty('title', testTask.title);
  });

  test('Should update a task', async () => {
    // Create a task first
    const createRes = await request(app)
      .post(`/api/projects/${projectId}/tasks`)
      .set('Authorization', `Bearer ${token}`)
      .send(testTask);
    
    const taskId = createRes.body._id;
    const updatedData = {
      title: 'Updated Task Title',
      status: 'in-progress'
    };
    
    // Update task
    const response = await request(app)
      .put(`/api/tasks/${taskId}`)
      .set('Authorization', `Bearer ${token}`)
      .send(updatedData);
    
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty('title', updatedData.title);
    expect(response.body).toHaveProperty('status', updatedData.status);
  });

  test('Should assign a task to a user', async () => {
    // Register second user
    const registerRes2 = await request(app)
      .post('/api/users/register')
      .send(testUser2);
    
    const user2Id = registerRes2.body.user._id;
    
    // Create a task first
    const createRes = await request(app)
      .post(`/api/projects/${projectId}/tasks`)
      .set('Authorization', `Bearer ${token}`)
      .send(testTask);
    
    const taskId = createRes.body._id;
    
    // Assign task
    const response = await request(app)
      .patch(`/api/tasks/${taskId}/assign`)
      .set('Authorization', `Bearer ${token}`)
      .send({ userId: user2Id });
    
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty('assignedTo', user2Id);
  });

  test('Should change task status', async () => {
    // Create a task first
    const createRes = await request(app)
      .post(`/api/projects/${projectId}/tasks`)
      .set('Authorization', `Bearer ${token}`)
      .send(testTask);
    
    const taskId = createRes.body._id;
    
    // Change status
    const response = await request(app)
      .patch(`/api/tasks/${taskId}/status`)
      .set('Authorization', `Bearer ${token}`)
      .send({ status: 'completed' });
    
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty('status', 'completed');
  });
});

describe('Search Functionality', () => {
  let token, workspaceId, projectId;

  beforeEach(async () => {
    // Register user and get token
    const registerRes = await request(app)
      .post('/api/users/register')
      .send(testUser1);
    
    token = registerRes.body.token;
    
    // Create workspace
    const workspaceRes = await request(app)
      .post('/api/workspaces')
      .set('Authorization', `Bearer ${token}`)
      .send(testWorkspace);
    
    workspaceId = workspaceRes.body._id;
    
    // Create project
    const projectRes = await request(app)
      .post(`/api/workspaces/${workspaceId}/projects`)
      .set('Authorization', `Bearer ${token}`)
      .send(testProject);
    
    projectId = projectRes.body._id;
    
    // Create multiple tasks
    await request(app)
      .post(`/api/projects/${projectId}/tasks`)
      .set('Authorization', `Bearer ${token}`)
      .send({ ...testTask, title: 'Important task about API' });
    
    await request(app)
      .post(`/api/projects/${projectId}/tasks`)
      .set('Authorization', `Bearer ${token}`)
      .send({ ...testTask, title: 'UI design task' });
  });

  test('Should search for tasks within a workspace', async () => {
    const response = await request(app)
      .get(`/api/search?q=API&workspaceId=${workspaceId}&type=task`)
      .set('Authorization', `Bearer ${token}`);
    
    expect(response.status).toBe(200);
    expect(Array.isArray(response.body)).toBe(true);
    expect(response.body.length).toBe(1);
    expect(response.body[0].title).toContain('API');
  });

  test('Should search for projects within a workspace', async () => {
    const response = await request(app)
      .get(`/api/search?q=Test&workspaceId=${workspaceId}&type=project`)
      .set('Authorization', `Bearer ${token}`);
    
    expect(response.status).toBe(200);
    expect(Array.isArray(response.body)).toBe(true);
    expect(response.body.length).toBe(1);
    expect(response.body[0].name).toContain('Test');
  });

  test('Should search across all content types if not specified', async () => {
    const response = await request(app)
      .get(`/api/search?q=test&workspaceId=${workspaceId}`)
      .set('Authorization', `Bearer ${token}`);
    
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty('projects');
    expect(response.body).toHaveProperty('tasks');
    expect(Array.isArray(response.body.projects)).toBe(true);
    expect(Array.isArray(response.body.tasks)).toBe(true);
  });

  test('Should handle no results gracefully', async () => {
    const response = await request(app)
      .get(`/api/search?q=nonexistent&workspaceId=${workspaceId}`)
      .set('Authorization', `Bearer ${token}`);
    
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty('projects');
    expect(response.body).toHaveProperty('tasks');
    expect(response.body.projects.length).toBe(0);
    expect(response.body.tasks.length).toBe(0);
  });
});

describe('Cross-Component Integration', () => {
  let token, workspace, project, task, user1Id, user2Id, user2Token;

  beforeEach(async () => {
    // Register first user
    const registerRes1 = await request(app)
      .post('/api/users/register')
      .send(testUser1);
    
    token = registerRes1.body.token;
    user1Id = registerRes1.body.user._id;
    
    // Register second user
    const registerRes2 = await request(app)
      .post('/api/users/register')
      .send(testUser2);
    
    user2Id = registerRes2.body.user._id;
    user2Token = registerRes2.body.token;
    
    // Create workspace
    const workspaceRes = await request(app)
      .post('/api/workspaces')
      .set('Authorization', `Bearer ${token}`)
      .send(testWorkspace);
    
    workspace = workspaceRes.body;
    
    // Add second user to workspace
    await request(app)
      .post(`/api/workspaces/${workspace._id}/members`)
      .set('Authorization', `Bearer ${token}`)
      .send({ userId: user2Id });
    
    // Create project
    const projectRes = await request(app)
      .post(`/api/workspaces/${workspace._id}/projects`)
      .set('Authorization', `Bearer ${token}`)
      .send(testProject);
    
    project = projectRes.body;
    
    // Create task
    const taskRes = await request(app)
      .post(`/api/projects/${project._id}/tasks`)
      .set('Authorization', `Bearer ${token}`)
      .send(testTask);
    
    task = taskRes.body;
  });

  test('Full workflow: Create workspace, project, task, assign and complete', async () => {
    // Assign task to user 2
    let response = await request(app)
      .patch(`/api/tasks/${task._id}/assign`)
      .set('Authorization', `Bearer ${token}`)
      .send({ userId: user2Id });
    
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty('assignedTo', user2Id);
    
    // User 2 updates task status to in-progress
    response = await request(app)
      .patch(`/api/tasks/${task._id}/status`)
      .set('Authorization', `Bearer ${user2Token}`)
      .send({ status: 'in-progress' });
    
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty('status', 'in-progress');
    
    // User 2 updates task status to completed
    response = await request(app)
      .patch(`/api/tasks/${task._id}/status`)
      .set('Authorization', `Bearer ${user2Token}`)
      .send({ status: 'completed' });
    
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty('status', 'completed');
    
    // User 1 verifies task is completed
    response = await request(app)
      .get(`/api/tasks/${task._id}`)
      .set('Authorization', `Bearer ${token}`);
    
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty('status', 'completed');
    expect(response.body).toHaveProperty('assignedTo', user2Id);
  });
  
  test('Permission hierarchy: Workspace owner has access to all projects and tasks', async () => {
    // Create a new project with user 2
    const newProjectRes = await request(app)
      .post(`/api/workspaces/${workspace._id}/projects`)
      .set('Authorization', `Bearer ${user2Token}`)
      .send({ name: 'User 2 Project', description: 'Created by user 2' });
    
    expect(newProjectRes.status).toBe(201);
    
    // Create task in that project
    const newTaskRes = await request(app)
      .post(`/api/projects/${newProjectRes.body._id}/tasks`)
      .set('Authorization', `Bearer ${user2Token}`)
      .send({ title: 'User 2 task', description: 'Created by user 2', priority: 'medium', status: 'todo' });
    
    expect(newTaskRes.status).toBe(201);
    
    // User 1 (workspace owner) should be able to access and modify
    const response = await request(app)
      .put(`/api/tasks/${newTaskRes.body._id}`)
      .set('Authorization', `Bearer ${token}`)
      .send({ priority: 'high' });
    
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty('priority', 'high');
  });

  test('Edge case: Handle user removal from workspace gracefully', async () => {
    // Remove user 2 from workspace
    await request(app)
      .delete(`/api/workspaces/${workspace._id}/members/${user2Id}`)
      .set('Authorization', `Bearer ${token}`);
    
    // Try to access workspace with user 2
    const response = await request(app)
      .get(`/api/workspaces/${workspace._id}`)
      .set('Authorization', `Bearer ${user2Token}`);
    
    expect(response.status).toBe(403);
  });

  test('Edge case: Handle workspace deletion and cascading deletions', async () => {
    // Delete workspace
    await request(app)
      .delete(`/api/workspaces/${workspace._id}`)
      .set('Authorization', `Bearer ${token}`);
    
    // Try to access deleted project
    const projectResponse = await request(app)
      .get(`/api/projects/${project._id}`)
      .set('Authorization', `Bearer ${token}`);
    
    expect(projectResponse.status).toBe(404);
    
    // Try to access deleted task
    const taskResponse = await request(app)
      .get(`/api/tasks/${task._id}`)
      .set('Authorization', `Bearer ${token}`);
    
    expect(taskResponse.status).toBe(404);
  });
  
  test('Edge case: Handle concurrent updates to tasks', async () => {
    // Both users try to update the task status
    const promise1 = request(app)
      .patch(`/api/tasks/${task._id}/status`)
      .set('Authorization', `Bearer ${token}`)
      .send({ status: 'in-progress' });
    
    const promise2 = request(app)
      .patch(`/api/tasks/${task._id}/status`)
      .set('Authorization', `Bearer ${user2Token}`)
      .send({ status: 'completed' });
    
    const [response1, response2] = await Promise.all([promise1, promise2]);
    
    // Both should be successful, but one should be the "winner"
    expect(response1.status).toBe(200);
    expect(response2.status).toBe(200);
    
    // Check final state
    const finalState = await request(app)
      .get(`/api/tasks/${task._id}`)
      .set('Authorization', `Bearer ${token}`);
    
    expect(finalState.status).toBe(200);
    expect(['in-progress', 'completed']).toContain(finalState.body.status);
  });
});

describe('Error Handling and Edge Cases', () => {
  let token, workspaceId, projectId, taskId;

  beforeEach(async () => {
    // Register user and get token
    const registerRes = await request(app)
      .post('/api/users/register')
      .send(testUser1);
    
    token = registerRes.body.token;
    
    // Create workspace
    const workspaceRes = await request(app)
      .post('/api/workspaces')
      .set('Authorization', `Bearer ${token}`)
      .send(testWorkspace);
    
    workspaceId = workspaceRes.body._id;
    
    // Create project
    const projectRes = await request(app)
      .post(`/api/workspaces/${workspaceId}/projects`)
      .set('Authorization', `Bearer ${token}`)
      .send(testProject);
    
    projectId = projectRes.body._id;
    
    // Create task
    const taskRes = await request(app)
      .post(`/api/projects/${projectId}/tasks`)
      .set('Authorization', `Bearer ${token}`)
      .send(testTask);
    
    taskId = taskRes.body._id;
  });

  test('Should handle non-existent resources gracefully', async () => {
    const nonExistentId = '60b1c2e68f491e001d3e9999'; // Valid MongoDB ID that doesn't exist
    
    // Try to get non-existent workspace
    const workspaceRes = await request(app)
      .get(`/api/workspaces/${nonExistentId}`)
      .set('Authorization', `Bearer ${token}`);
    
    expect(workspaceRes.status).toBe(404);
    
    // Try to get non-existent project
    const projectRes = await request(app)
      .get(`/api/projects/${nonExistentId}`)
      .set('Authorization', `Bearer ${token}`);
    
    expect(projectRes.status).toBe(404);
    
    // Try to get non-existent task
    const taskRes = await request(app)
      .get(`/api/tasks/${nonExistentId}`)
      .set('Authorization', `Bearer ${token}`);
    
    expect(taskRes.status).toBe(404);
  });

  test('Should handle invalid MongoDB IDs gracefully', async () => {
    const invalidId = 'not-a-valid-id';
    
    // Try to get with invalid ID
    const response = await request(app)
      .get(`/api/workspaces/${invalidId}`)
      .set('Authorization', `Bearer ${token}`);
    
    expect(response.status).toBe(400);
  });

  test('Should handle expired tokens gracefully', async () => {
    const expiredToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiI2MGIxYzJlNjhmNDkxZTAwMWQzZTk5OTkiLCJpYXQiOjE2MjIyMTMzNTAsImV4cCI6MTYyMjIxMzM1MH0.2hV0o9vFcQ1XJq7TZgxA9JAhwL5K5YVEuk6J_nGkNuE';
    
    const response = await request(app)
      .get('/api/users/me')
      .set('Authorization', `Bearer ${expiredToken}`);
    
    expect(response.status).toBe(401);
  });

  test('Should handle rate limiting', async () => {
    // Make many requests in quick succession
    const promises = [];
    const requestCount = 50; // Adjust this based on your rate limit settings
    
    for (let i = 0; i < requestCount; i++) {
      promises.push(
        request(app)
          .get('/api/users/me')
          .set('Authorization', `Bearer ${token}`)
      );
    }
    
    const responses = await Promise.all(promises);
    
    // At least some of the later requests should be rate limited (status 429)
    const rateLimitedResponses = responses.filter(res => res.status === 429);
    expect(rateLimitedResponses.length).toBeGreaterThan(0);
  });

  test('Should handle large payload gracefully', async () => {
    // Create a very large task description
    const largeDescription = 'a'.repeat(100000); // 100KB of data
    
    const response = await request(app)
      .post(`/api/projects/${projectId}/tasks`)
      .set('Authorization', `Bearer ${token}`)
      .send({ ...testTask, description: largeDescription });
    
    // Should either reject with 413 Payload Too Large or handle it gracefully
    expect([201, 413]).toContain(response.status);
  });

  test('Should handle malformed JSON gracefully', async () => {
    // This simulates sending malformed JSON data, which our supertest can't actually do directly
    // In a real application, we'd need to test this differently, but this illustrates the concept
    const rawResponse = await request(app)
      .post('/api/users/login')
      .set('Content-Type', 'application/json')
      .send('{"email": "test@example.com", "password": "incomplete JSON');
    
    expect(rawResponse.status).toBe(400);
  });
});