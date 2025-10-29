#!/usr/bin/env python3
"""
Add original_amounts column to fp_datasets table using SQLAlchemy
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from sqlalchemy import text

def add_column():
    """Add original_amounts column to fp_datasets table"""
    try:
        with app.app_context():
            # Check if column exists
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='fp_datasets' AND column_name='original_amounts'
            """))
            
            if result.fetchone():
                print("Column 'original_amounts' already exists in fp_datasets table")
                return True
            
            # Add the column
            db.session.execute(text("""
                ALTER TABLE fp_datasets 
                ADD COLUMN original_amounts TEXT
            """))
            
            db.session.commit()
            print("Successfully added 'original_amounts' column to fp_datasets table")
            return True
            
    except Exception as e:
        print(f"Migration failed: {e}")
        db.session.rollback()
        return False

if __name__ == "__main__":
    success = add_column()
    sys.exit(0 if success else 1)

