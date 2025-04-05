# CollabHub

CollabHub is a comprehensive collaboration platform built with Django, featuring real-time communication, work item management, thoughtful messaging, and robust search functionality.

## Overview

CollabHub is designed to enhance team collaboration with features like:

- **Work Items**: Create and manage tasks, documents, and projects
- **Real-time Messaging**: Chat instantly with WebSockets
- **Threaded Discussions**: Organize conversations by topic
- **Slow Channels**: For thoughtful, asynchronous communication
- **File Sharing**: Upload and search through files
- **Work-Life Balance Tools**: Notification preferences, working hours, and focus mode
- **Full-text Search**: Find content across all workspace elements

## Architecture

CollabHub is built on Django with several key components:

- **Django Channels**: Powers real-time WebSocket communication
- **Redis**: Serves as the channel layer and message broker
- **Celery**: Handles background tasks like scheduled messages and file indexing
- **Celery Beat**: Manages periodic tasks

## Project Structure

The application consists of several Django apps:

- **workspace**: Core collaboration features (work items, messages, threads)
- **users**: User management and profiles
- **search**: Full-text search functionality with file indexing

## Requirements

- Python 3.8+
- Django 5.1+
- Redis
- Additional dependencies in `requirements.txt`

## Installation

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure settings in `collabhub/settings.py`
5. Run migrations:
   ```bash
   python manage.py migrate
   ```
6. Create a superuser:
   ```bash
   python manage.py createsuperuser
   ```

## Running the Application

CollabHub requires multiple components running simultaneously:

1. **Redis Server** (message broker and channel layer)
2. **Django Channels/Daphne** (WebSocket server)
3. **Celery Worker** (background tasks)
4. **Celery Beat** (scheduled tasks)

### Using Provided Scripts

For convenience, the project includes batch scripts to start and stop all required components:

- `start_collabhub.bat`: Starts Redis, Celery Worker, Celery Beat, and Daphne
- `stop_collabhub.bat`: Stops all running components

**Note**: You may need to modify the paths in these scripts to match your installation.

### Manual Start

If you prefer to start components individually:

1. **Start Redis Server**:
   ```bash
   redis-server
   ```

2. **Start Celery Worker**:
   ```bash
   celery -A collabhub worker --pool=solo -l info
   ```

3. **Start Celery Beat**:
   ```bash
   celery -A collabhub beat -l info
   ```

4. **Start Daphne** (ASGI server):
   ```bash
   daphne -p 8000 collabhub.asgi:application
   ```

## Key Features

### Work Items

- Create tasks, documents, and projects
- Add collaborators
- Attach files
- Real-time messaging

### Real-time Communication

- WebSocket-based chat
- Read receipts
- Message threading
- Emoji reactions

### Slow Channels

Designed for thoughtful, asynchronous communication:

- Intentional delivery delays
- Minimum response intervals
- Guided discussions with prompts
- Reflection and ideation modes

### Search Functionality

- Full-text search across all content
- File content indexing
- Advanced filters
- Saved searches

### Work-Life Balance

- Notification preferences
- Do Not Disturb periods
- Working hours settings
- Focus mode
- Break reminders
- Analytics dashboard


## Contributing

[Insert contribution guidelines here]
