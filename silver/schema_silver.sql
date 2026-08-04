CREATE SCHEMA IF NOT EXISTS silver;

-- ============================================================
-- KNOWN LIMITATION: home_club_id / away_club_id (games) and
-- player_club_id / current_national_team_id (appearances, players)
-- can reference EITHER silver.clubs OR a national team, depending
-- on whether the competition is a domestic club competition or an
-- international one (e.g. World Cup). A national_teams table was
-- considered but scoped out due to time constraints. These columns
-- are intentionally left as plain integers with NO foreign key
-- constraint, since a single FK can't point at two different tables
-- (a "polymorphic reference"). This is a documented, deliberate
-- trade-off, not an oversight.
-- ============================================================


-- 1. competitions --------------------------------------------
DROP TABLE IF EXISTS silver.competitions CASCADE;
CREATE TABLE silver.competitions (
    competition_id        VARCHAR(10)  PRIMARY KEY,
    name                   VARCHAR(100) NOT NULL,
    sub_type                VARCHAR(50),
    type                     VARCHAR(50),
    country_name              VARCHAR(100),
    domestic_league_code       VARCHAR(10),
    confederation                 VARCHAR(50)
);


ALTER TABLE silver.competitions
    ADD CONSTRAINT fk_domestic_league
    FOREIGN KEY (domestic_league_code) REFERENCES silver.competitions(competition_id)
    DEFERRABLE INITIALLY DEFERRED;


-- 2. clubs (-> competitions) -----------------------------------
DROP TABLE IF EXISTS silver.clubs CASCADE;
CREATE TABLE silver.clubs (
    club_id                   INTEGER      PRIMARY KEY,
    name                       VARCHAR(100) NOT NULL,
    domestic_competition_id      VARCHAR(10) REFERENCES silver.competitions(competition_id),
    squad_size                     INTEGER,
    foreigners_number                 INTEGER,
    national_team_players                INTEGER,
    stadium_name                            VARCHAR(100),
    stadium_seats                              INTEGER,
    coach_name                                    VARCHAR(100),
    last_season                                      INTEGER
);


-- 3. players (-> clubs) -----------------------------------------
DROP TABLE IF EXISTS silver.players CASCADE;
CREATE TABLE silver.players (
    player_id                 INTEGER      PRIMARY KEY,
    first_name                 VARCHAR(100),
    last_name                    VARCHAR(100),
    last_season                    INTEGER,
    current_club_id                  INTEGER REFERENCES silver.clubs(club_id),
    country_of_birth                    VARCHAR(100),
    date_of_birth                          DATE,
    sub_position                              VARCHAR(50),
    position                                    VARCHAR(50),
    foot                                          VARCHAR(20),
    height_in_cm                                    INTEGER,
    international_caps                                 INTEGER,
    international_goals                                   INTEGER,
    current_national_team_id                                INTEGER  -- no FK, see note above
);


-- 4. games (-> competitions; home/away NOT FK'd, see note above) -
DROP TABLE IF EXISTS silver.games CASCADE;
CREATE TABLE silver.games (
    game_id                  INTEGER      PRIMARY KEY,
    competition_id             VARCHAR(10) REFERENCES silver.competitions(competition_id),
    season                        INTEGER,
    round                            VARCHAR(50),
    date                                DATE,
    home_club_id                          INTEGER,  -- no FK, see note above
    away_club_id                            INTEGER,  -- no FK, see note above
    home_club_goals                            INTEGER,
    away_club_goals                              INTEGER,
    home_club_position                              INTEGER,
    away_club_position                                 INTEGER,
    home_club_manager_name                                VARCHAR(100),
    away_club_manager_name                                   VARCHAR(100),
    stadium                                                    VARCHAR(100),
    attendance                                                    INTEGER,
    referee                                                         VARCHAR(100)
);


-- 5. appearances (-> games, players; player_club_id NOT FK'd) ----
DROP TABLE IF EXISTS silver.appearances CASCADE;
CREATE TABLE silver.appearances (
    appearance_id     VARCHAR(20) PRIMARY KEY,
    game_id             INTEGER NOT NULL REFERENCES silver.games(game_id),
    player_id             INTEGER NOT NULL REFERENCES silver.players(player_id),
    player_club_id           INTEGER,  -- no FK, see note above
    yellow_cards                INTEGER NOT NULL DEFAULT 0 CHECK (yellow_cards >= 0),
    red_cards                     INTEGER NOT NULL DEFAULT 0 CHECK (red_cards >= 0),
    goals                            INTEGER NOT NULL DEFAULT 0 CHECK (goals >= 0),
    assists                             INTEGER NOT NULL DEFAULT 0 CHECK (assists >= 0),
    minutes_played                         INTEGER NOT NULL DEFAULT 0
                                              CHECK (minutes_played BETWEEN 0 AND 120)
);


CREATE INDEX idx_appearances_player ON silver.appearances(player_id);
CREATE INDEX idx_appearances_game ON silver.appearances(game_id);
CREATE INDEX idx_games_competition ON silver.games(competition_id);
CREATE INDEX idx_clubs_competition ON silver.clubs(domestic_competition_id);

