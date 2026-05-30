"""
One-time migration: make businesses.twilio_number nullable.

Run with the backend STOPPED:
    cd backend
    python migrate_twilio_nullable.py
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "receptionist.db"

if not DB_PATH.exists():
    print(f"Database not found at {DB_PATH} — nothing to migrate.")
    sys.exit(0)

conn = sqlite3.connect(str(DB_PATH))
c = conn.cursor()

# Check if migration is already applied
c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='businesses'")
schema = c.fetchone()[0]
if "twilio_number VARCHAR(64)," in schema and "NOT NULL" not in schema.split("twilio_number")[1].split(",")[0]:
    print("Already migrated — twilio_number is already nullable.")
    conn.close()
    sys.exit(0)

print("Migrating businesses.twilio_number to nullable...")

c.executescript("""
PRAGMA foreign_keys=OFF;

CREATE TABLE businesses_new (
    id INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    twilio_number VARCHAR(64),
    twilio_number_normalized VARCHAR(32),
    forwarding_number VARCHAR(64),
    greeting TEXT,
    business_hours VARCHAR(255),
    booking_enabled BOOLEAN,
    knowledge_text TEXT,
    google_calendar_connected BOOLEAN,
    google_account_email VARCHAR(255),
    google_calendar_id VARCHAR(255),
    google_token_json TEXT,
    created_at DATETIME,
    PRIMARY KEY (id)
);

INSERT INTO businesses_new SELECT * FROM businesses;
DROP TABLE businesses;
ALTER TABLE businesses_new RENAME TO businesses;

CREATE INDEX IF NOT EXISTS ix_businesses_id ON businesses (id);
CREATE INDEX IF NOT EXISTS ix_businesses_twilio_number ON businesses (twilio_number);
CREATE INDEX IF NOT EXISTS ix_businesses_twilio_number_normalized ON businesses (twilio_number_normalized);

PRAGMA foreign_keys=ON;
""")

conn.commit()

# Verify
c.execute("SELECT id, name, twilio_number FROM businesses")
rows = c.fetchall()
print(f"Migration complete. {len(rows)} business row(s) preserved:")
for row in rows:
    print(f"  id={row[0]}  name={row[1]}  twilio_number={row[2]}")

conn.close()
