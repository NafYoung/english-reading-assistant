CREATE TABLE IF NOT EXISTS glossary_terms (
  id INTEGER PRIMARY KEY,
  term TEXT NOT NULL,
  lemma TEXT NOT NULL,
  pos TEXT,
  en_def TEXT NOT NULL,
  zh_def TEXT NOT NULL,
  domain TEXT DEFAULT 'ai',
  status TEXT NOT NULL CHECK(status IN ('draft','approved','rejected')),
  source TEXT NOT NULL,
  example_sentence_id INTEGER,
  created_at TEXT,
  reviewed_at TEXT
);

CREATE TABLE IF NOT EXISTS user_words (
  lemma TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK(status IN ('unknown','learning','known','ignored')),
  source TEXT NOT NULL,
  confidence REAL NOT NULL,
  encounters INTEGER DEFAULT 0,
  lookups INTEGER DEFAULT 0,
  first_seen TEXT,
  last_seen TEXT,
  fsrs_card TEXT,
  due_at TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS word_events (
  id INTEGER PRIMARY KEY,
  lemma TEXT,
  event TEXT,
  session_id INTEGER,
  doc_id INTEGER,
  sentence_id INTEGER,
  payload TEXT,
  ts TEXT
);

CREATE TABLE IF NOT EXISTS learner_profile (
  id INTEGER PRIMARY KEY CHECK(id=1),
  vocab_estimate INTEGER,
  band_curve TEXT,
  false_alarm_rate REAL,
  placement_at TEXT
);

CREATE TABLE IF NOT EXISTS corpora (
  id INTEGER PRIMARY KEY,
  title TEXT,
  goal TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY,
  corpus_id INTEGER,
  source_type TEXT CHECK(source_type IN ('url','pdf','md','text')),
  source_ref TEXT,
  title TEXT,
  text TEXT,
  n_tokens INTEGER,
  ingest_report TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS sentences (
  id INTEGER PRIMARY KEY,
  doc_id INTEGER,
  idx INTEGER,
  para_idx INTEGER,
  text TEXT,
  char_start INTEGER,
  char_end INTEGER
);

CREATE TABLE IF NOT EXISTS doc_lemmas (
  doc_id INTEGER,
  lemma TEXT,
  count INTEGER,
  first_sentence_id INTEGER,
  kind TEXT CHECK(kind IN ('dict','term_candidate')),
  PRIMARY KEY(doc_id, lemma)
);

CREATE TABLE IF NOT EXISTS plans (
  id INTEGER PRIMARY KEY,
  corpus_id INTEGER,
  created_at TEXT,
  plan_json TEXT,
  trace_id TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY,
  doc_id INTEGER,
  started_at TEXT,
  ended_at TEXT,
  words_read INTEGER,
  l1_count INTEGER,
  l2_count INTEGER,
  l3_count INTEGER,
  quiz_score REAL
);

CREATE TABLE IF NOT EXISTS hint_events (
  id INTEGER PRIMARY KEY,
  session_id INTEGER,
  sentence_id INTEGER,
  level INTEGER CHECK(level IN (1,2,3)),
  target TEXT,
  llm_call_id INTEGER,
  ts TEXT
);

CREATE TABLE IF NOT EXISTS sense_cache (
  lemma TEXT,
  sentence_id INTEGER,
  prompt_version TEXT,
  result_json TEXT,
  PRIMARY KEY(lemma, sentence_id, prompt_version)
);

CREATE TABLE IF NOT EXISTS quizzes (
  id INTEGER PRIMARY KEY,
  session_id INTEGER,
  items_json TEXT,
  verify_json TEXT
);

CREATE TABLE IF NOT EXISTS quiz_answers (
  quiz_id INTEGER,
  item_idx INTEGER,
  answer TEXT,
  correct INTEGER,
  ts TEXT
);

CREATE TABLE IF NOT EXISTS llm_calls (
  id INTEGER PRIMARY KEY,
  purpose TEXT,
  model TEXT,
  prompt_version TEXT,
  thinking INTEGER,
  input_tokens INTEGER,
  output_tokens INTEGER,
  cache_hit_tokens INTEGER,
  latency_ms INTEGER,
  cost_usd_est REAL,
  ok INTEGER,
  error TEXT,
  trace_id TEXT,
  ts TEXT
);

CREATE TABLE IF NOT EXISTS agent_traces (
  trace_id TEXT,
  step INTEGER,
  kind TEXT,
  content TEXT,
  ts TEXT
);

CREATE TABLE IF NOT EXISTS eval_labels (
  id INTEGER PRIMARY KEY,
  task TEXT,
  item_json TEXT,
  label_json TEXT,
  labeler TEXT,
  ts TEXT
);

CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_word_events_lemma ON word_events(lemma);
CREATE INDEX IF NOT EXISTS idx_sentences_doc ON sentences(doc_id, idx);
CREATE INDEX IF NOT EXISTS idx_hint_events_session ON hint_events(session_id);
CREATE INDEX IF NOT EXISTS idx_llm_calls_ts ON llm_calls(ts);
CREATE INDEX IF NOT EXISTS idx_user_words_due ON user_words(due_at);
CREATE INDEX IF NOT EXISTS idx_glossary_status ON glossary_terms(status, lemma);
CREATE INDEX IF NOT EXISTS idx_agent_traces ON agent_traces(trace_id, step);
