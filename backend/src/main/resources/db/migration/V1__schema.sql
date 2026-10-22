CREATE TABLE learner (
    id text PRIMARY KEY
);

CREATE TABLE concept (
    id text PRIMARY KEY,
    name text NOT NULL,
    field text NOT NULL DEFAULT 'computer_science'
);

CREATE TABLE problem (
    id text PRIMARY KEY,
    title text
);

CREATE TABLE problem_concept (
    problem_id text NOT NULL REFERENCES problem(id),
    concept_id text NOT NULL REFERENCES concept(id),
    PRIMARY KEY (problem_id, concept_id)
);

CREATE TABLE interaction (
    log_id text PRIMARY KEY,
    learner_id text NOT NULL REFERENCES learner(id),
    problem_id text NOT NULL REFERENCES problem(id),
    is_correct boolean NOT NULL,
    score double precision,
    source_attempts integer,
    submitted_at timestamptz NOT NULL,
    dataset_split text CHECK (dataset_split IN ('train', 'validation', 'test'))
);
CREATE INDEX interaction_learner_time_idx ON interaction(learner_id, submitted_at);
CREATE INDEX interaction_split_idx ON interaction(dataset_split, submitted_at);

CREATE TABLE learner_state (
    learner_id text NOT NULL REFERENCES learner(id),
    concept_id text NOT NULL REFERENCES concept(id),
    correct_count integer NOT NULL CHECK (correct_count >= 0),
    total_count integer NOT NULL CHECK (total_count > 0 AND correct_count <= total_count),
    mastery double precision NOT NULL CHECK (mastery >= 0 AND mastery <= 1),
    as_of timestamptz NOT NULL,
    PRIMARY KEY (learner_id, concept_id, as_of)
);

CREATE TABLE concept_difficulty (
    concept_id text PRIMARY KEY REFERENCES concept(id),
    train_correct integer NOT NULL CHECK (train_correct >= 0),
    train_total integer NOT NULL CHECK (train_total > 0 AND train_correct <= train_total),
    difficulty double precision NOT NULL CHECK (difficulty >= 0 AND difficulty <= 1),
    derived_from_split text NOT NULL CHECK (derived_from_split = 'train')
);

CREATE TABLE prerequisite (
    prerequisite_id text NOT NULL REFERENCES concept(id),
    concept_id text NOT NULL REFERENCES concept(id),
    source text NOT NULL,
    ground_truth smallint,
    text_predict double precision,
    graph_predict double precision,
    annotated boolean NOT NULL,
    PRIMARY KEY (prerequisite_id, concept_id, source),
    CHECK (prerequisite_id <> concept_id),
    CHECK (ground_truth IS NULL OR ground_truth IN (0, 1))
);

CREATE TABLE recommendation (
    id uuid PRIMARY KEY,
    learner_id text NOT NULL REFERENCES learner(id),
    target_id text NOT NULL REFERENCES concept(id),
    status text NOT NULL,
    config jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recommendation_step (
    recommendation_id uuid NOT NULL REFERENCES recommendation(id) ON DELETE CASCADE,
    step_index integer NOT NULL,
    concept_id text NOT NULL REFERENCES concept(id),
    scores jsonb NOT NULL,
    PRIMARY KEY (recommendation_id, step_index)
);

CREATE TABLE data_summary (
    key text PRIMARY KEY,
    value jsonb NOT NULL
);
