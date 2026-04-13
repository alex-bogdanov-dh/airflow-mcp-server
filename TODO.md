# TODO — Wex/Sonnet Handoff

Actionable tasks to finish on the work laptop. Each item is self-contained.

## Priority 1: Get It Running

- [ ] **Clone and install on work laptop**
  ```bash
  git clone <repo-url> ~/IdeaProjects/airflow-mcp-server
  cd ~/IdeaProjects/airflow-mcp-server
  bash install.sh
  ```

- [ ] **Add MCP server to Wex's Claude Code settings**
  Follow the install.sh output or see README for the JSON snippet.
  Config goes to `~/.config/airflow-mcp/config.yaml`.

- [ ] **Get a session cookie for your first DDU**
  1. Log into Airflow in the browser (e.g. `airflow-eiga.datahub.deliveryhero.net`)
  2. Open DevTools → Application → Cookies
  3. Copy the full cookie string (all cookies, not just session)
  4. Paste into config.yaml under the DDU's `session_cookie` field

- [ ] **Validate connectivity**
  ```bash
  airflow-mcp validate
  ```

- [ ] **Test a basic command in Claude Code**
  Ask: "Check the standup for eiga" or "Show me failing dags on eiga"

## Priority 2: Fill in DDU Registry

The DDU registry in `src/airflow_mcp/ddu_registry.py` has placeholder entries.
Verify and complete these from the Data Hub directory:

- [ ] Verify all existing DDU codes are correct
- [ ] Verify URL pattern `airflow-{ddu}.datahub.deliveryhero.net` works for each
- [ ] Add any missing DDUs (check Data Hub Confluence or ask Valentina/Niha)
- [ ] Remove any DDUs that don't have Airflow instances
- [ ] Update descriptions to match actual team/region names

Known DDUs to verify:
```
eiga, paa, fpk, fpt, fps, fpm, fpp, fpb, fpl, fpc, fph, fpmm,
tlb, hun, mjm, gfg, efg, ped, dmh, dhp
```

## Priority 3: Auth Improvements

- [ ] **Test dh_cookie auth against a real DH instance**
  The cookie format might need adjustment. Test and fix if needed.

- [ ] **Request a GCP service account** from Vale/Wilson
  Ask for: Airflow Viewer role on the instances you need.
  Once you have the key, implement `DHServiceAccountAuthProvider` in `auth.py`.

- [ ] **Document cookie refresh workflow**
  How often do cookies expire? Add a note in README about refresh cadence.

## Priority 4: Internal Distribution

- [ ] **Push to GitHub** (private repo first)
  ```bash
  cd ~/IdeaProjects/airflow-mcp-server
  gh repo create airflow-mcp-server --private --source=. --push
  ```

- [ ] **Write a Confluence page**
  Title: "How to Debug Airflow DAGs in 10 Seconds from the Terminal"
  Frame it as a workflow guide, not a tool announcement.
  Include the before/after table from the README.

- [ ] **Demo it at team standup**
  Don't announce — just USE it during the standup.
  When someone asks about a failing DAG, diagnose it live.
  "Let me check..." → `diagnose_dag_run("the_dag", ddu="eiga")`

- [ ] **Share in the Data Hub Slack channel**
  After the live demo, post the Confluence link.
  Offer to help anyone set it up.

- [ ] **Key people to demo to** (from org map):
  - Valentina (Airflow platform lead, Berlin) — highest leverage
  - Niha (Data Hub team) — potential champion
  - Wilson (your manager) — visibility
  - Charlie (Valentina's lead) — if Valentina is enthusiastic

## Priority 5: Future Enhancements

- [ ] **Implement GCP service account auth** (`auth.py:DHServiceAccountAuthProvider`)
  Requires `google-auth` library. Gets a long-lived token, no cookie refresh needed.

- [ ] **Add `get_dag_source` tool** — read the DAG Python source code from Airflow API
  Endpoint: `GET /api/v2/dags/{dag_id}/source`

- [ ] **Add `search_dags` tool** — search DAGs by name pattern
  Endpoint: `GET /api/v2/dags?dag_id_pattern=...`

- [ ] **Add `get_import_errors` tool** — show DAGs that failed to parse
  Endpoint: `GET /api/v2/importErrors`

- [ ] **Slack webhook integration** — auto-post standup to a channel
  Instead of copy-paste, directly post via Slack incoming webhook.

- [ ] **Make it a PyPI package** — `pip install airflow-mcp-server`
  Would make distribution much easier. Needs proper versioning.

## Notes

- Config file (`config.yaml`) is in `.gitignore` — never commit it, it has credentials
- The `config.example.yaml` has DH DDUs commented out — safe to commit
- Usage tracking is opt-in via `AIRFLOW_MCP_TRACK_USAGE=1` env var
- All tests run without a live Airflow instance (mocked with respx)
