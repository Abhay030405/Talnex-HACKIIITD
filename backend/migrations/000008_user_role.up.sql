-- One role per account: a person signs in through the recruiter door or the organizer door.
-- NULL means "not chosen yet"; the first sign-in through a door sets it and it never changes.
ALTER TABLE users
    ADD COLUMN role text CHECK (role IN ('recruiter', 'organizer'));

-- Accounts that already own something keep working: they get the role that matches what they own.
UPDATE users u SET role = 'organizer'
 WHERE role IS NULL AND EXISTS (SELECT 1 FROM events e WHERE e.owner_id = u.id);
UPDATE users u SET role = 'recruiter'
 WHERE role IS NULL AND EXISTS (SELECT 1 FROM candidates c WHERE c.owner_id = u.id);
