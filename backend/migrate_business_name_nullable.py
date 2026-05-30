"""
One-time migration: make businesses.name nullable (was NOT NULL).
SQLite doesn't support ALTER COLUMN, so we use the new-table/copy/rename pattern.
"""
import sqlite3, pathlib, sys

DB = pathlib.Path(__file__).parent / "receptionist.db"
if not DB.exists():
    sys.exit(f"Database not found at {DB}")

conn = sqlite3.connect(DB)
cur = conn.cursor()

print("Migrating businesses.name to nullable …")

# Get existing columns so the COPY covers them all
cur.execute("PRAGMA table_info(businesses)")
cols = [row[1] for row in cur.fetchall()]
col_list = ", ".join(cols)

cur.executescript(f"""
BEGIN;

CREATE TABLE businesses_new (
    id              INTEGER PRIMARY KEY,
    name            VARCHAR(255),            -- was NOT NULL, now nullable
    twilio_number   VARCHAR(64),
    twilio_number_normalized VARCHAR(32),
    forwarding_number VARCHAR(64),
    greeting        TEXT,
    business_hours  VARCHAR(255),
    booking_enabled BOOLEAN DEFAULT 1,
    knowledge_text  TEXT,
    google_calendar_connected BOOLEAN DEFAULT 0,
    google_account_email VARCHAR(255),
    google_calendar_id VARCHAR(255),
    google_token_json TEXT,
    created_at      DATETIME
);

INSERT INTO businesses_new ({col_list})
SELECT {col_list} FROM businesses;

DROP TABLE businesses;
ALTER TABLE businesses_new RENAME TO businesses;

-- Re-create indexes
CREATE INDEX IF NOT EXISTS ix_businesses_twilio_number ON businesses (twilio_number);
CREATE INDEX IF NOT EXISTS ix_businesses_twilio_number_normalized ON businesses (twilio_number_normalized);
CREATE INDEX IF NOT EXISTS ix_businesses_id ON businesses (id);

COMMIT;
""")

# Also update any existing '' rows to NULL
cur.execute("UPDATE businesses SET name = NULL WHERE name = ''")
conn.commit()
updated = cur.rowcount
print(f"  Converted {updated} empty-string name(s) to NULL")

conn.close()
print("Done.")
