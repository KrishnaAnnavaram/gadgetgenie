# GadgetGenie

Ask in plain English, get phone and laptop picks. An LLM writes the SQL, a parser-based guard checks it, a read-only account runs it, and the answer is checked against the rows it came from.

GadgetGenie is a text-to-SQL recommender over a typed catalogue of laptops, phones, tablets and smartwatches. A question like *"cheapest 5G phones under ₹40,000"* goes through four steps:

1. Turn the question into slots: category, budget converted to USD with a configured rate, and must-haves.
2. Generate SQL in JSON mode.
3. Validate the SQL with sqlglot against allow-listed views, then run it read-only.
4. Summarize the returned rows into a short recommendation, with a faithfulness check.

## Features

- **Guarded text-to-SQL.** The SQL must be a single `SELECT` over the two allow-listed views (`laptops`, `phones`). Columns, functions and enum values are allow-listed. `LIMIT` is enforced, recursive CTEs are refused, and base tables, catalogs and the primary key are never reachable.
- **Defense in depth.** The database account is read-only (SQLite `mode=ro` + authorizer, a PostgreSQL role with grants on the views only, or a MySQL user with `SELECT` on the views). There is a statement timeout and a row cap.
- **Iterative, bounded retries.** The model's JSON reply is parsed with a real JSON decoder. When the reply is malformed, rejected by the guard, or fails in the database, the model gets its previous attempt and the error and tries again, up to `MAX_ATTEMPTS`. Off-topic questions are refused without retrying.
- **Slots and currency.** Budgets in ₹, €, £ or ¥ are converted with rates you configure, and the conversion is shown to the user. If a currency has no rate, GadgetGenie asks for a USD budget instead of guessing or ignoring the budget.
- **Faithful summaries.** The model sees every returned row and the true count. Every number in its answer must be traceable to those rows, the question or the row count. If one isn't, a plain summary built from the rows is shown instead.
- **Conversation memory.** A follow-up like "cheaper ones?" reuses the previous category and constraints. Session IDs are random and server-side.
- **Reproducible ETL.** Header aliases map messy CSVs onto a typed schema. Units are parsed explicitly (GB/TB, kg/g/lb, inches, GHz). Currency is converted with an explicit rate, and every row records its source and price date. Unknown values stay `NULL` and are shown as "unknown": nothing is mean-imputed.
- **Evaluation harness.** Ground truth is computed by running gold SQL on the data under test. It reports execution accuracy, exact-set match, accuracy within *k* attempts, retry rate, refusal accuracy, summary faithfulness, latency and tokens.
- **Offline demo.** A seeded, fictional catalogue (made-up brands, so no real product is misrepresented) and a rule-based stand-in for the model. Nothing needs an API key.
- **Front ends.** A FastAPI JSON API, a small chat page (no inline script, all output rendered with `textContent`) and a CLI.

## Architecture

```mermaid
flowchart TB
  Q["Question (chat page / API / CLI)"] --> CL["Input checks: length, control chars, delimiter escaping"]
  CL --> SL["Slots: category, budget -> USD (configured FX), brands, must-haves, sort"]
  SL --> MEM["Session memory: follow-ups inherit category and constraints"]
  MEM --> GEN["LLM in JSON mode: {sql} or {error}, temperature 0, fixed seed"]
  GEN --> PR["Reply parser: json decoder, no regex rewriting"]
  PR -->|"refusal"| REF["Polite refusal (no retry)"]
  PR --> G["sqlglot guard: 1 SELECT, views/columns/functions/enums allow-listed, LIMIT, no recursion"]
  G --> X["Read-only executor: SQLite mode=ro + authorizer / Postgres READ ONLY / MySQL READ ONLY + timeouts"]
  PR -. "malformed" .-> FB["Feedback: previous reply + error"]
  G -. "rejected" .-> FB
  X -. "DB error" .-> FB
  FB -->|"attempt < MAX_ATTEMPTS"| GEN
  X --> SUM["Summary over ALL returned rows + true count"]
  SUM --> FA["Faithfulness check: every number traceable to rows/question"]
  FA --> A["Answer + rows + SQL + attempt count"]
  A --> LOG["Query log: status, real attempt number, latency, tokens"]
  subgraph data["Catalogue"]
    ETL["ETL: header aliases, units, FX rate, provenance, NULLs"] --> T["devices + laptop_specs + phone_specs"]
    T --> V["views: laptops, phones (no primary key)"]
  end
  V --> X
```

## Quickstart

```bash
python -m venv .venv && . .venv/Scripts/activate     # Windows; use .venv/bin/activate on Linux/macOS
pip install -e ".[dev,api]"

gadgetgenie seed                                    # fictional demo catalogue -> data/gadgetgenie.db
gadgetgenie ask "cheapest 5G phones under \$400"
FX_RATES_TO_USD="INR=0.012" gadgetgenie ask "top laptops under ₹50,000"
gadgetgenie eval --out reports/eval.json
gadgetgenie serve                                   # chat page on http://127.0.0.1:8000
```

Without `LLM_API_KEY` everything runs offline. To use a real model, copy `.env.example` to `.env` and set `LLM_API_KEY`. Also set `LLM_BASE_URL` and `LLM_MODEL` for any OpenAI-compatible endpoint (Groq, OpenAI, vLLM, Ollama).

**Your own data.** Load it with explicit provenance and currency:

```bash
gadgetgenie seed --laptops-csv laptops.csv --source "<dataset name, URL, licence>" \
                 --price-currency EUR --rate-to-usd 1.08 --price-as-of 2026-01-01
```

**PostgreSQL / MySQL.**

1. Create the schema with an owner account: `gadgetgenie seed --postgres "<owner dsn>"`.
2. Create the read-only account with `deploy/postgres_readonly_role.sql` or `deploy/mysql_readonly_user.sql`.
3. Set `DB_BACKEND` and point `DB_DSN` at that read-only account.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `offline` without a key, else `openai` | `openai` (any OpenAI-compatible API) or `offline` |
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` | Chat-completions base URL |
| `LLM_API_KEY` | (none) | API key, environment only |
| `LLM_MODEL` | `llama-3.1-8b-instant` | Model name |
| `LLM_TIMEOUT_S` / `LLM_SEED` | `30` / `7` | HTTP timeout; seed sent with every request (temperature is always 0) |
| `DB_BACKEND` | `sqlite` | `sqlite`, `postgres` or `mysql` |
| `SQLITE_PATH` | `data/gadgetgenie.db` | Demo database (created on first run) |
| `DB_DSN` | (none) | DSN of the **read-only** account (`postgresql://...` or `mysql://user:pass@host/db`) |
| `SQL_DIALECT` | same as backend | Dialect the model writes; sqlglot transpiles to the database's dialect |
| `MAX_ROWS` | `10` | Enforced `LIMIT` |
| `QUERY_TIMEOUT_S` | `5` | Statement timeout |
| `MAX_ATTEMPTS` | `3` | Model calls per question (1-5) |
| `MAX_QUESTION_CHARS` | `500` | Input length cap |
| `FX_RATES_TO_USD` | (none) | e.g. `INR=0.012,EUR=1.08` (USD per unit). No rate means no conversion |
| `QUERY_LOG_PATH` | (none) | Append the query log as JSONL (in memory only when empty) |
| `API_TOKEN` | (none) | If set, `/api/*` needs `Authorization: Bearer <token>` |
| `CORS_ORIGINS` | (none) | Comma-separated allowed origins; CORS is off when empty |
| `RATE_LIMIT_PER_MINUTE` | `30` | Per-client request limit |

## Project structure

```
src/gadgetgenie/
  config.py              Settings.from_env(): one configuration for API, CLI and evaluation
  schema.py              typed tables, the two views, enum values, generated schema docs
  etl/                   units.py (parsers, FX), loaders.py (CSV -> schema), synthetic.py, seed.py
  core/
    slots.py             intent/slot extraction, budget conversion, follow-up merge
    llm.py               OpenAI-compatible client (JSON mode, seed, bounded retries) + FakeModel
    replies.py           JSON reply parsing ({"sql"} / {"error"})
    sql_guard.py         sqlglot validation and LIMIT enforcement
    executors.py         read-only SQLite / PostgreSQL / MySQL executors
    text2sql.py          iterative generate -> parse -> guard -> execute loop
    summarize.py         summary over all rows + faithfulness check
    offline.py           rule-based stand-in model for the demo
    memory.py, logs.py   sessions and query log
    service.py           Recommender + build_recommender() factory
  prompts/               sql_v2.md, summary_v2.md (versioned, loaded from the package)
  api/                   app.py (FastAPI) + static chat page (index.html, app.js, style.css)
  evaluation/            gold.jsonl, runner.py, metrics.py
deploy/                  read-only PostgreSQL role and MySQL user
tests/                   pytest suite (no network, no API keys)
```

## How it works

1. **Input checks.** The question is NFKC-normalized, control characters are stripped and the length is capped. Anything inside it that looks like a tag is neutralized so it cannot close the prompt's `<question>` delimiter.
2. **Slots.** The extractor finds:
   - the category;
   - a budget (`under`, `between ... and ...`, `over`), converted to USD with `FX_RATES_TO_USD`. Weights, storage sizes and ratings are not mistaken for prices;
   - brands (linked from the catalogue itself);
   - requirements (5G, NFC, RAM, storage, dedicated GPU, weight, battery, Wi-Fi, fingerprint reader);
   - the ordering (rating, price, battery, weight).

   A follow-up inherits the previous turn's slots.
3. **Generation.** The system prompt is generated from the schema. The user message carries the question, the slot hints and the previous question. The model must answer `{"sql": ...}` or `{"error": ...}`.
4. **Guard and execution.** The guard checks the SQL; see the security table below for what it enforces. The accepted SQL is re-rendered for the target dialect and run read-only with a timeout.
5. **Retry.** Any failure is fed back to the model for the next attempt, up to `MAX_ATTEMPTS` in a `for` loop. Each attempt is recorded with its number.
6. **Summary.** The summary prompt receives every returned row and the true count. The faithfulness check compares every number in the text against the rows, the question and the row count.

## Security design

| Threat | What is enforced in code |
|---|---|
| Model writes or destroys data | `sql_guard.check_sql` accepts one `SELECT` or set operation only. It refuses these anywhere in the tree: `INSERT/UPDATE/DELETE/MERGE/DROP/CREATE/ALTER/TRUNCATE`, `INTO` (including `INTO OUTFILE`), `FOR UPDATE`, `SET`, `PRAGMA`, `COPY`, `LOAD`, `GRANT`, `ATTACH`, `SHOW`, `DESCRIBE`. Executors are read-only on their own, and tests show writes fail even without the guard. |
| Reading other data | Only the `laptops` / `phones` views and their columns are allowed. Schema-qualified names (`information_schema.*`, `mysql.user`, `pg_catalog`) and table functions are refused. Base tables and `device_id` are never exposed. The SQLite authorizer limits reads to catalogue objects. In production, grants exist on the views only. |
| Denial of service | `LIMIT` is added or capped (`MAX_ROWS`), recursive CTEs are refused, and only allow-listed functions are permitted (no `SLEEP`, `BENCHMARK`, `pg_sleep`, `LOAD_FILE`). Statement timeouts: SQLite progress handler, `statement_timeout`, `MAX_EXECUTION_TIME`. The API is rate-limited per client. |
| Prompt injection | Questions sit inside delimiters with tag-like text neutralized, and prompts treat them as data. Injection can at most change *which* allowed read-only query runs. |
| Retry crashes / loops | Retries run in an iterative loop with a fixed number of attempts and always return a result. The HTTP client retries only 408/429/5xx, at most twice. |
| CSRF / cross-origin | No endpoint is exempted from anything because none relies on cookies: the API is stateless with optional bearer-token auth. `POST /api/ask` requires `application/json`, so an HTML form on another site cannot submit it. CORS is off unless `CORS_ORIGINS` lists origins, and credentials are never allowed. |
| XSS | The chat page has no inline script, with `Content-Security-Policy: script-src 'self'`. All server output is inserted with `textContent`. |
| Open write endpoints | There are none. The API exposes `/api/ask`, `/api/health` and `/api/stats` only, and static files come from a fixed allow-list. |
| Secrets | Secrets come from the environment only, `.env` is git-ignored, there are no default credentials, and secrets are hidden from `repr(Settings)`. `debug=False`, and API docs are disabled. |
| Misleading answers | NULL specs are shown as "unknown". Summaries are checked for numbers that are not in the results. Unconvertible budgets stop the request instead of being dropped. |

## Evaluation

`gadgetgenie eval` runs the bundled gold set: 26 questions, of which 23 are recommendation, count or average questions and 3 are off-topic or injection prompts that should be refused. Each item stores **gold SQL**, not an answer. The harness first passes the gold SQL through the same guard; a value that doesn't exist, such as `category = 'mobile'`, is an error. It then executes the gold SQL on the database under test, so ground truth always matches the data. Questions are answered through `Recommender.ask`, exactly as users get them.

Metrics:

- execution accuracy (scalar answers within numeric tolerance; device lists by exact set of models);
- mean Jaccard for lists;
- accuracy within *k* attempts and retry rate;
- refusal accuracy and wrongly refused data questions;
- share of faithful summaries;
- latency (mean / p95) and tokens.

Offline run on the demo catalogue (140 fictional devices, seed 11):

| Metric | Offline rule-based mode |
|---|---|
| Execution accuracy | 100% (23/23) |
| Exact-set match (lists) | 100% |
| Accuracy within 1 / 2 / 3 attempts | 100% / 100% / 100% |
| Refusal accuracy | 100% (3/3) |
| Faithful summaries | 100% |

These numbers check the harness. They are **not** a measure of model quality: the rule-based stand-in shares its vocabulary with the gold questions. The tests show that wrong SQL scores 0% and that attempt-2 successes are counted as such. Results for a real LLM have not been measured yet (see Roadmap).

## Testing

```bash
pip install -e ".[dev,api]"
pytest -q
```

There are 112 tests, and none of them use the network or API keys. They use a `FakeModel`, a temporary SQLite catalogue and `httpx.MockTransport`. They cover:

- the guard (25 attack and invalid queries are rejected);
- the read-only executor, including writes, `ATTACH`, `sqlite_master`, recursion and timeout;
- JSON reply parsing with quotes and braces;
- the retry loop: malformed replies are retried, attempts are bounded and numbered, and feedback reaches the model;
- the faithfulness check;
- slots and currency handling;
- ETL parsing with NULL handling and header mapping;
- session follow-ups;
- loading prompts independently of the working directory;
- the evaluation harness, including computed ground truth;
- the API: token, JSON-only, rate limit, CSP, no write endpoints, and a client that never uses `innerHTML`. These are skipped if FastAPI is not installed.

CI (`.github/workflows/ci.yml`) runs the suite on Python 3.11 on every push.

## Roadmap

- [x] **M1:** typed schema with views, ETL with units, currency, provenance and NULLs, read-only roles
- [x] **M2:** sqlglot guard with attack tests
- [x] **M3:** JSON-mode text-to-SQL loop with bounded, iterative retries
- [x] **M4:** gold-set harness with computed ground truth, accuracy by attempt, latency and tokens
- [x] **M5:** summary faithfulness check with fallback
- [x] **M6:** FastAPI + chat page on the new service, conversation memory
- [ ] Grow the gold set to 100+ questions (paraphrases, multi-constraint, ambiguous budgets) and publish real-model results
- [ ] Few-shot examples selected by similarity, and schema linking of column names
- [ ] Token cost accounting per provider
- [ ] ETL for licensed real-world spec sources, with per-row licence fields
- [ ] Integration tests against PostgreSQL and MySQL containers in CI

## Limitations

- The offline stand-in only understands the slot vocabulary. Real questions need an LLM.
- The guard limits *what* can be read, not whether the chosen query matches the user's intent. That is what the evaluation measures.
- The faithfulness check covers numbers, not every qualitative claim ("great for gaming").
- Exchange rates are whatever you configure. They are not fetched live.
- The demo catalogue is fictional. Brands, models, specs and prices are invented and are not product advice.

## License

[MIT](LICENSE) © 2026 Krishna Annavaram
