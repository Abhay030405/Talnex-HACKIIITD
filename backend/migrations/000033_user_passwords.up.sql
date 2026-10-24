-- Email and password sign-in. Accounts made through Google or the local email-only sign-in have no password.
-- The hash is bcrypt (cost 12) of the SHA-256 of the password, so passwords longer than bcrypt's 72 bytes still count.
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash text;
