# CollabHub: How to Test and Deploy

This guide explains how to work with both the development and production configurations for CollabHub.

## Development Environment

Your original development environment is still intact and works exactly as before.

### Running in Development Mode

To run CollabHub in development mode:

```bash
python manage.py runserver
```

This will use your original `settings.py` file with SQLite, InMemoryChannelLayer, etc. - perfect for local development.

### Running Celery in Development Mode

```bash
# Start Redis if not running
redis-server

# Start Celery worker
celery -A collabhub worker --loglevel=info

# Start Celery beat for scheduled tasks
celery -A collabhub beat --loglevel=info
```

## Testing Production Configuration Locally

Before deploying to Google Cloud, you can test the production configuration locally to ensure everything works as expected.

### Option 1: Using Docker Compose (Recommended)

1. Start the Docker Compose environment:
   ```bash
   docker-compose up -d
   ```

2. Migrate your data from SQLite to PostgreSQL (optional):
   ```bash
   python migrate_to_postgres.py
   ```

3. Access the application at http://localhost:8000

4. When done, stop the containers:
   ```bash
   docker-compose down
   ```

### Option 2: Running Locally with Production Settings

1. Create a `.env` file from `.env.example`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with local test values:
   ```
   DEBUG=True
   SECRET_KEY=your-test-secret-key
   ALLOWED_HOSTS=localhost,127.0.0.1
   DATABASE_URL=postgres://username:password@localhost:5432/collabhub
   REDIS_URL=redis://localhost:6379/0
   ```

3. Install PostgreSQL and Redis on your machine

4. Run the application with production settings:
   ```bash
   COLLABHUB_ENVIRONMENT=production python manage.py runserver
   ```

5. Run Celery with production settings:
   ```bash
   COLLABHUB_ENVIRONMENT=production celery -A collabhub worker --loglevel=info
   COLLABHUB_ENVIRONMENT=production celery -A collabhub beat --loglevel=info
   ```

## Moving to Production

When you're ready to deploy to Google Cloud:

1. Follow the complete step-by-step guide in `CLOUD_DEPLOYMENT.md`

2. Remember to set `DEBUG=False` in your production environment

3. Generate a strong secret key for production:
   ```python
   from django.core.management.utils import get_random_secret_key
   print(get_random_secret_key())
   ```

## Checking WebSocket Support

Since your application uses WebSockets extensively, ensure they're working:

1. In development:
   ```
   python manage.py check_websocket_support
   ```

2. In production (Docker Compose):
   ```
   docker-compose exec web python manage.py check_websocket_support
   ```

## Common Debugging Tasks

### Check Celery Tasks

```bash
# Development
celery -A collabhub inspect active

# Production (Docker)
docker-compose exec celery celery -A collabhub inspect active
```

### View Application Logs

```bash
# Development 
# Check console output

# Production (Docker)
docker-compose logs -f web
docker-compose logs -f celery
docker-compose logs -f celery-beat
```

### Database Commands

```bash
# Access development database (SQLite)
python manage.py dbshell

# Access production database (PostgreSQL in Docker)
docker-compose exec db psql -U collabhub_user -d collabhub
```

## Testing Specific Features

### Test WebSockets

1. Open a browser at http://localhost:8000 (or your deployed URL)
2. Log in with test credentials
3. Open the chat feature in two different browsers
4. Verify messages are delivered between them immediately

### Test Celery Tasks

1. Schedule a message for future delivery
2. Wait for the task to execute (or adjust the schedule time to be sooner)
3. Verify the message is delivered at the scheduled time

## Switching Between Environments

You can easily switch between development and production configurations:

- For development: Use the standard Django commands without special environment variables
- For production: Use the `COLLABHUB_ENVIRONMENT=production` prefix or Docker Compose

Remember that your original development environment is completely preserved!