# TalNex MCP server

Lets an AI assistant (Claude Code, Claude Desktop, Gemini CLI or any MCP client) use TalNex: create hackathon events,
add teams, see what a check would cost, start it, watch it live, read proof cards and compare teams. Recruiters can add
candidates from a resume, confirm the projects found and read the proof report.

It talks **only to the TalNex Go API**, as one person, so every result stays private to its owner. It runs on your
computer over stdio; the assistant starts it.

## Install and build

Needs Node 20 or newer and a running TalNex API (`docker compose up` in the repository root).

```bash
cd mcp
npm install
npm run build        # writes dist/index.js
```

## Settings

All four are required. A missing one stops the server at start with its name.

| Setting | What it is |
|---|---|
| `TALNEX_API_URL` | Address of the Go API, e.g. `http://localhost:8080` |
| `AUTH_SECRET` | The same `AUTH_SECRET` the API uses (from the repository's `.env`) |
| `TALNEX_EMAIL` | The account to act as. Results are that person's only |
| `TALNEX_ROLE` | `organizer` (hackathons) or `recruiter` (candidates) |

> **Signing with `AUTH_SECRET` is for local and self-hosted use only.** The server signs the same short-lived token the
> website does, and whoever holds `AUTH_SECRET` can sign as any account. Use it on your own computer against your own
> stack; never put it in a shared config or a repository. Per-person API keys (needed before anyone else can connect,
> and for billing) are future work.

## Connect and test it yourself

In the snippets, replace `C:/Projects/Talnex-HACKIIITD` with where you cloned the repository, and
`<AUTH_SECRET from .env>` with the value from your `.env`.

### Claude Code

```bash
claude mcp add talnex \
  --env TALNEX_API_URL=http://localhost:8080 \
  --env AUTH_SECRET=<AUTH_SECRET from .env> \
  --env TALNEX_EMAIL=organizer@example.com \
  --env TALNEX_ROLE=organizer \
  -- node C:/Projects/Talnex-HACKIIITD/mcp/dist/index.js
```

Then type `/mcp` in Claude Code: `talnex` should show as connected with 19 tools. Add `--scope user` to use it in every
project. On PowerShell, put it on one line (or end lines with a backtick instead of `\`).

### Claude Desktop

Edit `%APPDATA%\Claude\claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "talnex": {
      "command": "node",
      "args": ["C:\\Projects\\Talnex-HACKIIITD\\mcp\\dist\\index.js"],
      "env": {
        "TALNEX_API_URL": "http://localhost:8080",
        "AUTH_SECRET": "<AUTH_SECRET from .env>",
        "TALNEX_EMAIL": "organizer@example.com",
        "TALNEX_ROLE": "organizer"
      }
    }
  }
}
```

Quit Claude Desktop completely (also from the tray) and open it again. The tools appear under the tools button.

### Gemini CLI

Add to `~/.gemini/settings.json` (Windows: `%USERPROFILE%\.gemini\settings.json`):

```json
{
  "mcpServers": {
    "talnex": {
      "command": "node",
      "args": ["C:/Projects/Talnex-HACKIIITD/mcp/dist/index.js"],
      "env": {
        "TALNEX_API_URL": "http://localhost:8080",
        "AUTH_SECRET": "<AUTH_SECRET from .env>",
        "TALNEX_EMAIL": "organizer@example.com",
        "TALNEX_ROLE": "organizer"
      }
    }
  }
}
```

Start `gemini` and type `/mcp` to see the server and its tools.

### Try it: an organizer's conversation

1. "Which TalNex account am I? List my events." (`who_am_i`, `list_events`)
2. "Create a fixed-problem event called Campus Hack, 23 Oct 2026 09:00 to 24 Oct 18:00 UTC, with criteria Core
   features (weight 3) and Ease of use (weight 1)." (`create_event`)
3. "Add team TinyTools with the live site https://talnex-honest.vercel.app." (`add_project`)
4. "What would checking every team cost?" (`run_event` without confirm: a preview and an estimate, nothing starts)
5. "Go ahead and start it." (`run_event` with `confirm: true`: this spends money, so the assistant should ask you first)
6. "Watch it live for a minute." (`watch_live`: stages, each claim's status, the latest actions and reasons)
7. "Show TinyTools' proof card." (`get_proof_card`)
8. "Which teams built each feature best?" (`compare_event`: up to three teams per feature, never one winner)

A recruiter's conversation: "Add a candidate from C:/resumes/cv.pdf" (`create_candidate`), "What did TalNex find?"
(`get_found_projects`), "What would checking them cost?" (`confirm_candidate` without confirm), "Start it"
(`confirm_candidate` with confirm), "How far along is it?" (`get_progress`), "Show the report" (`get_report`).

### Switching roles

One server acts as one person. To use both, add two servers with different names:
`talnex-organizer` (`TALNEX_ROLE=organizer`, the organizer's email) and `talnex-recruiter` (`TALNEX_ROLE=recruiter`,
the recruiter's email). Changing `TALNEX_EMAIL` changes whose events and candidates you see.

### Troubleshooting

| You see | Fix |
|---|---|
| `Cannot reach the TalNex API at http://localhost:8080` | Start the stack (`docker compose up`) and check `TALNEX_API_URL` and the port |
| `sign in required. ... Check AUTH_SECRET and TALNEX_EMAIL` | `AUTH_SECRET` must be exactly the API's value: no quotes, no spaces |
| `list_events is for organizer accounts, but this server is set up as a recruiter` | Set `TALNEX_ROLE` to the role the tool needs, or use the other server entry |
| `Not found (or it belongs to another account)` | The id is wrong or belongs to a different `TALNEX_EMAIL` |
| The server stops at once with `Missing setting: ...` | Add that setting to the `env` block |
| Server not starting on Windows | Run `npm run build` first; in JSON write paths with `\\` or `/`; if `node` is not found, use its full path, e.g. `C:\\Program Files\\nodejs\\node.exe`. Claude Desktop logs are in `%APPDATA%\Claude\logs\mcp-server-talnex.log` |

## Tools

| Tool | Who | What it does |
|---|---|---|
| `who_am_i` | anyone | The account this server acts as |
| `list_events` | organizer | Your hackathon events |
| `get_event` | organizer | One event and every team: status, TalNex score, coverage, flags, run time and cost (listed, never ranked) |
| `create_event` | organizer | Create an event (open theme or fixed problem with weighted criteria) |
| `add_project` | organizer | Add a team: live site, repository and/or demo video |
| `run_project` | organizer | Check one team. **Needs `confirm: true`**, otherwise a preview and estimate |
| `run_event` | organizer | Check every new team. **Needs `confirm: true`**, otherwise a preview and estimate |
| `get_proof_card` | organizer | A team's proof card: claims, verdicts, scores, proof, flags, AI opinion |
| `compare_event` | organizer | Up to three teams that built each feature best, and pairs whose code looks shared |
| `ask_project` | anyone | Ask how a feature works; answered from the code and the test results |
| `list_roles` | recruiter | Your hiring roles |
| `list_candidates` | recruiter | Your candidates |
| `create_candidate` | recruiter | Add a candidate from a resume PDF (under an auto-confirm role it **needs `confirm: true`**) |
| `get_found_projects` | recruiter | The projects and coding profiles read from the resume |
| `confirm_candidate` | recruiter | Confirm the projects and start the checks. **Needs `confirm: true`** |
| `get_progress` | recruiter | Where each stage of a candidate's check stands |
| `get_report` | recruiter | The candidate's proof report |
| `delete_candidate` | recruiter | Delete a candidate and their files for good. **Needs `confirm: true`** |
| `watch_live` | anyone | Watch a project, candidate or event for 1–120 seconds (default 20); saved events are replayed first |

Estimates come from earlier runs (about $0.10–0.15 and 5 minutes per project); they are not quotes.

## Safety

- Nothing that spends money or deletes starts without `confirm: true`.
- "Could not test" is never reported as broken, and a claim is only "broken" once its verdict arrives.
- No ranking and no single winner. Results are only ever the configured person's.
- Errors come back as plain words from the API, never a stack trace.

## Tests

```bash
npm test              # 182 tests against a fake API, no network
npm run coverage      # the same with a coverage report
npm run typecheck
npm run e2e           # builds, then runs the real server against the local stack (Node 22.6+); never passes confirm
```

The e2e check reads `AUTH_SECRET` from the repository's `.env` (never printed), acts as `edge-organizer@talnex.test`
and `edge-recruiter@talnex.test`, and creates a small event and a candidate from `testdata/resumes/test_resume.pdf`.
