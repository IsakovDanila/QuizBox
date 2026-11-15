CREATE TABLE quizzes (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE TABLE questions (
    id INTEGER PRIMARY KEY,
    quiz_id INTEGER NOT NULL REFERENCES quizzes (id) ON DELETE CASCADE,
    prompt TEXT NOT NULL CHECK (length(trim(prompt)) > 0),
    position INTEGER NOT NULL CHECK (position > 0),
    points INTEGER NOT NULL DEFAULT 1 CHECK (points > 0),
    UNIQUE (quiz_id, position),
    UNIQUE (quiz_id, id)
) STRICT;

CREATE TABLE question_options (
    id INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES questions (id) ON DELETE CASCADE,
    label TEXT NOT NULL CHECK (length(trim(label)) > 0),
    position INTEGER NOT NULL CHECK (position > 0),
    is_correct INTEGER NOT NULL DEFAULT 0 CHECK (is_correct IN (0, 1)),
    UNIQUE (question_id, position),
    UNIQUE (question_id, id)
) STRICT;

CREATE UNIQUE INDEX uq_question_options_correct
    ON question_options (question_id)
    WHERE is_correct = 1;

CREATE TABLE game_sessions (
    id INTEGER PRIMARY KEY,
    quiz_id INTEGER NOT NULL REFERENCES quizzes (id) ON DELETE RESTRICT,
    join_code TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK (length(trim(join_code)) > 0),
    status TEXT NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'active', 'finished')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (quiz_id, id)
) STRICT;

CREATE TABLE participants (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES game_sessions (id) ON DELETE CASCADE,
    display_name TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (session_id, id)
) STRICT;

CREATE TABLE answers (
    id INTEGER PRIMARY KEY,
    quiz_id INTEGER NOT NULL,
    session_id INTEGER NOT NULL,
    participant_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    option_id INTEGER NOT NULL,
    awarded_points INTEGER NOT NULL CHECK (awarded_points >= 0),
    submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (session_id, participant_id, question_id),
    FOREIGN KEY (quiz_id, session_id) REFERENCES game_sessions (quiz_id, id),
    FOREIGN KEY (session_id, participant_id) REFERENCES participants (session_id, id),
    FOREIGN KEY (quiz_id, question_id) REFERENCES questions (quiz_id, id),
    FOREIGN KEY (question_id, option_id) REFERENCES question_options (question_id, id)
) STRICT;

CREATE INDEX ix_answers_question_option ON answers (question_id, option_id);
