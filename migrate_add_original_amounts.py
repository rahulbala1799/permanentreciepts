#!/usr/bin/env python3
"""
Migration script to add original_amounts column to fp_datasets table
"""

import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Database connection parameters
DB_HOST = 'localhost'
DB_PORT = '5432'
DB_NAME = 'permanent_receipts'
DB_USER = 'postgres'
DB_PASSWORD = 'password'

def run_migration():
    """Add original_amounts column to fp_datasets table"""
    try:
        # Connect to database
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='fp_datasets' AND column_name='original_amounts'
        """)
        
        if cursor.fetchone():
            print("Column 'original_amounts' already exists in fp_datasets table")
            return True
        
        # Add the column
        cursor.execute("""
            ALTER TABLE fp_datasets 
            ADD COLUMN original_amounts TEXT
        """)
        
        print("Successfully added 'original_amounts' column to fp_datasets table")
        return True
        
    except Exception as e:
        print(f"Migration failed: {e}")
        return False
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)

