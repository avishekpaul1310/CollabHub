# CollabHub - Contextual Collaboration Hub

A modern web application for team collaboration that combines messaging, document management, and work item tracking in a single integrated platform.

## Features

- **User Authentication**: Secure login and registration system
- **Work Item Management**: Create, track, and manage work items
- **Real-time Messaging**: Instant communication through WebSocket technology
- **File Sharing**: Upload and share files with team members
- **User Notifications**: Get notified of important events in real-time
- **Modern UI**: Clean, responsive interface built with Bootstrap

## Technologies Used

- **Backend**: Django, Django Channels
- **Frontend**: HTML, CSS, JavaScript, Bootstrap
- **Database**: SQLite (development), PostgreSQL (recommended for production)
- **Real-time Communication**: WebSockets with Daphne/ASGI
- **Authentication**: Django Authentication System

## Getting Started

### Prerequisites

- Python 3.8+
- Node.js and npm (for frontend assets)
- Redis server (for WebSocket support)

### Installation

1. Clone the repository
   ```bash
   git clone https://github.com/avishekpaul1310/CollabHub.git
   cd CollabHub
## Running the Application

CollabHub uses WebSockets for real-time features like chat, notifications, and live updates. Therefore, it must be run using Daphne instead of Django's standard development server.

### Development

To run the development server:

```bash
daphne -p 8000 collabhub.asgi:application
