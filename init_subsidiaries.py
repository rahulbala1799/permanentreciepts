#!/usr/bin/env python3
"""
Script to initialize subsidiaries in the database
"""

import os
import sys
from datetime import datetime

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db, Subsidiary

def init_subsidiaries():
    """Initialize subsidiaries in the database"""
    with app.app_context():
        
        # Check if subsidiaries already exist
        existing_subsidiaries = Subsidiary.query.all()
        if existing_subsidiaries:
            print("Subsidiaries already exist in the database:")
            for sub in existing_subsidiaries:
                print(f"  - {sub.name} ({sub.code})")
            return
        
        # Define subsidiaries
        subsidiaries_data = [
            {
                'name': 'Phorest Australia',
                'code': 'AU',
                'region': 'Australia'
            },
            {
                'name': 'Canada',
                'code': 'CA',
                'region': 'North America'
            },
            {
                'name': 'USA',
                'code': 'US',
                'region': 'North America'
            },
            {
                'name': 'EU',
                'code': 'EU',
                'region': 'Europe'
            },
            {
                'name': 'UK',
                'code': 'UK',
                'region': 'Europe'
            }
        ]
        
        # Create subsidiaries
        for sub_data in subsidiaries_data:
            subsidiary = Subsidiary(
                name=sub_data['name'],
                code=sub_data['code'],
                region=sub_data['region'],
                is_active=True,
                created_at=datetime.utcnow()
            )
            db.session.add(subsidiary)
        
        # Commit changes
        db.session.commit()
        
        print("Successfully initialized subsidiaries:")
        for sub_data in subsidiaries_data:
            print(f"  - {sub_data['name']} ({sub_data['code']}) - {sub_data['region']}")

if __name__ == '__main__':
    init_subsidiaries()
