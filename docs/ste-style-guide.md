# ASD-STE100 Simplified Technical English: the standard for GadgetGenie documents

Use these rules for the `README.md` of GadgetGenie and for this file. Section 3 gives the
**project vocabulary**: the technical names and the technical verbs of GadgetGenie. Each term has one meaning.

## 1. Rules for text

### Words

1. Use one word for one meaning, and one meaning for one word. Do not use synonyms for variety.
2. Use a word only as one part of speech. For example, "test" is a noun or a verb, "check" is a verb.
3. Do not use phrasal verbs (`set up`, `carry out`, `find out`, `pick up`, `look up`, `come up with`).
   Use one verb: "prepare", "do", "find", "get", "make".
4. Do not use an "-ing" form as a noun or an adjective (`the running job`, `after indexing`).
   Exception: a technical name, a file name, a command or a status value.
5. Do not use contractions (`don't`, `it's`, `can't`). Do not use slang or idioms
   (`out of the box`, `under the hood`, `at a glance`, `gotcha`, `bells and whistles`).
6. Do not use `and/or`. Write "A, B or both".
7. Do not use `should`, `could`, `would` or `may` for instructions. Use "must" for a rule, the
   imperative for a step and "can" for a possibility.
8. Keep the articles "a", "an" and "the" in sentences.
9. Do not make a noun cluster of more than three words. A technical name is one word.

### Sentences

1. A procedural sentence (an instruction) has a maximum of **20 words**.
2. A descriptive sentence has a maximum of **25 words**.
3. Write one instruction in one sentence.
4. Use the imperative for an instruction: "Run the tests." Not `The tests are to be run.`
5. Use the active voice. Use the passive voice only when the agent of the action is not important.
6. Use only the simple present, the simple past and the simple future.
7. Put a condition before the instruction: "If the index is old, build it again."
8. Do not use semicolons in sentences. Write two sentences.

### Paragraphs, notes and warnings

1. A paragraph has one topic and a maximum of **6 sentences**. Start with the topic sentence.
2. A warning or a caution starts with a clear command. Then it gives the reason.
3. A note gives information. It does not give an instruction.
4. Use a vertical list for a sequence or a set of conditions. Each item of a numbered procedure is one step.

### Tables, headings and diagrams

1. A table cell can be a short phrase. If a cell has a sentence, the sentence obeys the rules.
2. A heading is a noun phrase ("The cost model") or an imperative ("Run the demo").
   Do not start a heading with an "-ing" form.
3. A diagram label is a short phrase. Use the same terms as the text.

### What STE does not change

Code, commands, file names, paths, field names, environment variables, status values, enum values,
product names and URLs stay exactly as they are. They are technical names. Put them in backticks.

## 2. General words to replace

| Do not use | Use |
|---|---|
| utilize, leverage | use |
| in order to | to |
| set up | prepare, install, configure |
| carry out, perform | do |
| make sure, ensure | make sure (allowed), or "check that" |
| a lot of, lots of | many, much |
| e.g., i.e. | for example, that is |
| should (instruction) | must (rule) / imperative (step) |
| might, may (possibility) | can |
| very, really, just, simply, easily | (delete) |
| seamless, robust, powerful, blazing | (delete or give a measured fact) |

## 3. Project vocabulary

### 3.1 Technical names (nouns)

| Term | Meaning | Do not use |
|---|---|---|
| **answer** | The object that `Recommender.ask()` returns: summary text, status, SQL query, rows, attempts, notes | response (except for HTTP), result |
| **attempt** | One LLM call in the text-to-SQL loop, with the parse, the SQL guard and the run of its SQL query | try, round |
| **back end** | A database that GadgetGenie reads: SQLite, PostgreSQL or MySQL | backend, storage layer |
| **base table** | One of `devices`, `laptop_specs` and `phone_specs` | raw table, source table |
| **budget** | A price limit in the question, converted to US dollars | price cap, spend |
| **catalogue** | The database of devices: 3 base tables and 2 views | catalog, inventory, product DB |
| **component** | One part of GadgetGenie with one purpose | module (except for a Python file), piece |
| **device** | One laptop, phone, tablet or smartwatch in the catalogue | product, gadget, item |
| **device model** | The value in the column `model`: the name of one device | product name, SKU |
| **ETL step** | The code in `src/gadgetgenie/etl/` that reads, converts and loads device data | importer, loader job, pipeline |
| **evaluation harness** | The code in `src/gadgetgenie/evaluation/` that scores the recommender on the gold set | benchmark, evaluator |
| **exchange rate** | The number of US dollars for 1 unit of a currency, from `FX_RATES_TO_USD` | FX, conversion factor |
| **executor** | The component that runs a checked SQL query read-only | runner, driver, DB client |
| **faithfulness check** | The code that compares each number in a summary with the rows, the question and the row count. A technical name: the verb is "check" | hallucination filter, validator |
| **front end** | The CLI, the HTTP API or the chat page | interface, client, frontend |
| **gold SQL** | A correct SQL query for a gold question | reference query, expected SQL |
| **gold set** | The list of evaluation questions in `gold.jsonl` | test set, benchmark |
| **gold item** | One question in the gold set, with its gold query or its expected refusal | case, sample, record |
| **ground truth** | The result of the gold SQL on the catalogue under test | expected answer, label |
| **hints** | The slot text that the text-to-SQL loop sends to the LLM | context, constraints text |
| **input check** | The component that normalizes and limits the question (`Recommender.clean()`). A technical name: the verb is "check" | sanitizer, input filter |
| **LLM** | The language model client: an OpenAI-compatible API or the offline LLM | model (alone: `model` is a column), AI, bot |
| **offline LLM** | `OfflineModel`, the rule-based stand-in for an LLM | mock, fake model, dummy |
| **plain summary** | The summary that `plain_summary()` makes from the rows without an LLM | fallback text, template answer |
| **query log** | The record of each question with status, attempts, time and tokens (`QueryLog`) | audit log, telemetry |
| **query safety model** | The set of rules in code that limit what a SQL query can read and how long it runs | security layer, guard rails |
| **question** | The plain-English text that a user sends | query (for user text), prompt, request |
| **random seed** | The number that makes the synthetic catalogue the same each time (`--seed`, default `11`) | seed (alone), RNG state |
| **rate limiter** | The component that limits API requests for each client IP (`RateLimiter`) | throttle |
| **refusal** | A reply with an `error` key. The answer status is `refused` | rejection, decline |
| **reply** | The JSON text that the LLM returns for the SQL task | completion, output, response |
| **result** | The rows that a SQL query returns | records, data, output |
| **retry** | A repeat of a failed LLM call or of a failed attempt | second try, redo |
| **session** | One conversation, with a random 32-character session ID | chat, thread, user context |
| **setting** | One configuration value that an environment variable gives | option, parameter, flag (for configuration) |
| **slots** | The fields that the slot extractor finds in a question | entities, intents, parameters |
| **SQL guard** | The code in `core/sql_guard.py` that checks each SQL query against the allow-lists | validator, checker, sanitizer, filter |
| **SQL query** | One SQL statement that the LLM generates or that the gold set holds | command, request |
| **statement** | One SQL command in a query text | SQL instruction |
| **summary** | The short recommendation text in an answer | description, explanation |
| **test** | One `pytest` test function or one parameter case of it. A noun only: the verb is "check" | unit check, spec |
| **view** | `laptops` or `phones`: the only objects that the LLM can query | virtual table, projection |

### 3.2 Technical verbs

| Verb | Meaning |
|---|---|
| **check** | Compare a value, a query or a component with a rule or a limit |
| **convert** | Change an amount to US dollars with an exchange rate, or change a unit to the catalogue unit |
| **generate** | Make text with the LLM: a reply or a summary |
| **refuse** | Answer a question about other topics with a refusal |
| **reject** | Stop a SQL query, a reply or an input and give an error message |
| **run** | Start a command, a test, a SQL query on a back end or the evaluation |
| **seed** | Create the catalogue and fill it (`gadgetgenie seed`) |
