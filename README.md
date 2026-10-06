<div align="center">

# GadgetGenie — Guarded Text-to-SQL Device Recommendations

**GadgetGenie is a device recommender for laptops, phones, tablets and smartwatches. It takes a plain-English question about devices through these steps to a short recommendation that the code checks against the result rows:**

`input check` → `slots and budget` → `generate SQL` → `SQL guard` → `run read-only` → `summary and faithfulness check`.

![Views](https://img.shields.io/badge/Views-2_(laptops_·_phones)-1F3864?style=for-the-badge)
![Back ends](https://img.shields.io/badge/Back_ends-3_(SQLite_·_PostgreSQL_·_MySQL)-2E5FD9?style=for-the-badge)
![Guard](https://img.shields.io/badge/Guard_attack_tests-25_refused-6E86E8?style=for-the-badge)
![Gold set](https://img.shields.io/badge/Gold_set-26_questions-4B6CB7?style=for-the-badge)
![Tests](https://img.shields.io/badge/Tests-112_passing-3DA35B?style=for-the-badge)
![Offline demo](https://img.shields.io/badge/Offline_demo-Yes-F5C542?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-A0399B?style=for-the-badge)

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![sqlglot](https://img.shields.io/badge/sqlglot-30.x-4479A1?style=flat-square)
![SQLite](https://img.shields.io/badge/SQLite-read--only-003B57?style=flat-square&logo=sqlite&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-optional-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-optional-4479A1?style=flat-square&logo=mysql&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-optional-009688?style=flat-square&logo=fastapi&logoColor=white)
![Docs](https://img.shields.io/badge/Docs-ASD--STE100-5D6D7E?style=flat-square)

**[Summary](#1-summary)** ·
**[Workflow](#4-the-end-to-end-workflow)** ·
**[Run it](#16-how-to-run-gadgetgenie)** ·
**[Configuration](#164-environment-variables)** ·
**[Known problems](#19-known-problems)** ·
**[Glossary](#21-glossary)**

</div>

> [!NOTE]
> This README uses ASD-STE100 Simplified Technical English. The writing rules and the project
> vocabulary are in [`docs/ste-style-guide.md`](docs/ste-style-guide.md). Each term in the
> [Glossary](#21-glossary) has only one meaning.

---

GadgetGenie changes a question about devices into one SQL query over a typed device catalogue. An LLM generates the SQL query in JSON mode. Code then parses the query with `sqlglot`, checks it against allow-lists and runs it on a read-only account. Each number in the final summary must come from the result rows, the question or the row count. If a number does not, the user sees a plain summary that the code makes from the rows.

This README is the **one location that explains all of GadgetGenie**. It gives these topics:

- the general design
- each component and its procedure, step by step
- the SQL guard rules and the query safety model
- the data map
- the runbook
- the validation results and the known problems

| If you are… | Read |
|---|---|
| A manager or reviewer | [1](#1-summary), [3](#3-design-rules), [4](#4-the-end-to-end-workflow), [18](#18-validation-results), [20](#20-key-points) |
| A developer who joins the project | All sections, in sequence. Keep [16](#16-how-to-run-gadgetgenie) and [19](#19-known-problems) open while you work |
| An operator who runs GadgetGenie | [16](#16-how-to-run-gadgetgenie), [14](#14-the-query-safety-model), then the section for the component that you use |

---

## Table of contents

1. 🧭 [Summary](#1-summary)
2. 🏗️ [How GadgetGenie is built](#2-how-gadgetgenie-is-built)
   - 2.1 [Components](#21-components)
   - 2.2 [System context](#22-system-context)
   - 2.3 [Repository layout](#23-repository-layout)
3. 🛡️ [Design rules](#3-design-rules)
4. 🔄 [The end-to-end workflow](#4-the-end-to-end-workflow)
   - 4.1 [Full flow](#41-full-flow)
   - 4.2 [The life cycle of one question](#42-the-life-cycle-of-one-question)
5. 🔵 [The catalogue and the ETL step](#5-the-catalogue-and-the-etl-step)
6. 🟢 [The input check and the session store](#6-the-input-check-and-the-session-store)
7. 🟣 [The slot extractor](#7-the-slot-extractor)
8. 🟡 [The text-to-SQL loop](#8-the-text-to-sql-loop)
9. 🟠 [The read-only executors](#9-the-read-only-executors)
10. 🔴 [The summarizer and the faithfulness check](#10-the-summarizer-and-the-faithfulness-check)
11. 🖥️ [The front ends](#11-the-front-ends)
12. 📝 [The query log](#12-the-query-log)
13. 🧪 [The evaluation harness](#13-the-evaluation-harness)
14. ⚖️ [The query safety model](#14-the-query-safety-model)
15. 🗂️ [Data and file map](#15-data-and-file-map)
16. ▶️ [How to run GadgetGenie](#16-how-to-run-gadgetgenie)
    - 16.1 [Prerequisites](#161-prerequisites) · 16.2 [Installation](#162-installation) · 16.3 [Run GadgetGenie](#163-run-gadgetgenie) · 16.4 [Environment variables](#164-environment-variables)
17. 🧩 [How to extend GadgetGenie](#17-how-to-extend-gadgetgenie)
18. ✅ [Validation results](#18-validation-results)
19. ⚠️ [Known problems](#19-known-problems)
20. 📌 [Key points](#20-key-points)
21. 📖 [Glossary](#21-glossary)
22. 📄 [License](#22-license)

---

## 1. Summary

**The problem.** An LLM can generate SQL from a question about devices. But generated SQL is not safe or correct by default, and an LLM summary can contain numbers that are not in the data. These are the difficult questions:

- How do you stop SQL that writes data, reads other tables or runs for a long time?
- How do you use a budget in rupees, euros or pounds when the catalogue prices are in US dollars?
- How do you answer a follow-up question such as "cheaper ones?"
- How do you stop a summary that gives a price or a spec that is not in the result rows?
- How do you measure accuracy when the catalogue changes?

GadgetGenie gives each of these questions its own component. The SQL guard and the read-only executors stop unsafe SQL. The faithfulness check stops summaries with invented numbers.

| Item | Value |
|---|---|
| Input | One question about devices in plain English, from the chat page, the HTTP API or the CLI |
| Output | A summary, the result rows, the SQL query that ran, the attempt count, notes and a status |
| Components | **10**: ETL step, input check, slot extractor, text-to-SQL loop, SQL guard, executors, summarizer, front ends, query log, evaluation harness |
| Catalogue | 4 device categories in 3 base tables. The LLM sees only the 2 views `laptops` and `phones` |
| Providers | Any OpenAI-compatible chat API (default base URL: Groq) |
| Offline mode | All components run with no key and no network: SQLite, the synthetic catalogue and the offline LLM |
| Safety | The SQL guard (`sqlglot`) and read-only executors for SQLite, PostgreSQL and MySQL |
| Tests | **112** unit tests (`pytest`), no network and no API key |

```mermaid
flowchart LR
    IN["Question"] --> A["Input check"] --> B["Slots and budget in USD"] --> C["LLM generates SQL"] --> D["SQL guard"] --> E["Read-only executor"] --> F["Summary and faithfulness check"] --> OUT["Answer with rows and SQL"]
```

---

## 2. How GadgetGenie is built

### 2.1 Components

| Component | Module | Purpose |
|---|---|---|
| Configuration | `src/gadgetgenie/config.py` | Reads all settings from environment variables and `.env` |
| Catalogue schema | `src/gadgetgenie/schema.py` | DDL of 3 base tables and 2 views, view columns, enum values, prompt text |
| ETL step | `src/gadgetgenie/etl/` | Unit parsers, CSV loaders, synthetic catalogue, SQLite and PostgreSQL loaders |
| Recommender service | `src/gadgetgenie/core/service.py` | `Recommender`, the input check and the one factory `build_recommender()` |
| Session store | `src/gadgetgenie/core/memory.py` | The last turn of each session, with random session IDs |
| Slot extractor | `src/gadgetgenie/core/slots.py` | Category, budget in USD, brands, requirements, sort order, follow-up merge |
| LLM clients | `src/gadgetgenie/core/llm.py`, `core/offline.py` | OpenAI-compatible client, offline LLM, `FakeModel` for tests |
| Prompts | `src/gadgetgenie/core/prompts.py`, `prompts/` | `sql_v2.md` and `summary_v2.md`, loaded from the package |
| Reply parser | `src/gadgetgenie/core/replies.py` | Reads `{"sql": ...}` or `{"error": ...}` from the reply |
| Text-to-SQL loop | `src/gadgetgenie/core/text2sql.py` | Generate, parse, guard and run, with a fixed number of attempts |
| SQL guard | `src/gadgetgenie/core/sql_guard.py` | Parses and checks each SQL query, adds or reduces the `LIMIT` |
| Executors | `src/gadgetgenie/core/executors.py` | Read-only SQLite, PostgreSQL and MySQL access |
| Summarizer | `src/gadgetgenie/core/summarize.py` | Summary from all rows and the faithfulness check |
| Query log | `src/gadgetgenie/core/logs.py` | One record for each question, optional JSONL file |
| Front ends | `cli.py`, `api/app.py`, `api/static/` | CLI, FastAPI HTTP API and chat page |
| Evaluation harness | `src/gadgetgenie/evaluation/` | Gold set, ground truth, metrics and report |

### 2.2 System context

```mermaid
flowchart TB
    U["User"] --> FE["Chat page, HTTP API or CLI"]
    FE --> APP["GadgetGenie recommender"]
    APP --> LLM["LLM: OpenAI-compatible API (optional) or offline LLM"]
    APP --> DB["SQLite, PostgreSQL or MySQL (read-only account, views only)"]
    APP --> LOG["Query log (memory, optional JSONL file)"]
    OWN["Operator with owner account"] --> SEED["gadgetgenie seed"]
    CSV["Laptop or phone CSV with data source and exchange rate"] --> SEED
    SEED --> DB
```

### 2.3 Repository layout

```
gadgetgenie/
├── .github/workflows/ci.yml        CI: install ".[dev,api]" and run pytest on Python 3.11
├── deploy/
│   ├── postgres_readonly_role.sql  Read-only PostgreSQL role with SELECT on the 2 views
│   └── mysql_readonly_user.sql     Read-only MySQL user with SELECT on the 2 views
├── docs/ste-style-guide.md         Writing rules and project vocabulary for this README
├── src/gadgetgenie/
│   ├── config.py                   Settings.from_env(), Settings.check(), parse_rates()
│   ├── schema.py                   DDL, VIEWS, enum values, schema_doc()
│   ├── cli.py                      gadgetgenie seed | ask | eval | serve
│   ├── etl/                        units, loaders, synthetic, seed
│   ├── core/                       service, slots, llm, offline, prompts, replies,
│   │                               text2sql, sql_guard, executors, summarize, memory, logs
│   ├── prompts/                    sql_v2.md, summary_v2.md
│   ├── api/                        app.py and static/ (index.html, app.js, style.css)
│   └── evaluation/                 gold.jsonl, runner.py, metrics.py
├── tests/                          9 test files and conftest.py, 112 tests
├── .env.example                    All environment variable names, no values
├── pyproject.toml                  Package, extras, pytest and ruff settings
└── LICENSE                         MIT
```

---

## 3. Design rules

### 3.1 The code enforces safety, not the prompt
The prompt tells the LLM to treat the question as data. A prompt cannot stop prompt injection. Thus `sql_guard.check_sql()` parses each SQL query and rejects it if it breaks an allow-list. The executors then open each connection read-only, so a query that passes the SQL guard still cannot write.

### 3.2 The LLM sees views, not tables
The LLM can query only the views `laptops` and `phones`. The base tables and the key `device_id` are not in the views. The SQL guard rejects all other table names, and the read-only accounts have grants on the views only.

### 3.3 Each number in a summary comes from the data
The summarizer gives the LLM all result rows and the true row count. The faithfulness check then compares each number in the summary with the rows, the question and the row count. If one number has no source, the user gets the plain summary.

### 3.4 No guessed values
An unknown spec stays `NULL` and shows as "unknown". The ETL step does not fill values with averages. A budget in a currency without a configured exchange rate stops the request with status `needs_input`.

### 3.5 Bounded loops only
The text-to-SQL loop makes a maximum of `MAX_ATTEMPTS` LLM calls in a plain `for` loop. The HTTP client makes a maximum of 3 requests for each call. A refusal stops the loop at once.

### 3.6 One factory for all front ends
The CLI, the HTTP API and the evaluation harness all call `build_recommender()`. The harness calls `Recommender.ask()` in the same way as a user. Thus the evaluation measures the same service that users get.

---

## 4. The end-to-end workflow

### 4.1 Full flow

```mermaid
flowchart TB
    Q["Question (chat page, HTTP API or CLI)"] --> CL["Input check: NFKC, control characters, length limit"]
    CL --> SL["Slot extractor: category, budget in USD, brands, requirements, sort order"]
    SL -->|"no exchange rate"| NI["Status needs_input: ask for a USD budget"]
    SL --> MEM["Session store: a follow-up gets the earlier slots"]
    MEM --> GEN["LLM in JSON mode: sql or error, temperature 0, fixed seed"]
    GEN --> PR["Reply parser: JSON decoder"]
    PR -->|"error key"| REF["Status refused (no retry)"]
    PR --> G["SQL guard: one SELECT, views, columns, functions, enum values, LIMIT"]
    G --> X["Read-only executor: SQLite, PostgreSQL or MySQL, with time limit"]
    PR -.->|"bad reply"| FB["Feedback: previous reply and error"]
    G -.->|"rejected"| FB
    X -.->|"database error"| FB
    FB -->|"attempt < MAX_ATTEMPTS"| GEN
    X --> SUM["Summarizer: all rows and the true row count"]
    SUM --> FA["Faithfulness check: each number has a source"]
    FA --> A["Answer: summary, rows, SQL, attempt count, notes"]
    A --> LOG["Query log: status, attempts, time, tokens"]
    subgraph data["Catalogue"]
        ETL["ETL: header aliases, units, exchange rate, data source, NULL"] --> T["devices, laptop_specs, phone_specs"]
        T --> V["Views laptops and phones (no device_id)"]
    end
    V --> X
```

### 4.2 The life cycle of one question

1. A front end sends the question and an optional session ID to `Recommender.ask()`.
2. If the session ID is not 32 lower-case hexadecimal characters, the service makes a new random ID.
3. The input check normalizes the text. If the text is empty or too long, the status is `invalid`.
4. The slot extractor finds the category, the budget, the brands and the requirements.
5. If the budget has no exchange rate, the status is `needs_input` and the request stops.
6. If the question is a follow-up, the session store gives the earlier slots and the earlier question.
7. The text-to-SQL loop generates SQL, parses the reply, checks the SQL and runs it read-only.
8. If a step fails, the loop sends the reply and the error to the LLM and tries again.
9. The summarizer generates a summary from all rows. The faithfulness check compares each number with its sources.
10. The service keeps the turn in the session store and adds one record to the query log.
11. The front end shows the summary, the notes, the rows and the SQL with the attempt count.

---

## 5. The catalogue and the ETL step

**Purpose.** Keep one typed catalogue with explicit units, a data source and a price date for each device.

| Input | Output |
|---|---|
| A random seed (synthetic catalogue), or laptop and phone CSV files with `--source`, currency and exchange rate | SQLite file (default `data/gadgetgenie.db`) or PostgreSQL tables and views |

**The catalogue schema** (`schema.py`)

| Object | Kind | Contents |
|---|---|---|
| `devices` | Base table | `device_id`, `category`, `brand`, `model` (unique), `release_year`, `price_usd`, `price_as_of`, `rating` (0 to 5), `source` |
| `laptop_specs` | Base table | CPU, RAM, SSD, HDD, GPU, screen, weight, battery hours, Wi-Fi standard, fingerprint reader |
| `phone_specs` | Base table | OS, chipset, RAM, storage, display, battery mAh, camera, 5G, NFC, headphone jack, weight |
| `laptops` | View, 21 columns | Laptops with their specs. No `device_id` |
| `phones` | View, 18 columns | Phones, tablets and smartwatches with their specs and `category`. No `device_id` |

Enum columns: `category` (`phone`, `tablet`, `smartwatch`), `cpu_brand` (4 values), `gpu_brand` (5 values) and `wifi_standard` (`Wi-Fi 5`, `Wi-Fi 6`, `Wi-Fi 6E`, `Wi-Fi 7`).

**Procedure**

1. Run `gadgetgenie seed`. The command reads `Settings.from_env()`.
2. If you give `--laptops-csv` or `--phones-csv`, you must also give `--source`. Otherwise the command stops.
3. `load_laptops()` and `load_phones()` find each column through a list of header aliases.
4. If a required column (`brand` or `model`) is not there, the loader raises `SchemaMismatchError`.
5. Each value goes through a unit parser. A value that the parser cannot read becomes `NULL`, and the report counts it.
6. The loader converts each price to USD with `--rate-to-usd`. If the currency is not USD and no rate is given, the loader stops.
7. Without CSV files, `generate()` makes the synthetic catalogue (random seed 11).
8. `write_sqlite()` deletes the old file, applies the DDL and inserts the devices. With `--postgres OWNER_DSN`, `write_postgres()` does this on PostgreSQL.

**Unit parsers** (`etl/units.py`)

| Parser | Example |
|---|---|
| `size_gb()` | `"1TB"` → `1000`, `"512 MB"` → `1` |
| `storage_split()` | `"256GB SSD + 1TB HDD"` → SSD `256`, HDD `1000` |
| `weight_kg()` | `"3.5 lbs"` → `1.588`, `"1500 g"` → `1.5` |
| `inches()` | `'15.6"'` → `15.6` |
| `to_flag()` | `yes`, `true`, `1` → `1`. `no`, `false`, `0` → `0`. Other text → `NULL` |
| `to_float()` | `n/a`, `unknown`, `-` → `NULL` |

**Rules**

- The synthetic catalogue has 140 fictional devices: 60 laptops, 50 phones, 15 tablets and 15 smartwatches.
- The synthetic brands are invented. About 8% of the optional specs, 5% of the prices and 10% of the ratings are `NULL` on purpose.
- If two devices have the same `model`, the seed step keeps the first one.
- Seed with an owner account. The application must connect with a read-only account.

---

## 6. The input check and the session store

**Purpose.** Reject bad input before it reaches the LLM, and keep the last turn of each session.

| Input | Output |
|---|---|
| Raw question text, optional session ID | Clean question text and a valid session ID, or an answer with status `invalid` |

**Procedure**

1. `Recommender.clean()` applies Unicode NFKC normalization.
2. It replaces control characters with spaces and removes outer spaces.
3. If the text is empty or has more than `MAX_QUESTION_CHARS` characters, the status is `invalid`.
4. `prompts.tag()` puts user text in tags such as `<question>`. It replaces each `<` before a letter, `/`, `!` or `?` with `‹`.
5. Thus user text cannot close a tag. Comparison text such as `<=` stays the same.

**Session rules** (`core/memory.py`)

- A session ID is `secrets.token_hex(16)`: 32 lower-case hexadecimal characters. The server makes it.
- The service replaces a client session ID that does not have this format.
- `Sessions` keeps only the last turn (question, slots, answer) of each session.
- The store keeps a maximum of 2,000 sessions. The least recently used session goes first.
- The store is in the process memory. A restart deletes all sessions.

---

## 7. The slot extractor

**Purpose.** Change the question into explicit slots, and give them to the LLM as hints. Convert each budget to US dollars with a configured exchange rate.

| Input | Output |
|---|---|
| Clean question, `FX_RATES_TO_USD`, brand names from the catalogue, earlier slots | `Slots` with hints text, a budget note and problems |

**Slots**

| Slot | How the extractor finds it |
|---|---|
| `category` | Words such as laptop, notebook, phone, mobile, tablet, iPad, watch, wearable |
| `intent` | `count` for "how many", "number of", "count". `average_price` for "average" or "mean" with "price". Else `recommend` |
| `max_price_usd`, `min_price_usd` | "under", "below", "up to", "within", "over", "at least", "between X and Y" with an amount |
| `brands` | Brand names from the catalogue (`SELECT DISTINCT brand`) that the question contains |
| Requirements | RAM, storage, 5G, NFC, dedicated GPU or gaming, fingerprint, weight in kg, battery hours, Wi-Fi standard |
| `sort` | `price` (cheap, budget, affordable), `battery`, `weight` (light, portable) or `rating` (default) |

**Budget procedure**

1. The extractor finds each amount after a budget word.
2. If a unit such as `GB`, `kg`, `hours`, `mAh`, `inch`, `MP`, `GHz` or `stars` follows the amount, it is not a price.
3. If an amount has no currency and is less than 50, it is not a price. For example, "rating above 4".
4. A `k` after a number multiplies it by 1,000.
5. The currency comes from a sign (`$`, `₹`, `€`, `£`, `¥`) or a word (`rupees`, `euros`, `pounds`, `yen`, …). The default is USD.
6. `to_usd()` converts the amount with the rate from `FX_RATES_TO_USD`. The answer gets a note that shows the conversion.
7. If the currency has no rate, the extractor adds a problem. The service then returns status `needs_input`.

**Follow-up rules** (`merge()`)

- A follow-up gets the earlier category, budget, brands and limits that the new question does not give.
- The requirement flags (5G, NFC, dedicated GPU, fingerprint) of the two turns add together.
- An off-topic question that does not start like a follow-up ("and", "what about", "cheaper", "only", …) gets no earlier slots.

---

## 8. The text-to-SQL loop

**Purpose.** Get one valid SQL query from the LLM and run it read-only, with a fixed number of attempts.

| Input | Output |
|---|---|
| Clean question, slots, earlier question | `SQLOutcome`: status (`ok`, `refused`, `failed`, `model_error`), SQL query, rows, attempts, tokens, time |

**Procedure**

1. `TextToSQL` makes the system prompt from `prompts/sql_v2.md`, the dialect, the view columns and `MAX_ROWS`.
2. The user message has the `<question>`, the `<hints>` from the slots and the `<previous_question>`.
3. The loop calls the LLM in JSON mode (`response_format` `json_object`, temperature 0, `LLM_SEED`).
4. `parse_reply()` removes `<think>` blocks and code fences. It decodes JSON objects with a real JSON decoder.
5. If the reply has an `error` key, the status is `refused` and the loop stops without a retry.
6. If the reply has an `sql` key, `check_sql()` checks the SQL query (see [14](#14-the-query-safety-model)).
7. The executor runs the SQL query that the SQL guard generated again from the checked syntax tree.
8. If step 4, 6 or 7 fails, the next user message gets the previous reply (first 1,500 characters) and the error.
9. The loop stops after `MAX_ATTEMPTS` attempts with status `failed`. An LLM transport error gives status `model_error` at once.

**Rules**

- Each attempt has its real number, its reply, its SQL query and its error.
- The offline LLM makes SQL from the slots and the hints. It refuses a question without a category.
- The prompt asks the LLM to put `NULL` values last when it sorts.

---

## 9. The read-only executors

**Purpose.** Run one checked SQL query on a read-only connection with a row limit and a time limit.

| Input | Output |
|---|---|
| Checked SQL query, `MAX_ROWS` | `Rows`: columns, rows, `truncated` flag |

| Executor | Read-only controls | Time limit |
|---|---|---|
| `SQLiteExecutor` | URI `mode=ro`, `PRAGMA query_only = 1`, an authorizer that permits only `SELECT`, `READ` and functions. Reads only of the 3 base tables and the 2 views. It denies `load_extension`, `readfile`, `writefile` and recursive CTEs | Progress handler stops the query after `QUERY_TIMEOUT_S` |
| `PostgresExecutor` | Session `read_only = True`, a role with `SELECT` on the 2 views only, rollback after each query | `SET LOCAL statement_timeout` |
| `MySQLExecutor` | `SET SESSION TRANSACTION READ ONLY`, `START TRANSACTION READ ONLY`, a user with `SELECT` on the 2 views only, rollback | `MAX_EXECUTION_TIME` and a socket read time limit |

**Rules**

- Each executor reads a maximum of `MAX_ROWS + 1` rows to set the `truncated` flag.
- An executor error goes back into the text-to-SQL loop as feedback.
- `Rows.records()` changes `Decimal`, bytes and dates to plain JSON values.
- The MySQL DSN has the form `mysql://user:password@host:3306/database`.

---

## 10. The summarizer and the faithfulness check

**Purpose.** Make a short recommendation from the result rows, and make sure that it does not invent numbers.

| Input | Output |
|---|---|
| Clean question, `Rows` | `Summary`: text, `faithful` flag, unsupported numbers, a flag for the plain summary |

**Procedure**

1. The summarizer makes the system prompt from `prompts/summary_v2.md` with the true row count.
2. If the executor cut the rows, the prompt tells the LLM that more rows exist.
3. The LLM gets all result rows as JSON in `<rows>` tags.
4. If the LLM call fails or gives empty text, the answer is the plain summary.
5. The faithfulness check finds each number in the summary.
6. It ignores tokens such as `5G`, `Wi-Fi 6E`, `USB-C 3.2` and ordinals such as `3rd`.
7. A number is supported if it matches a row value, a number in the question or a number in a text cell.
8. An integer from 0 to the row count is also supported.
9. The check accepts format variants, for example `799.99`, `800` and `799.990`.
10. If one number is not supported, the answer is the plain summary and `faithful` is `false`.

**Rules**

- The plain summary (`plain_summary()`) gives the first 5 devices with price and rating, then "and N more".
- A `NULL` value shows as "unknown" in the plain summary, the CLI and the chat page.
- The check covers numbers only. It does not check names or claims such as "great for gaming".

---

## 11. The front ends

**Purpose.** Give the same recommender to a terminal user, an HTTP client and a browser user.

**CLI commands** (`gadgetgenie`, from `cli.py`)

| Command | Options | Result |
|---|---|---|
| `gadgetgenie seed` | `--seed 11`, `--sqlite PATH`, `--postgres OWNER_DSN`, `--laptops-csv PATH`, `--phones-csv PATH`, `--source TEXT`, `--price-currency USD`, `--rate-to-usd RATE`, `--price-as-of YYYY-MM-DD` | Creates the catalogue (see [5](#5-the-catalogue-and-the-etl-step)) |
| `gadgetgenie ask "QUESTION"` | `--json` | Prints the summary, the notes, the SQL query with the attempt count and the rows, or the full JSON answer |
| `gadgetgenie eval` | `--gold PATH`, `--out PATH` | Prints the evaluation report and writes the full JSON report |
| `gadgetgenie serve` | `--host 127.0.0.1`, `--port 8000` | Starts the HTTP API and the chat page with `uvicorn`. Needs the `api` extra |
| `gadgetgenie --version` | None | Prints `gadgetgenie 0.1.0` |

**HTTP API endpoints** (`api/app.py`)

| Endpoint | Token and rate limit | Response |
|---|---|---|
| `GET /` | No | The chat page (`index.html`) |
| `GET /static/{name}` | No | Only `app.js` and `style.css`. All other names get `404` |
| `GET /api/health` | No | `{"status": "ok"}` |
| `POST /api/ask` | Yes | The answer object below |
| `GET /api/stats` | Yes | Query log statistics (see [12](#12-the-query-log)) |

The `POST /api/ask` body is `{"question": "...", "session_id": "..."}`. The `session_id` is optional, with a maximum of 64 characters. The answer has these fields: `session_id`, `status`, `text`, `sql`, `columns`, `rows`, `truncated`, `attempts`, `faithful`, `notes`.

| Answer status | Meaning |
|---|---|
| `ok` | The SQL query ran. The answer has a summary and rows |
| `refused` | The LLM refused an off-topic question |
| `failed` | No valid SQL query after `MAX_ATTEMPTS` attempts |
| `model_error` | The LLM API is not available |
| `invalid` | The question is empty or too long |
| `needs_input` | The budget currency has no exchange rate |

| HTTP status | Cause |
|---|---|
| `401` | `API_TOKEN` is set and the `Authorization: Bearer <token>` header is absent or wrong |
| `415` or `422` | The body is not `application/json` |
| `422` | The question is empty or has more than `MAX_QUESTION_CHARS` characters, or `session_id` is too long |
| `429` | The client sent more than `RATE_LIMIT_PER_MINUTE` requests in the last 60 seconds |

**Security headers and settings**

- Each response has `Content-Security-Policy` with `default-src 'self'`, `script-src 'self'` and `frame-ancestors 'none'`.
- Each response also has `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`.
- The app runs with `debug=False`. The `/docs` and `/redoc` pages are off.
- CORS is off if `CORS_ORIGINS` is empty. CORS never allows credentials.

**Chat page** (`api/static/`)

- The page has no inline script. `app.js` inserts all server text with `textContent`, never as HTML.
- The page keeps the session ID in `sessionStorage` (key `gg-session`).
- Each answer shows the summary, the notes, a table of rows and the SQL query with the attempt count.

---

## 12. The query log

**Purpose.** Keep one record for each question with the real attempt count, the status and the time.

| Input | Output |
|---|---|
| The question, the `SQLOutcome` and the summary result | `LogRecord` in memory, and one JSON line in `QUERY_LOG_PATH` if set |

**Rules**

- A record has `question`, `status`, `sql`, `attempts`, `solved_at`, `faithful`, `seconds`, `tokens`, `errors` and `ts`.
- The memory buffer keeps the last 1,000 records.
- `GET /api/stats` gives `questions`, `by_status`, `solved_at_attempt`, `retry_rate` and `unfaithful_answers`.
- Answers with status `invalid` or `needs_input` do not go into the log.

---

## 13. The evaluation harness

**Purpose.** Measure the end-to-end accuracy, the attempts, the refusals, the faithfulness and the time on a gold set. The ground truth comes from the data.

| Input | Output |
|---|---|
| The recommender from `build_recommender()`, the gold set (bundled or `--gold PATH`) | A report with metrics and one result for each item |

**Procedure**

1. `load_gold()` reads the JSONL gold set. It rejects repeated IDs, unknown `compare` modes and items without `gold_sql` or `expect_refusal`.
2. `validate_gold()` sends each gold SQL query through the SQL guard. One rejected gold query stops the run.
3. For each item, the harness calls `Recommender.ask()` with a new session, as a user does.
4. A refusal item is correct if the status is `refused`.
5. For a data item with status `ok`, the harness runs the gold SQL query through the SQL guard and the executor.
6. For `"compare": "scalar"`, the item is correct if the gold value is in the single predicted row.
7. For `"compare": "set"`, the item is correct if the set of `model` values is the same. The harness also computes the Jaccard index.
8. `summarize()` computes the metrics. `format_report()` prints them, and `--out` writes the JSON report.

**Metrics**

| Metric | Meaning |
|---|---|
| `execution_accuracy` | Share of data items that are correct |
| `exact_set_match`, `mean_jaccard` | Set items only: exact match and mean Jaccard index of the `model` sets |
| `accuracy_within_attempts` | Share of data items that are correct within `k` attempts, for `k` = 1 to `MAX_ATTEMPTS` |
| `retry_rate` | Share of items with more than one attempt |
| `refusal_accuracy`, `wrong_refusals` | Refusal items with status `refused`, and data items that the LLM refused |
| `faithful_summaries` | Share of data items with `faithful = true` |
| `latency_mean_s`, `latency_p95_s`, `tokens_total` | Time and token use |

**The bundled gold set** (`evaluation/gold.jsonl`): 26 items. 12 items are about laptops and 11 items are about phones, tablets and smartwatches. 3 items are off-topic or injection prompts that the LLM must refuse. Of the 23 data items, 8 use `scalar` and 15 use `set`.

---

## 14. The query safety model

The code enforces each rule in this section. Prompt injection can change which allowed read-only query runs, but it cannot widen what the query can read.

**SQL guard** (`core/sql_guard.py`, checks in this sequence)

| # | Rule | Detail |
|---|---|---|
| 1 | Size and parse | A maximum of 3,000 characters. `sqlglot` must parse the text in `SQL_DIALECT`. Exactly one statement |
| 2 | Statement type | `SELECT`, or `UNION`, `INTERSECT` or `EXCEPT` of `SELECT` statements |
| 2 | Banned nodes | 26 node types anywhere in the tree: DML, DDL, `INTO` (also `INTO OUTFILE`), `FOR UPDATE`, `SET`, `PRAGMA`, `COPY`, `LOAD DATA`, `GRANT`, `ATTACH`, `SHOW`, `DESCRIBE` and more |
| 2 | Recursion | No recursive CTE |
| 3 | Tables | Only `laptops`, `phones` or a CTE of the same query. No qualified name such as `information_schema.tables` or `mysql.user`. No table function |
| 4 | Columns | Each column must exist in an allowed view or be an alias of the query. No `t.*`. `*` only in `COUNT(*)` |
| 5 | Functions | 33 allowed functions (aggregates, math, `CAST`, `CASE`, text, window ranks). All others are rejected, for example `SLEEP`, `BENCHMARK`, `LOAD_FILE`, `pg_sleep` |
| 6 | Enum values | A string compared with `category`, `cpu_brand`, `gpu_brand` or `wifi_standard` by `=`, `<>` or `IN` must be a valid value |
| 7 | `LIMIT` | Added if absent. Reduced to `MAX_ROWS`. Must be an integer literal of at least 1 |
| Output | Dialect | `sqlglot` generates the SQL again from the checked tree, without comments, in the executor dialect |

**Limits**

| Limit | Value | Variable |
|---|---|---|
| Rows for each query | 10 (range 1 to 100) | `MAX_ROWS` |
| LLM calls for each question | 3 (range 1 to 5) | `MAX_ATTEMPTS` |
| Time for each query | 5 s | `QUERY_TIMEOUT_S` |
| Question length | 500 characters | `MAX_QUESTION_CHARS` |
| API requests for each client | 30 in 60 seconds | `RATE_LIMIT_PER_MINUTE` |
| HTTP requests for each LLM call | 3 (2 retries for transport errors and status 408, 429, 500, 502, 503, 504, after 1.5 s and 3 s) | Code |
| HTTP time for each LLM request | 30 s | `LLM_TIMEOUT_S` |
| SQL text | 3,000 characters | Code |
| Sessions | 2,000 | Code |
| Query log records in memory | 1,000 | Code |

**Accounts and secrets**

- `deploy/postgres_readonly_role.sql` makes the role `gadgetgenie_reader` with `SELECT` on `laptops` and `phones` only, `default_transaction_read_only = on` and `statement_timeout = '5s'`.
- `deploy/mysql_readonly_user.sql` makes the user `gadgetgenie_reader` with `SELECT` on the 2 views and `MAX_QUERIES_PER_HOUR 2000`.
- Credentials come only from the environment. `repr(Settings)` hides `LLM_API_KEY`, `DB_DSN` and `API_TOKEN`.

---

## 15. Data and file map

| Path | Committed? | Contents |
|---|---|---|
| `src/gadgetgenie/evaluation/gold.jsonl` | Yes (an exception to the `*.jsonl` rule) | 26 gold questions with gold SQL or `expect_refusal` |
| `src/gadgetgenie/prompts/*.md` | Yes | The SQL prompt and the summary prompt |
| `src/gadgetgenie/api/static/*` | Yes | Chat page, script and style sheet |
| `deploy/*.sql` | Yes | Scripts for the read-only database accounts |
| `.env.example` | Yes | All variable names, no values |
| `data/gadgetgenie.db` | No (git ignores `/data/`) | SQLite demo catalogue. `build_recommender()` creates it if it does not exist |
| `reports/eval.json` | No (git ignores `/reports/`) | Evaluation report from `gadgetgenie eval --out` |
| `logs/*.jsonl` | No (git ignores `/logs/` and `*.jsonl`) | Query log if `QUERY_LOG_PATH` points there |
| `.env` | No (git ignores it) | Local credentials |
| `*.csv`, `*.db`, `*.sqlite` | No (git ignores them) | Source CSV files and databases |

---

## 16. How to run GadgetGenie

### 16.1 Prerequisites

| Need | For |
|---|---|
| Python 3.10+ (CI uses 3.11) | All components |
| An OpenAI-compatible API key | Optional. Real LLM answers |
| PostgreSQL or MySQL server | Optional. Production back ends |
| `curl` | Optional. Calls to the HTTP API |

### 16.2 Installation

```bash
git clone https://github.com/KrishnaAnnavaram/gadgetgenie.git
cd gadgetgenie
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev,api]"
```

| Extra | Packages | For |
|---|---|---|
| (core) | `sqlglot`, `httpx` | All components |
| `dev` | `pytest`, `ruff` | Tests |
| `api` | `fastapi`, `uvicorn` | `gadgetgenie serve` |
| `postgres` | `psycopg[binary]` | `DB_BACKEND=postgres` and `seed --postgres` |
| `mysql` | `pymysql` | `DB_BACKEND=mysql` |
| `all` | `api`, `postgres`, `mysql` | Full installation |

### 16.3 Run GadgetGenie

Offline demo (no key, no server):

```bash
gadgetgenie seed                                    # data/gadgetgenie.db: 140 fictional devices
gadgetgenie ask 'cheapest 5G phones under $400'
FX_RATES_TO_USD="INR=0.012" gadgetgenie ask "top laptops under ₹50,000"
gadgetgenie ask "What is the capital of France?" --json   # status "refused"
gadgetgenie eval --out reports/eval.json            # evaluation on the bundled gold set
pytest -q                                           # 112 tests
```

HTTP API and chat page:

```bash
gadgetgenie serve                                   # chat page on http://127.0.0.1:8000
curl -s -X POST http://127.0.0.1:8000/api/ask -H "Content-Type: application/json" \
     -d '{"question": "How many tablets are there?"}'
curl -s http://127.0.0.1:8000/api/stats
```

Real LLM: copy `.env.example` to `.env` and set `LLM_API_KEY`. For a provider other than Groq, also set `LLM_BASE_URL` and `LLM_MODEL`.

Your own data:

```bash
gadgetgenie seed --laptops-csv laptops.csv --source "<dataset name, URL, licence>" \
                 --price-currency EUR --rate-to-usd 1.08 --price-as-of 2026-01-01
```

PostgreSQL:

1. Install the extra: `pip install -e ".[postgres]"`.
2. Create and fill the catalogue with the owner account: `gadgetgenie seed --postgres "<owner dsn>"`.
3. Make the read-only role with `deploy/postgres_readonly_role.sql`.
4. Set `DB_BACKEND=postgres` and set `DB_DSN` to the read-only role.

MySQL: create the tables and views with an owner account (the seed step has no MySQL loader). Then run `deploy/mysql_readonly_user.sql`, set `DB_BACKEND=mysql` and set `DB_DSN`.

### 16.4 Environment variables

| Variable | Used by | Meaning |
|---|---|---|
| `LLM_PROVIDER` | LLM clients | `openai` (any OpenAI-compatible API) or `offline`. Default: `openai` if `LLM_API_KEY` is set, else `offline` |
| `LLM_BASE_URL` | LLM clients | Chat-completions base URL. Default `https://api.groq.com/openai/v1` |
| `LLM_API_KEY` | LLM clients | API key. No default |
| `LLM_MODEL` | LLM clients | Name of the LLM at the provider. Default `llama-3.1-8b-instant` |
| `LLM_TIMEOUT_S` | LLM clients | HTTP time limit for each request. Default `30` |
| `LLM_SEED` | LLM clients | Seed sent with each request (temperature is always 0). Default `7` |
| `DB_BACKEND` | Executors | `sqlite`, `postgres` or `mysql`. Default `sqlite` |
| `SQLITE_PATH` | Executors, ETL step | SQLite file. Default `data/gadgetgenie.db` |
| `DB_DSN` | Executors | DSN of the read-only account (`postgresql://...` or `mysql://user:pass@host/db`). Necessary for `postgres` and `mysql` |
| `SQL_DIALECT` | Text-to-SQL loop, SQL guard | Dialect that the LLM generates. Default: the same as `DB_BACKEND` |
| `MAX_ROWS` | SQL guard, executors | Row limit for `LIMIT`. Default `10`, range 1 to 100 |
| `QUERY_TIMEOUT_S` | Executors | Time limit for each query. Default `5`, must be positive |
| `MAX_ATTEMPTS` | Text-to-SQL loop | LLM calls for each question. Default `3`, range 1 to 5 |
| `MAX_QUESTION_CHARS` | Input check, HTTP API | Question length limit. Default `500` |
| `FX_RATES_TO_USD` | Slot extractor | Exchange rates in USD for 1 unit, for example `INR=0.012,EUR=1.08`. `USD=1` is always present |
| `QUERY_LOG_PATH` | Query log | JSONL file for the query log. If empty, the log is in memory only |
| `API_TOKEN` | HTTP API | If set, `POST /api/ask` and `GET /api/stats` need `Authorization: Bearer <token>` |
| `CORS_ORIGINS` | HTTP API | Comma-separated origins. CORS is off if empty |
| `RATE_LIMIT_PER_MINUTE` | HTTP API | Requests for each client IP in 60 seconds. Default `30` |

`Settings.check()` rejects unknown provider and back-end values, an empty `DB_DSN` for PostgreSQL or MySQL and values out of range. `parse_rates()` rejects a rate that is not positive. Values in the environment win over values in `.env`.

Credentials are only in a local `.env` file. Git ignores this file. Do not print or commit credentials.

---

## 17. How to extend GadgetGenie

| You want to… | Do this | Code change? |
|---|---|---|
| Use another LLM provider | Set `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY` | No |
| Accept a new currency | Add `CODE=rate` to `FX_RATES_TO_USD` (the currency must be in `etl/units.py`) | No |
| Load real device data | Run `gadgetgenie seed --laptops-csv` or `--phones-csv` with `--source` and the exchange rate | No |
| Add gold questions | Add JSON lines to a file and run `gadgetgenie eval --gold PATH` | No |
| Accept a new CSV header name | Add the alias to `LAPTOP_ALIASES` or `PHONE_ALIASES` in `etl/loaders.py` | Small |
| Allow one more SQL function | Add the name to `SAFE_FUNCTIONS` in `core/sql_guard.py` and add a test | Small |
| Add a spec column | Add it to the DDL, the view, `VIEWS` in `schema.py`, the loaders and `etl/seed.py` | Yes |
| Add a device category | Add it to `CATEGORIES`, the DDL `CHECK`, the views, the slot words and the synthetic data | Yes |
| Change a prompt | Add a new file in `prompts/` and change `SQL_PROMPT` or `SUMMARY_PROMPT` in `core/prompts.py` | Small |

---

## 18. Validation results

| Validation | Result | Command |
|---|---|---|
| Unit tests | **112 passed** | `pytest -q` |
| `execution accuracy` (offline, 23 data items) | 100% (23/23) | `gadgetgenie eval` |
| Exact-set match (15 list items) | 100%, mean Jaccard 1.000 | `gadgetgenie eval` |
| Accuracy within 1, 2, 3 attempts | 100%, 100%, 100% | `gadgetgenie eval` |
| Retry rate | 0% | `gadgetgenie eval` |
| Refusal accuracy (3 items) | 100% (3/3) | `gadgetgenie eval` |
| Faithful summaries | 100% | `gadgetgenie eval` |
| HTTP API | `/api/health` 200, `/api/ask` 200, `/api/stats` 200, `429` after the rate limit, `/docs` 404 | `gadgetgenie serve` and `curl` |

The evaluation ran on the synthetic demo catalogue (140 fictional devices, random seed 11) with the offline LLM. The tests use a `FakeModel`, a temporary SQLite catalogue and `httpx.MockTransport`. They cover 25 attack and bad queries for the SQL guard and 7 writes and catalogue reads that the executor blocks without the SQL guard. They also cover the reply parser, the retry loop, the faithfulness check, slots and currency, the ETL step, sessions, the harness and the HTTP API.

These numbers show that the harness works. They are not a quality claim, because the offline LLM uses the same vocabulary as the gold questions. The tests show that wrong SQL gets 0% and that a success at attempt 2 counts as attempt 2. The project has no results for a real LLM on the gold set yet.

---

## 19. Known problems

Read these problems before you use GadgetGenie in production.

| # | Area | Problem | Impact and action |
|---|---|---|---|
| 1 | Offline LLM | It knows only the slot vocabulary | Use a real LLM for real questions |
| 2 | Answer quality | The SQL guard limits what a query can read. It does not prove that the query matches the question | Use the evaluation harness to measure accuracy |
| 3 | Faithfulness check | It checks numbers only, not names or claims. Small integers up to the row count always pass | Read the rows, not only the summary |
| 4 | Exchange rates | The rates are fixed values from `FX_RATES_TO_USD`. Nothing gets live rates | Update the rates when they change |
| 5 | MySQL | The seed step has no MySQL loader, and no test runs the DDL on MySQL | Create the MySQL schema by hand and check it on a MySQL server |
| 6 | Back ends in CI | No CI test uses a real PostgreSQL or MySQL server | Check `PostgresExecutor`, `MySQLExecutor` and `write_postgres()` on real servers before production |
| 7 | State | The sessions, the query log and the rate limiter are in process memory. The rate limiter keeps one entry for each client IP and never deletes it | A restart deletes them. Several workers do not share them. Use a proxy rate limit for public use |
| 8 | Rate limit key | The key is the client IP. Behind a proxy, all users share one IP | Put the rate limit in the proxy, or pass the real client IP |
| 9 | Evaluation | The gold set has only 26 items, and no real-LLM numbers exist | Add paraphrased and multi-constraint questions and measure a real LLM |
| 10 | Chat page | `index.html` has `maxlength="500"`, which does not follow `MAX_QUESTION_CHARS` | Change the page if you change the limit |
| 11 | Session memory | The store keeps only the last turn | A follow-up of a follow-up uses only the most recent slots |
| 12 | Demo catalogue | The 140 devices are fictional | Do not use the demo data as advice about real devices |

---

## 20. Key points

1. **The LLM generates SQL, but code decides what can run.** The SQL guard parses each query, and read-only accounts stop all writes.
2. **The LLM sees only two views.** The base tables and `device_id` are not available to it.
3. **Each number in a summary has a source.** If not, the user gets a plain summary from the rows.
4. **No value is guessed.** Unknown specs stay `NULL`, and a budget without an exchange rate stops the request.
5. **Retries are bounded and recorded.** Each attempt has its real number, and a refusal stops the loop.
6. **Ground truth comes from gold SQL.** The harness runs gold queries on the catalogue under test.
7. **Everything runs offline.** The demo, the evaluation and the 112 tests need no key and no network.

---

## 21. Glossary

| Term | Meaning |
|---|---|
| **Answer** | The object that `Recommender.ask()` returns: summary text, status, SQL query, rows, attempts, notes |
| **Attempt** | One LLM call in the text-to-SQL loop, with the parse, the SQL guard and the run of its SQL query |
| **Base table** | One of `devices`, `laptop_specs` and `phone_specs`. The LLM cannot query them |
| **Budget** | A price limit in the question, converted to US dollars |
| **Catalogue** | The database of devices: 3 base tables and 2 views |
| **Device** | One laptop, phone, tablet or smartwatch in the catalogue |
| **ETL step** | The code in `src/gadgetgenie/etl/` that reads, converts and loads device data |
| **Exchange rate** | The number of US dollars for 1 unit of a currency, from `FX_RATES_TO_USD` |
| **Executor** | The component that runs a checked SQL query read-only |
| **Faithfulness check** | The code that compares each number in a summary with the rows, the question and the row count |
| **Gold SQL** | A correct SQL query for a gold question |
| **Gold set** | The list of evaluation questions in `gold.jsonl` |
| **Ground truth** | The result of the gold SQL on the catalogue under test |
| **Hints** | The slot text that the text-to-SQL loop sends to the LLM |
| **LLM** | The language model client: an OpenAI-compatible API or the offline LLM |
| **Offline LLM** | `OfflineModel`, a rule-based stand-in for an LLM with no network |
| **Plain summary** | The summary that `plain_summary()` makes from the rows without an LLM |
| **Query log** | The record of each question with status, attempts, time and tokens |
| **Refusal** | A reply with an `error` key. The answer status is `refused` |
| **Reply** | The JSON text that the LLM returns for the SQL task |
| **Session** | One conversation, with a random 32-character session ID |
| **Slots** | The fields that the slot extractor finds in a question: category, budget, brands, requirements, sort order |
| **SQL guard** | The code in `core/sql_guard.py` that checks each SQL query against the allow-lists |
| **Summary** | The short recommendation text in an answer |
| **View** | `laptops` or `phones`: the only objects that the LLM can query |

---

## 22. License

[MIT](LICENSE) © 2026 Krishna Annavaram
