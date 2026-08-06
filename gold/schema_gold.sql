CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS gold.dim_date (
    date_id        INTEGER      PRIMARY KEY,
    full_date      DATE         NOT NULL,
    day            INTEGER      NOT NULL,
    month          INTEGER      NOT NULL,
    month_name     VARCHAR(20)  NOT NULL,
    quarter        INTEGER      NOT NULL,
    year           INTEGER      NOT NULL,
    day_of_week    INTEGER      NOT NULL,
    day_name       VARCHAR(20)  NOT NULL,
    is_weekend     BOOLEAN      NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.dim_competitions (
    competition_id   VARCHAR(10)  PRIMARY KEY,
    name             VARCHAR(100),
    type             VARCHAR(50),
    sub_type         VARCHAR(50),
    confederation    VARCHAR(50),
    country_name     VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS gold.dim_clubs (
    club_id          INTEGER      PRIMARY KEY,
    name             VARCHAR(100),
    competition_id   VARCHAR(10)  REFERENCES gold.dim_competitions(competition_id),
    stadium_name     VARCHAR(100),
    stadium_seats    INTEGER,
    squad_size       INTEGER,
    coach_name       VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS gold.dim_players (
    player_id        INTEGER      PRIMARY KEY,
    first_name       VARCHAR(100),
    last_name        VARCHAR(100),
    position         VARCHAR(50),
    sub_position     VARCHAR(50),
    foot             VARCHAR(20),
    height_in_cm     INTEGER,
    date_of_birth    DATE,
    country_of_birth VARCHAR(100),
    current_club_id  INTEGER      REFERENCES gold.dim_clubs(club_id)
);

CREATE TABLE IF NOT EXISTS gold.fact_appearances (
    appearance_id    VARCHAR(20)  PRIMARY KEY,
    date_id          INTEGER      NOT NULL REFERENCES gold.dim_date(date_id),
    player_id        INTEGER      NOT NULL REFERENCES gold.dim_players(player_id),
    club_id          INTEGER      REFERENCES gold.dim_clubs(club_id),
    competition_id   VARCHAR(10)  REFERENCES gold.dim_competitions(competition_id),
    game_id          INTEGER      NOT NULL,
    season           INTEGER,
    goals            INTEGER      NOT NULL DEFAULT 0,
    assists          INTEGER      NOT NULL DEFAULT 0,
    yellow_cards     INTEGER      NOT NULL DEFAULT 0,
    red_cards        INTEGER      NOT NULL DEFAULT 0,
    minutes_played   INTEGER      NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_fact_player      ON gold.fact_appearances(player_id);
CREATE INDEX IF NOT EXISTS idx_fact_date        ON gold.fact_appearances(date_id);
CREATE INDEX IF NOT EXISTS idx_fact_club        ON gold.fact_appearances(club_id);
CREATE INDEX IF NOT EXISTS idx_fact_competition ON gold.fact_appearances(competition_id);
CREATE INDEX IF NOT EXISTS idx_fact_season      ON gold.fact_appearances(season);