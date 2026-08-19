-- Runs once when the Postgres container initialises its data directory.
-- Schema itself is owned by Alembic (`alembic upgrade head`); this file only
-- sets up things migrations should not depend on.

-- Case-insensitive search on usernames in the admin panel.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Postgres' own random() is enough for reporting; game outcomes never use it —
-- they come from the HMAC seed chain or the OS CSPRNG.
SET timezone TO 'UTC';
