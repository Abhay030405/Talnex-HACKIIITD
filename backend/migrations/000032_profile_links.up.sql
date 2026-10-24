-- Profile pages found on the resume (GitHub, LinkedIn, portfolio, Kaggle, ...), kind -> address. Links only: emails and
-- phone numbers are never stored (AGENTS.md rule 21). Editable on the confirm page.
ALTER TABLE candidates ADD COLUMN profile_links jsonb NOT NULL DEFAULT '{}';
