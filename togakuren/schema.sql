-- Analytical store for Tokyo University Football Association fixtures.
--
-- Personal data lives in `players` and `squad_members` only. Everything an
-- analysis actually needs joins on `player_id`, so those two tables can be
-- dropped or pseudonymised without breaking the rest of the schema.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS series (
    id           TEXT PRIMARY KEY,
    year         TEXT NOT NULL,
    name         TEXT,
    short_name   TEXT,
    type         TEXT,
    division     TEXT
);

CREATE TABLE IF NOT EXISTS teams (
    id           TEXT PRIMARY KEY,   -- seriesTeams._id (one row per team per series)
    series_id    TEXT NOT NULL REFERENCES series(id),
    team_id      TEXT,               -- federation-wide club id, stable across seasons
    name         TEXT,
    short_name   TEXT
);
CREATE INDEX IF NOT EXISTS idx_teams_series ON teams(series_id);

CREATE TABLE IF NOT EXISTS standings (
    team_pk           TEXT PRIMARY KEY REFERENCES teams(id),
    series_id         TEXT NOT NULL REFERENCES series(id),
    played            INTEGER,
    win               INTEGER,
    draw              INTEGER,
    lose              INTEGER,
    points            INTEGER,
    goals_for         INTEGER,
    goal_difference   INTEGER,
    fairplay_points   INTEGER
);

-- Personal data. Not exported, not committed. See docs/DATA_POLICY.en.md.
CREATE TABLE IF NOT EXISTS players (
    player_id    TEXT PRIMARY KEY,
    name         TEXT,
    kana         TEXT
);

CREATE TABLE IF NOT EXISTS squad_members (
    series_id    TEXT NOT NULL REFERENCES series(id),
    team_pk      TEXT NOT NULL REFERENCES teams(id),
    player_id    TEXT NOT NULL REFERENCES players(player_id),
    number       TEXT,
    position     TEXT,
    grade        TEXT,
    height       TEXT,
    weight       TEXT,
    former_team  TEXT,
    PRIMARY KEY (series_id, team_pk, player_id)
);

CREATE TABLE IF NOT EXISTS games (
    id           TEXT PRIMARY KEY,
    series_id    TEXT NOT NULL REFERENCES series(id),
    section      TEXT,
    name         TEXT,
    kickoff      TEXT,
    venue        TEXT,
    game_over    INTEGER,
    length       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_games_series ON games(series_id);

CREATE TABLE IF NOT EXISTS game_teams (
    id               TEXT PRIMARY KEY,   -- gameRecords._id
    game_id          TEXT NOT NULL REFERENCES games(id),
    series_id        TEXT NOT NULL REFERENCES series(id),
    team_pk          TEXT,
    score            INTEGER,
    penalties        INTEGER,
    points           INTEGER,
    goal_difference  INTEGER,
    fairplay_points  INTEGER,
    manager          TEXT
);
CREATE INDEX IF NOT EXISTS idx_game_teams_game ON game_teams(game_id);
CREATE INDEX IF NOT EXISTS idx_game_teams_team ON game_teams(team_pk);

CREATE TABLE IF NOT EXISTS appearances (
    game_team_id  TEXT NOT NULL REFERENCES game_teams(id),
    player_id     TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('start', 'bench')),
    position      TEXT,
    number        TEXT,
    on_minute     INTEGER,
    off_minute    INTEGER,
    minutes       INTEGER NOT NULL,
    PRIMARY KEY (game_team_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_appearances_player ON appearances(player_id);

-- `extra_first`/`extra_second` are only ever populated for knockout ties that
-- went to extra time; league fixtures use the two half columns alone.
CREATE TABLE IF NOT EXISTS shots (
    game_team_id  TEXT NOT NULL REFERENCES game_teams(id),
    player_id     TEXT NOT NULL,
    first_half    INTEGER NOT NULL DEFAULT 0,
    second_half   INTEGER NOT NULL DEFAULT 0,
    extra_first   INTEGER NOT NULL DEFAULT 0,
    extra_second  INTEGER NOT NULL DEFAULT 0,
    total         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (game_team_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_shots_player ON shots(player_id);

CREATE TABLE IF NOT EXISTS events (
    game_team_id  TEXT NOT NULL REFERENCES game_teams(id),
    player_id     TEXT,
    type          TEXT NOT NULL CHECK (type IN ('goal', 'yellow', 'red')),
    code          TEXT,
    minute        INTEGER,
    seq           INTEGER NOT NULL,
    PRIMARY KEY (game_team_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_events_player ON events(player_id, type);

CREATE TABLE IF NOT EXISTS substitutions (
    game_team_id   TEXT NOT NULL REFERENCES game_teams(id),
    seq            INTEGER NOT NULL,
    out_player_id  TEXT,
    in_player_id   TEXT,
    minute         INTEGER,
    PRIMARY KEY (game_team_id, seq)
);
