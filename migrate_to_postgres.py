#!/usr/bin/env python
"""
Script to migrate data from SQLite to PostgreSQL for local testing.

This is useful when you want to test the production configuration locally
with PostgreSQL while preserving your development data from SQLite.

Usage:
    python migrate_to_postgres.py

Prerequisites:
    - Docker and Docker Compose must be running
    - The PostgreSQL container should be up and reachable
"""

import os
import subprocess
import json
import sys

def run_command(command, description=None):
    """Run a command and return the output"""
    if description:
        print(f"\n{description}...")
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        print(f"Command output: {e.stderr}")
        sys.exit(1)

def check_prerequisites():
    """Check if Docker and Docker Compose are running"""
    print("Checking prerequisites...")
    
    # Check if Docker is running
    run_command("docker info", "Checking Docker connection")
    
    # Check if PostgreSQL container is running
    try:
        run_command("docker-compose ps db | grep Up", "Checking if PostgreSQL is up")
        print("PostgreSQL container is running.")
    except:
        print("PostgreSQL container is not running. Please start it with:")
        print("docker-compose up -d db")
        sys.exit(1)
        
    # Check if we have the SQLite database
    if not os.path.exists('db.sqlite3'):
        print("SQLite database (db.sqlite3) not found.")
        sys.exit(1)

def dump_sqlite_data():
    """Dump data from SQLite database"""
    print("Dumping data from SQLite database...")
    
    # Create a backup using Django's dumpdata
    run_command(
        "python manage.py dumpdata --exclude=auth.permission --exclude=contenttypes --indent=2 > data_backup.json",
        "Creating backup of all data"
    )
    
    print("SQLite data dumped to data_backup.json")
    return "data_backup.json"

def configure_postgres_settings():
    """Configure Django to use PostgreSQL temporarily"""
    print("Configuring Django to use PostgreSQL...")
    
    # Set environment variables for PostgreSQL connection
    os.environ["COLLABHUB_ENVIRONMENT"] = "production"
    os.environ["DATABASE_URL"] = "postgres://collabhub_user:collabhub_password@localhost:5432/collabhub"
    
    # Ensure Django sees these settings
    os.environ["DJANGO_SETTINGS_MODULE"] = "collabhub.settings_prod"

def migrate_postgres_schema():
    """Run migrations on PostgreSQL database"""
    print("Running migrations on PostgreSQL...")
    
    run_command(
        "python manage.py migrate --settings=collabhub.settings_prod",
        "Creating tables in PostgreSQL"
    )

def load_data_into_postgres(data_file):
    """Load data into PostgreSQL database"""
    print("Loading data into PostgreSQL...")
    
    run_command(
        f"python manage.py loaddata {data_file} --settings=collabhub.settings_prod",
        "Loading data into PostgreSQL"
    )

def main():
    """Main function to migrate data"""
    print("Starting migration from SQLite to PostgreSQL...")
    
    # Check prerequisites
    check_prerequisites()
    
    # Dump data from SQLite
    data_file = dump_sqlite_data()
    
    # Configure PostgreSQL settings
    configure_postgres_settings()
    
    # Migrate schema
    migrate_postgres_schema()
    
    # Load data into PostgreSQL
    load_data_into_postgres(data_file)
    
    print("\n✅ Migration completed successfully!")
    print("\nYou can now run the application with:")
    print("docker-compose up")
    print("\nYour data has been migrated from SQLite to PostgreSQL.")

if __name__ == "__main__":
    main()