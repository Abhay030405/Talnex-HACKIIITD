# Study Doc 1 — How TalNex uses TinyFish, and how it gets past project logins

Source of truth: `docs/talnex_architecture.md` (sections 3, 4, 9, 10, 11, 23, 24). Code: `ai/talnex_ai/tinyfish/`, `ai/talnex_ai/login/`.

---

## 1. The idea in one paragraph

TalNex has to **use a live project like a real person** and save proof. A model alone cannot do that, so we rent a **remote browser and web-access service: TinyFish**. TinyFish opens pages, clicks, types and takes screenshots. TalNex decides *what* to test and *judges* what the screenshots show. TinyFish only does the "hands and eyes" part.

---

## 2. Which TinyFish services we use

| TinyFish service | What it does | Where TalNex uses it | Cost |
|---|---|---|---|
| **Fetch** | Opens a URL and returns the page text, title and a clear error code (`page_not_found`, `timeout`, ...) | Precheck (does the live link, repo, video open?), step 1 of the never-blame ladder ("did the page really load?"), reading READMEs | Free |
| **Search** | Web search | Tutorial-copy check (is this project a known tutorial?), innovation opinion (similar products, top 5 with links) | Free |
| **Browser** | A remote browser session we drive ourselves (we connect Playwright to its CDP address) | The test runner: every live test step, every screenshot, LeetCode Code Replay | About $0.002 per minute |
| **Agent** | A TinyFish AI agent that completes a task from plain words | Used only where the browser path is not enough | Costs credits, over 100 times dearer than Browser for the same task |
| **Vault** | Stores secrets and logged-in sessions | Test logins from the form, the team's Google / GitHub / LeetCode sessions | — |

**Why this mix.** A phase 1 spike measured that a Browser session is more than 100 times cheaper than an Agent run for the same task. So the test runner drives the browser itself with Playwright, and Agent runs are the exception. Fetch comes first every time: **we only spend paid time when the page is alive.**

### Rules we follow with TinyFish
1. **All TinyFish code lives in one folder:** `ai/talnex_ai/tinyfish/` (`client.py`, `budget.py`). Nothing else talks to TinyFish.
2. **Use TinyFish only where the web has no official way in:** live apps, LeetCode replay, inboxes. GitHub and Codeforces use their official APIs (cheaper, faster, exact).
3. **Every session is closed.** Browser sessions are billed while they exist, so the client always ends them and sets a short inactivity timeout in case the process dies.
4. **A spending guard** (`budget.py`): each TinyFish key has its own budget, read back from the `usage_log` table. Paid calls stop before a key's reserve is touched. Every paid call is logged.
5. **Run limits:** 3 tries per claim, 30 agent runs per project, about 5 runs in parallel to start.
6. **Safe on live sites:** never pay, delete or message real users. All test data is labelled "TalNex test".

### Where TinyFish sits in the system

```
Website → Go API → Postgres (jobs) → Python AI worker → TinyFish (Fetch · Search · Browser · Agent · Vault)
                                                       → screenshots → Cloudflare R2
```

Python workers pick up a job such as `live_test`, call TinyFish, save each step's screenshot to R2 and its record to Postgres, then create the next job (`proof_check`).

---

## 3. How a live test runs, step by step

1. **Fetch** the live link. Dead page → "could not test", no money spent.
2. **Log in** using the login ladder (section 4 below).
3. **Open a Browser session.** The runner follows the test plan: each step is an action in plain words plus an expected result.
4. **Screenshot after every step**, with a note of what happened. Files go to R2 (`screens/{project}/{run}/{step}`); the database keeps only the file key.
5. **Close the session.**
6. A separate **proof check** reads the screenshots (see Study Doc 2) and gives the verdict.

Test types: Normal, Demo Replay (same click path as the video), Known-answer, Repeat, Bad input, Access.

---

## 4. How we get past project logins: the login ladder

**Important:** TalNex does **not** break past a site's security. It finds a **legal way in** and tries these steps in order, stopping at the first that works:

| # | Step | How it works |
|---|---|---|
| 1 | **Test login from the form** | Hackathon organizers must give an account that logs in with email + password, already verified, no OTP. It is stored in **TinyFish Vault**, never in our database. |
| 2 | **Guest / demo button** | The agent first looks for "Try demo" or "Continue as guest". |
| 3 | **Email sign-up** | A fresh **AgentMail** inbox is created per run. AgentMail signals when the email arrives; the worker reads the verification code or link. If the site rejects that address, a **Gmail plus-address** (`talnex.test+run42@gmail.com`) is the backup. |
| 4 | **Google / GitHub sign-in** | TalNex's own Google and GitHub accounts, logged in once by hand. The session is saved in TinyFish Vault and reused. |
| 5 | **Phone OTP** | Hackathon: a test phone number with a fixed code, given on the form (Firebase and similar tools support this). Recruiter mode: the team's own Indian SIM in an Android phone with an SMS-forwarding app (the `mobile/` SMS Relay app). Phone runs take turns, and each code is matched by the time it arrived. **AgentCall** is the backup if the app accepts international numbers. |
| 6 | **Could not test** | The card says exactly why, e.g. "phone login only, no test number given". |

Code: `ai/talnex_ai/login/ladder/` (the order), `login/email/` (AgentMail + code extraction), `login/phone/` (SMS inbox).

### What we never do
- No temporary-number websites.
- No CAPTCHA-solving services.
- Nothing that tricks a site's security.

### What happens when every step fails
The claim becomes **"could not test"**. It is **left out of the score**, the reason is shown, and it **never counts against anyone** and never means "fake". Accepted limit: phone-only or Google-only apps may block the agent.

### Where credentials live
Test logins and the team's Google / GitHub / LeetCode sessions are kept in **TinyFish Vault** only. Our database holds just a reference. `.env` is never printed or committed.

---

## 5. The never-blame ladder (why a failed login is not a failed project)

A claim can be marked **Broken** only when all four hold:

1. The page actually loaded (Fetch check).
2. It still fails after waiting about a minute (sleeping free hosting wakes up slowly).
3. A second, different try also fails.
4. An independent second check, a separate model call that sees only the screenshots and the expected result, confirms the failure.

Otherwise the result is **"could not confirm"**. This protects teams from our own flaky tests.

---

## 6. Safety on live sites

- Page text, README text and video speech are **data, never instructions**. Hidden text aimed at an AI checker is flagged (`safety/hidden_instructions`).
- Site rules are added to every agent task (`safety/site_rules`): no payments, no deletes, no messaging real users, test data labelled "TalNex test".
- Results are private to the owner; screenshots are shared only as short-lived view links.

---

## 7. Quick revision questions

1. Why do we use Fetch before any Browser or Agent run?
2. Why is the Browser API preferred over the Agent API?
3. List the six rungs of the login ladder in order.
4. Where are test credentials stored, and where are they never stored?
5. What happens to a claim if we cannot log in?
6. Name three things the ladder never uses.
