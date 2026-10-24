-- What the browser's developer tools saw during a live test step: API calls with their status and response time,
-- error responses, failed requests and console errors. Watched only, nothing extra is sent to the site. URLs are kept
-- without their query strings. Null for steps from before this.
ALTER TABLE steps ADD COLUMN devtools jsonb;
