import sqlite3

def check_database_schema():
    try:
        conn = sqlite3.connect('./db/ncert_tutor.db')
        cursor = conn.cursor()
        
        # Check ncert_chunks table schema
        print("=== ncert_chunks table schema ===")
        cursor.execute('PRAGMA table_info(ncert_chunks)')
        columns = cursor.fetchall()
        for col in columns:
            print(f"Column: {col[1]}, Type: {col[2]}, NotNull: {col[3]}, Default: {col[4]}, PrimaryKey: {col[5]}")
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ncert_chunks'")
        table_exists = cursor.fetchone()
        print(f"\nTable 'ncert_chunks' exists: {table_exists is not None}")
        
        # Check all tables in database
        print("\n=== All tables in database ===")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        for table in tables:
            print(f"Table: {table[0]}")
        
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_database_schema()
