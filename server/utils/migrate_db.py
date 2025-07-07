#!/usr/bin/env python3
"""
Database migration utility for Papyrus RSS aggregator

This script handles database schema migrations to ensure compatibility
between different versions of the application.

Usage:
    python server/utils/migrate_db.py

Current migrations:
    - v1: Add is_visible column to feeds table for feed visibility controls
"""

import duckdb
import sys
import os

def migrate_database():
    """
    Adds is_visible column to feeds table if it doesn't exist
    
    This migration enables users to hide/show feeds without deleting them.
    All existing feeds are set to visible by default.
    """
    db_path = '../data/papyrus.db'
    
    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found!")
        return False
    
    try:
        db = duckdb.connect(db_path)
        
        # Check if is_visible column already exists
        columns = db.execute("PRAGMA table_info(feeds)").fetchall()
        column_names = [col[1] for col in columns]
        
        if 'is_visible' in column_names:
            print("✓ is_visible column already exists in feeds table")
            return True
        
        print("Adding is_visible column to feeds table...")
        
        # Add the column with default value TRUE
        db.execute("ALTER TABLE feeds ADD COLUMN is_visible BOOLEAN DEFAULT TRUE")
        
        # Update all existing feeds to be visible
        db.execute("UPDATE feeds SET is_visible = TRUE WHERE is_visible IS NULL")
        
        # Count total feeds
        count_result = db.execute("SELECT COUNT(*) FROM feeds").fetchone()
        total_feeds = count_result[0] if count_result else 0
        
        print(f"✓ Successfully added is_visible column")
        print(f"✓ Updated {total_feeds} existing feeds to be visible")
        
        # Verify the migration
        columns_after = db.execute("PRAGMA table_info(feeds)").fetchall()
        print("\nCurrent feeds table structure:")
        for col in columns_after:
            print(f"  {col[1]} ({col[2]})")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    print("Starting database migration...")
    success = migrate_database()
    
    if success:
        print("\n✓ Migration completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)