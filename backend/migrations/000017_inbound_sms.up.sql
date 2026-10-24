-- Text messages forwarded by the team phone (login ladder, phone way-in). Personal data: rows are deleted after 24 hours.
CREATE TABLE inbound_sms (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    from_number text        NOT NULL,
    body        text        NOT NULL,
    device      text,
    received_at timestamptz NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX inbound_sms_created_at_idx ON inbound_sms (created_at);
