#!/usr/bin/env python3
"""
Database initialization script for Receipts Automation App
Run this script to create the database and tables
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from app import app, db
from models import Receipt, ProcessingJob

def create_database():
    """Create the database if it doesn't exist"""
    # Get database URL from config
    database_url = app.config['SQLALCHEMY_DATABASE_URI']
    
    # Extract database name from URL
    if 'postgresql://' in database_url:
        # Parse PostgreSQL URL
        db_name = database_url.split('/')[-1]
        base_url = database_url.rsplit('/', 1)[0]
        
        # Connect to PostgreSQL server (not specific database)
        engine = create_engine(base_url + '/postgres')
        
        try:
            with engine.connect() as conn:
                # Check if database exists
                result = conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'"))
                if not result.fetchone():
                    # Create database
                    conn.execute(text(f"CREATE DATABASE {db_name}"))
                    print(f"Database '{db_name}' created successfully")
                else:
                    print(f"Database '{db_name}' already exists")
        except OperationalError as e:
            print(f"Error connecting to PostgreSQL: {e}")
            print("Make sure PostgreSQL is running and credentials are correct")
            return False
    
    return True

def init_tables():
    """Initialize database tables"""
    try:
        with app.app_context():
            db.create_all()
            print("Database tables created successfully")
            return True
    except Exception as e:
        print(f"Error creating tables: {e}")
        return False

def main():
    """Main initialization function"""
    print("Initializing Receipts Automation Database...")
    
    # Create database
    if not create_database():
        sys.exit(1)
    
    # Initialize tables
    if not init_tables():
        sys.exit(1)
    
    print("Database initialization completed successfully!")
    print("\nNext steps:")
    print("1. Update your .env file with correct database credentials")
    print("2. Run 'flask db init' to initialize migrations")
    print("3. Run 'flask db migrate -m \"Initial migration\"' to create migration")
    print("4. Run 'flask db upgrade' to apply migrations")
    print("5. Start the Flask app with 'python app.py'")

if __name__ == '__main__':
    main()
