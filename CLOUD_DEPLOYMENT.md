# CollabHub Cloud Deployment Guide

This guide will walk you through deploying CollabHub to Google Cloud Platform.

## Prerequisites

1. A Google Cloud Platform account
2. Google Cloud SDK installed locally
3. Docker installed locally (for building and testing containers)

## Step 1: Set Up Google Cloud Project

1. Create a new project in Google Cloud Console:
   ```
   gcloud projects create collabhub-app --name="CollabHub"
   ```

2. Set the project as your default:
   ```
   gcloud config set project collabhub-app
   ```

3. Enable the required APIs:
   ```
   gcloud services enable compute.googleapis.com
   gcloud services enable sqladmin.googleapis.com
   gcloud services enable redis.googleapis.com
   gcloud services enable artifactregistry.googleapis.com
   gcloud services enable storage.googleapis.com
   gcloud services enable cloudbuild.googleapis.com
   gcloud services enable run.googleapis.com
   ```

## Step 2: Set Up Database (Cloud SQL)

1. Create a PostgreSQL instance:
   ```
   gcloud sql instances create collabhub-db \
     --database-version=POSTGRES_14 \
     --tier=db-f1-micro \
     --region=us-central1 \
     --root-password=your-secure-password
   ```

2. Create a database:
   ```
   gcloud sql databases create collabhub --instance=collabhub-db
   ```

3. Create a user:
   ```
   gcloud sql users create collabhub-user \
     --instance=collabhub-db \
     --password=your-user-password
   ```

4. Note the connection string for later:
   ```
   gcloud sql instances describe collabhub-db --format="value(connectionName)"
   ```

## Step 3: Set Up Redis (Memorystore)

1. Create a Redis instance:
   ```
   gcloud redis instances create collabhub-redis \
     --size=1 \
     --region=us-central1 \
     --redis-version=redis_6_x
   ```

2. Get the Redis IP address:
   ```
   gcloud redis instances describe collabhub-redis \
     --region=us-central1 \
     --format="value(host)"
   ```

## Step 4: Set Up Storage Bucket

1. Create a bucket for media and static files:
   ```
   gsutil mb -l us-central1 gs://collabhub-media
   ```

2. Make the bucket publicly readable:
   ```
   gsutil iam ch allUsers:objectViewer gs://collabhub-media
   ```

3. Create a service account for storage access:
   ```
   gcloud iam service-accounts create collabhub-storage-sa \
     --display-name="CollabHub Storage Access"
   ```

4. Grant the service account access to the bucket:
   ```
   gsutil iam ch serviceAccount:collabhub-storage-sa@collabhub-app.iam.gserviceaccount.com:objectAdmin gs://collabhub-media
   ```

5. Create and download a key for the service account:
   ```
   gcloud iam service-accounts keys create credentials.json \
     --iam-account=collabhub-storage-sa@collabhub-app.iam.gserviceaccount.com
   ```

## Step 5: Configure Environment Variables

Create a `.env` file for your production settings:

1. Copy the example file:
   ```
   cp .env.example .env
   ```

2. Fill in the values based on your Google Cloud resources. For example:

   ```
   DEBUG=False
   SECRET_KEY=your-production-secret-key
   ALLOWED_HOSTS=your-app-url.run.app,your-custom-domain

   DATABASE_URL=postgres://collabhub-user:your-user-password@/collabhub?host=/cloudsql/your-connection-name

   REDIS_URL=redis://your-redis-ip:6379/0

   USE_GCS=True
   GS_BUCKET_NAME=collabhub-media
   GS_CREDENTIALS=/app/credentials.json
   GCS_STATIC=True
   ```

## Step 6: Build and Push Docker Image

1. Create an Artifact Registry repository:
   ```
   gcloud artifacts repositories create collabhub-repo \
     --repository-format=docker \
     --location=us-central1
   ```

2. Configure Docker for authentication:
   ```
   gcloud auth configure-docker us-central1-docker.pkg.dev
   ```

3. Build and tag the image:
   ```
   docker build -t us-central1-docker.pkg.dev/collabhub-app/collabhub-repo/collabhub:latest .
   ```

4. Push the image to Artifact Registry:
   ```
   docker push us-central1-docker.pkg.dev/collabhub-app/collabhub-repo/collabhub:latest
   ```

## Step 7: Deploy to Cloud Run

1. Deploy the web service:
   ```
   gcloud run deploy collabhub-web \
     --image=us-central1-docker.pkg.dev/collabhub-app/collabhub-repo/collabhub:latest \
     --region=us-central1 \
     --platform=managed \
     --allow-unauthenticated \
     --add-cloudsql-instances=your-connection-name \
     --set-env-vars="COLLABHUB_ENVIRONMENT=production" \
     --update-secrets=SECRET_KEY=collabhub-secret-key:latest \
     --update-secrets=GS_CREDENTIALS=/app/credentials.json:collabhub-gcs-creds:latest \
     --memory=512Mi \
     --concurrency=80 \
     --timeout=300s
   ```

2. Deploy Celery worker:
   ```
   gcloud run deploy collabhub-worker \
     --image=us-central1-docker.pkg.dev/collabhub-app/collabhub-repo/collabhub:latest \
     --region=us-central1 \
     --platform=managed \
     --no-allow-unauthenticated \
     --command="celery" \
     --args="-A,collabhub,worker,--loglevel=info" \
     --add-cloudsql-instances=your-connection-name \
     --set-env-vars="COLLABHUB_ENVIRONMENT=production" \
     --update-secrets=SECRET_KEY=collabhub-secret-key:latest \
     --update-secrets=GS_CREDENTIALS=/app/credentials.json:collabhub-gcs-creds:latest \
     --memory=512Mi
   ```

3. Deploy Celery beat scheduler:
   ```
   gcloud run deploy collabhub-beat \
     --image=us-central1-docker.pkg.dev/collabhub-app/collabhub-repo/collabhub:latest \
     --region=us-central1 \
     --platform=managed \
     --no-allow-unauthenticated \
     --command="celery" \
     --args="-A,collabhub,beat,--loglevel=info" \
     --add-cloudsql-instances=your-connection-name \
     --set-env-vars="COLLABHUB_ENVIRONMENT=production" \
     --update-secrets=SECRET_KEY=collabhub-secret-key:latest \
     --update-secrets=GS_CREDENTIALS=/app/credentials.json:collabhub-gcs-creds:latest \
     --memory=256Mi
   ```

## Step 8: Run Database Migrations

Create a one-time migration job:

```
gcloud run jobs create collabhub-migrate \
  --image=us-central1-docker.pkg.dev/collabhub-app/collabhub-repo/collabhub:latest \
  --command="python" \
  --args="manage.py,migrate,--settings=collabhub.settings_prod" \
  --add-cloudsql-instances=your-connection-name \
  --set-env-vars="COLLABHUB_ENVIRONMENT=production" \
  --update-secrets=SECRET_KEY=collabhub-secret-key:latest \
  --update-secrets=GS_CREDENTIALS=/app/credentials.json:collabhub-gcs-creds:latest
```

Run the migration job:
```
gcloud run jobs execute collabhub-migrate
```

## Step 9: Setup WebSockets (Optional)

For WebSockets in production, you may need additional configuration:

1. Set up Google Cloud Armor to allow WebSocket connections
2. Configure your service with higher timeout values
3. Consider using a serverless WebSocket service like Firebase

## Managing Data

### Backing up your database

```
gcloud sql export sql collabhub-db gs://collabhub-media/backups/backup-$(date +%Y%m%d).sql \
  --database=collabhub
```

### Restoring from backup

```
gcloud sql import sql collabhub-db gs://collabhub-media/backups/backup-YYYYMMDD.sql \
  --database=collabhub
```

## Monitoring

1. Set up Cloud Monitoring to track your CollabHub services
2. Create alerts for critical failures
3. Set up logging to capture application errors

## Cost Optimization

To reduce costs:

1. Use Cloud Run service minimums
2. Set up scheduled scaling for non-peak hours
3. Choose appropriate instance sizes for your database and Redis

## Local Testing

Before deploying to Google Cloud, test your production configuration locally using Docker Compose:

```
docker-compose up
```

This will start your application with Redis and PostgreSQL, allowing you to test the production configuration on your local machine.