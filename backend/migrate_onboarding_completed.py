"""
One-time migration: add onboarding_completed column to businesses table,
and revert name to NOT NULL by converting empty/NULL names to the google_account_email.
"""
import sqlite3, pathlib, sys

DB = pathlib.Path(__file__).parent / "receptionist.db"
if not DB.exists():
    sys.exit(f"Database not found at {DB}")

conn = sqlite3.connect(DB)
cur = conn.cursor()

# 1. Add onboarding_completed column (SQLite supports ADD COLUMN with a default)
cur.execute("PRAGMA table_info(businesses)")
existing_cols = [row[1] for row in cur.fetchall()]

if "onboarding_completed" not in existing_cols:
    print("Adding onboarding_completed column …")
    cur.execute("ALTER TABLE businesses ADD COLUMN onboarding_completed BOOLEAN NOT NULL DEFAULT 0")
else:
    print("onboarding_completed column already exists, skipping.")

# 2. Mark existing businesses with a real name as onboarding_completed=1
cur.execute("UPDATE businesses SET onboarding_completed = 1 WHERE name IS NOT NULL AND trim(name) != ''")
print(f"  Marked {cur.rowcount} existing business(es) as onboarding_completed")

# 3. Fix any '' or NULL names by falling back to google_account_email
cur.execute("""
    UPDATE businesses
    SET name = COALESCE(NULLIF(trim(name), ''), google_account_email, 'My Business')
    WHERE name IS NULL OR trim(name) = ''
""")
print(f"  Fixed {cur.rowcount} business(es) with empty/NULL names")

conn.commit()
conn.close()
print("Done.")
