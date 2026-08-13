"""
app.py -- Streamlit dashboard on top of the Gold warehouse.

Run with:  streamlit run app.py   (from inside dashboard/)

Structure: st.tabs() as top-level navigation --
  Dashboard | Players | Clubs

Players tab filters: stat type (goals/assists), season, league, position
leaderboards. Nationality filter intentionally omitted -- country_of_citizenship
was scoped out of Silver (see decisions_log.md); country_of_birth was judged
not a reliable-enough substitute to build a filter around.
"""
import os
import psycopg2
import pandas as pd
import streamlit as st
import plotly.express as px
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "bronze", ".env")
load_dotenv(ENV_PATH)

DB_CONFIG = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=os.getenv("DB_PORT", 5432),
    dbname=os.getenv("DB_NAME", "football_db"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", ""),
)

st.set_page_config(page_title="Football Performance Dashboard", layout="wide")


@st.cache_resource
def get_connection():
    return psycopg2.connect(**DB_CONFIG)


@st.cache_data(ttl=600)
def run_query(sql, params=None):
    conn = get_connection()
    return pd.read_sql_query(sql, conn, params=params)


st.title("⚽ Football Player Performance")

# Shared constants -- defined once, used across all tabs.
PLAYER_NAME_EXPR = "TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.last_name, ''))"
DEFAULT_TOP5_IDS = ["GB1", "ES1", "IT1", "L1", "FR1"]  # Premier League, La Liga, Serie A, Bundesliga, Ligue 1
POSITIONS_FOR_BOXES = ["Goalkeeper", "Defender", "Midfield", "Attack"]

# ---------------- Shared reference data ----------------
competitions_df = run_query(
    "SELECT competition_id, name FROM gold.dim_competitions ORDER BY name"
)

# Reorder: top 5 leagues first (in the order listed above), then
# everything else alphabetically -- makes every dropdown/multiselect
# that uses competitions_df show the major leagues up top.
top5_df = competitions_df[competitions_df["competition_id"].isin(DEFAULT_TOP5_IDS)].copy()
top5_df["sort_key"] = top5_df["competition_id"].apply(lambda x: DEFAULT_TOP5_IDS.index(x))
top5_df = top5_df.sort_values("sort_key").drop(columns="sort_key")

others_df = competitions_df[~competitions_df["competition_id"].isin(DEFAULT_TOP5_IDS)].sort_values("name")

competitions_df = pd.concat([top5_df, others_df], ignore_index=True)

seasons_df = run_query(
    "SELECT DISTINCT season FROM gold.fact_appearances WHERE season IS NOT NULL ORDER BY season"
)
positions_df = run_query(
    "SELECT DISTINCT position FROM gold.dim_players WHERE position IS NOT NULL ORDER BY position"
)

tab_dashboard, tab_players, tab_clubs = st.tabs(
    ["Dashboard", "Players", "Clubs"]
)


# ============================================================
# TAB 1 -- Dashboard (hardcoded top-5 league cards, no picker)
# ============================================================
with tab_dashboard:
    st.subheader("Top 5 Leagues")

    # Hardcoded, in DEFAULT_TOP5_IDS order -- no dropdown/multiselect to
    # add or remove leagues here. If you ever want a 6th league on this
    # tab, it means editing DEFAULT_TOP5_IDS, not adding a picker back.
    top5_names = competitions_df.loc[
        competitions_df["competition_id"].isin(DEFAULT_TOP5_IDS), "name"
    ].tolist()
    top5_names = sorted(
        top5_names,
        key=lambda n: DEFAULT_TOP5_IDS.index(
            competitions_df.loc[competitions_df["name"] == n, "competition_id"].iloc[0]
        ),
    )

    if "active_league" not in st.session_state:
        st.session_state.active_league = top5_names[0]

    card_cols = st.columns(5)
    for i, league_name in enumerate(top5_names):
        with card_cols[i]:
            if st.button(league_name, key=f"card_{league_name}", width="stretch"):
                st.session_state.active_league = league_name

    st.divider()

    active_league = st.session_state.active_league
    comp_id = competitions_df.loc[competitions_df["name"] == active_league, "competition_id"].iloc[0]

    # ---- latest season for this league (drives KPIs + Golden Boot only) ----
    latest_season_df = run_query(
        "SELECT MAX(season) AS latest FROM gold.fact_appearances WHERE competition_id = %(cid)s",
        params={"cid": comp_id},
    )
    latest_season = (
        int(latest_season_df["latest"].iloc[0])
        if not latest_season_df.empty and latest_season_df["latest"].iloc[0] is not None
        else None
    )

    st.header(active_league)

    # ---- season control: Winner/Top Scorer/Top Assist/Standings react to this ----
    season_options = sorted(seasons_df["season"].tolist(), reverse=True)
    dash_season_sel = st.selectbox(
        "Season",
        options=season_options,
        index=season_options.index(latest_season) if latest_season in season_options else 0,
        key="dash_season",
    )

    st.divider()

    # ---- Winner + Top Scorer + Top Assist (reacts to dash_season_sel) ----
    standings_sql = """
        WITH club_matches AS (
            SELECT home_club_id AS club_id, home_club_position AS position, date
            FROM silver.games
            WHERE competition_id = %(cid)s AND season = %(season)s
            UNION ALL
            SELECT away_club_id AS club_id, away_club_position AS position, date
            FROM silver.games
            WHERE competition_id = %(cid)s AND season = %(season)s
        ),
        last_match AS (
            SELECT club_id, position,
                   ROW_NUMBER() OVER (PARTITION BY club_id ORDER BY date DESC) AS rn
            FROM club_matches
            WHERE position IS NOT NULL
        ),
        matches_played AS (
            SELECT club_id, COUNT(*) AS played
            FROM club_matches
            GROUP BY club_id
        )
        SELECT c.name AS club, lm.position, mp.played AS matches_played
        FROM last_match lm
        JOIN matches_played mp ON mp.club_id = lm.club_id
        JOIN gold.dim_clubs c ON c.club_id = lm.club_id
        WHERE lm.rn = 1
        ORDER BY lm.position
    """
    standings_df = run_query(standings_sql, params={"cid": comp_id, "season": dash_season_sel})

    golden_boot_sql = f"""
        SELECT {PLAYER_NAME_EXPR} AS player, SUM(f.goals) AS goals
        FROM gold.fact_appearances f
        JOIN gold.dim_players p ON p.player_id = f.player_id
        WHERE f.competition_id = %(cid)s AND f.season = %(season)s
          AND {PLAYER_NAME_EXPR} <> ''
        GROUP BY player
        ORDER BY goals DESC
        LIMIT 1
    """
    gb_df = run_query(golden_boot_sql, params={"cid": comp_id, "season": dash_season_sel})

    top_assist_sql = f"""
        SELECT {PLAYER_NAME_EXPR} AS player, SUM(f.assists) AS assists
        FROM gold.fact_appearances f
        JOIN gold.dim_players p ON p.player_id = f.player_id
        WHERE f.competition_id = %(cid)s AND f.season = %(season)s
          AND {PLAYER_NAME_EXPR} <> ''
        GROUP BY player
        ORDER BY assists DESC
        LIMIT 1
    """
    top_assist_df = run_query(top_assist_sql, params={"cid": comp_id, "season": dash_season_sel})

    c1, c2, c3 = st.columns(3)
    with c1:
        if not standings_df.empty:
            st.metric("🏆 Winner", standings_df.iloc[0]["club"])
        else:
            st.metric("🏆 Winner", "No data")
    with c2:
        if not gb_df.empty:
            st.metric("⚽ Top Scorer", gb_df.iloc[0]["player"], f"{int(gb_df.iloc[0]['goals'])} goals")
        else:
            st.metric("⚽ Top Scorer", "No data")
    with c3:
        if not top_assist_df.empty:
            st.metric("🎯 Top Assist", top_assist_df.iloc[0]["player"], f"{int(top_assist_df.iloc[0]['assists'])} assists")
        else:
            st.metric("🎯 Top Assist", "No data")

    with st.expander(f"Full {dash_season_sel} Standings"):
        if not standings_df.empty:
            standings_display = standings_df[["club", "matches_played"]].reset_index(drop=True)
            standings_display.index = standings_display.index + 1
            standings_display.index.name = "Pos"
            standings_display = standings_display.rename(columns={"matches_played": "Matches Played"})
            st.dataframe(standings_display, width="stretch")
        else:
            st.info("No standings data.")

    st.divider()

    # ---- Position by matchweek -- one line per club, showing where they
    # sat in the table after each of their own matches. "Matchweek" here is
    # each club's own match sequence number (their Nth match that season),
    # not a calendar-aligned gameweek -- close enough for a round-robin
    # league, but worth knowing if a judge asks about exact alignment.
    trajectory_sql = """
        WITH club_matches AS (
            SELECT home_club_id AS club_id, home_club_position AS position, date
            FROM silver.games
            WHERE competition_id = %(cid)s AND season = %(season)s
            UNION ALL
            SELECT away_club_id AS club_id, away_club_position AS position, date
            FROM silver.games
            WHERE competition_id = %(cid)s AND season = %(season)s
        ),
        numbered AS (
            SELECT club_id, position, date,
                   ROW_NUMBER() OVER (PARTITION BY club_id ORDER BY date) AS matchweek
            FROM club_matches
            WHERE position IS NOT NULL
        )
        SELECT n.matchweek, c.name AS club, n.position
        FROM numbered n
        JOIN gold.dim_clubs c ON c.club_id = n.club_id
        ORDER BY n.matchweek, n.position
    """
    trajectory_df = run_query(trajectory_sql, params={"cid": comp_id, "season": dash_season_sel})
    if not trajectory_df.empty:
        st.subheader(f"League Position by Matchweek — {dash_season_sel}")
        fig = px.line(
            trajectory_df, x="matchweek", y="position", color="club",
            markers=True,
        )
        fig.update_layout(
            xaxis_title="Matchweek", yaxis_title="League Position",
            yaxis=dict(autorange="reversed", dtick=1),  # position 1 at top
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No position-by-matchweek data available for this season.")


# ============================================================
# TAB 2 -- Players (single-select season/league, position leaderboards)
# ============================================================
with tab_players:
    st.subheader("Player Stats Explorer")

    # Defaults: Premier League, latest season overall
    default_comp_id = "GB1"
    latest_season_default_df = run_query(
        "SELECT MAX(season) AS latest FROM gold.fact_appearances"
    )
    default_season = int(latest_season_default_df["latest"].iloc[0])

    f1, f2, f3 = st.columns(3)
    with f1:
        stat_type = st.radio("Stat", ["Goals", "Assists"], key="p_stat")
    with f2:
        season_options = sorted(seasons_df["season"].tolist(), reverse=True)
        season_sel = st.selectbox(
            "Season",
            options=season_options,
            index=season_options.index(default_season) if default_season in season_options else 0,
            key="p_season",
        )
    with f3:
        league_options = competitions_df["name"].tolist()
        default_league_name = competitions_df.loc[
            competitions_df["competition_id"] == default_comp_id, "name"
        ].iloc[0]
        league_sel = st.selectbox(
            "League",
            options=league_options,
            index=league_options.index(default_league_name),
            key="p_league",
        )

    league_comp_id = competitions_df.loc[
        competitions_df["name"] == league_sel, "competition_id"
    ].iloc[0]

    stat_col = "goals" if stat_type == "Goals" else "assists"

    players_sql = f"""
        SELECT
            {PLAYER_NAME_EXPR} AS player,
            p.position,
            c.name AS club,
            SUM(f.{stat_col}) AS total
        FROM gold.fact_appearances f
        JOIN gold.dim_players p ON p.player_id = f.player_id
        LEFT JOIN gold.dim_clubs c ON c.club_id = f.club_id
        WHERE {PLAYER_NAME_EXPR} <> ''
          AND f.season = %(season)s
          AND f.competition_id = %(comp_id)s
        GROUP BY player, p.position, c.name
        HAVING SUM(f.{stat_col}) > 0
        ORDER BY total DESC
        LIMIT 50
    """
    players_result = run_query(
        players_sql, params={"season": season_sel, "comp_id": league_comp_id}
    )

    st.markdown(f"**{league_sel} — {season_sel} — Top 50 by {stat_type.lower()}**")

    view_table, view_chart = st.columns(2)
    with view_table:
        st.markdown("*Table view*")
        if not players_result.empty:
            st.dataframe(players_result, hide_index=True, width="stretch", height=500)
        else:
            st.info("No players match this league/season.")

    with view_chart:
        st.markdown("*Leaderboard view (top 15)*")
        if not players_result.empty:
            chart_df = players_result.head(15)
            fig = px.bar(chart_df, x="total", y="player", orientation="h",
                         hover_data=["position", "club"])
            fig.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No players match this league/season.")

    # ---- Position leaderboards: top 5 by chosen stat, per position ----
    # scoped to the same league + season + stat_type selected above
    st.divider()
    st.markdown(f"### Top {stat_type} by Position")

    pos_cols = st.columns(4)
    for i, pos in enumerate(POSITIONS_FOR_BOXES):
        pos_sql = f"""
            SELECT {PLAYER_NAME_EXPR} AS player, SUM(f.{stat_col}) AS {stat_col}
            FROM gold.fact_appearances f
            JOIN gold.dim_players p ON p.player_id = f.player_id
            WHERE f.season = %(season)s
              AND f.competition_id = %(comp_id)s
              AND p.position = %(pos)s
              AND {PLAYER_NAME_EXPR} <> ''
            GROUP BY player
            HAVING SUM(f.{stat_col}) > 0
            ORDER BY {stat_col} DESC
            LIMIT 5
        """
        pos_df = run_query(
            pos_sql, params={"season": season_sel, "comp_id": league_comp_id, "pos": pos}
        )
        with pos_cols[i]:
            st.markdown(f"**{pos}**")
            if not pos_df.empty:
                pos_display = pos_df.reset_index(drop=True)
                pos_display.index = pos_display.index + 1
                st.dataframe(pos_display, width="stretch", hide_index=False)
            else:
                st.info("No data")

# ============================================================
# TAB 3 -- Clubs (competition -> club cascade, + season filter)
# ============================================================
with tab_clubs:
    st.subheader("Club Explorer")

    fc1, fc2, fc3 = st.columns(3)

    with fc1:
        # Default to the first of the top-5 leagues if present, else first competition overall
        default_comp_names = competitions_df.loc[
            competitions_df["competition_id"].isin(DEFAULT_TOP5_IDS), "name"
        ].tolist()
        comp_options = competitions_df["name"].tolist()
        default_index = comp_options.index(default_comp_names[0]) if default_comp_names else 0
        club_league_choice = st.selectbox(
            "Competition", options=comp_options, index=default_index, key="club_league_pick"
        )
        club_comp_id = competitions_df.loc[
            competitions_df["name"] == club_league_choice, "competition_id"
        ].iloc[0]

    with fc2:
        # Sourced from silver.games rather than gold.dim_clubs.competition_id --
        # dim_clubs.competition_id is each club's *home domestic league*, so a
        # continental competition like the Champions League has zero clubs whose
        # home league equals 'CL'. Querying who actually played in this
        # competition (via games) works for both domestic leagues and cups.
        clubs_in_league_df = run_query(
            """
            SELECT DISTINCT c.club_id, c.name
            FROM gold.dim_clubs c
            WHERE c.club_id IN (
                SELECT home_club_id FROM silver.games WHERE competition_id = %(cid)s
                UNION
                SELECT away_club_id FROM silver.games WHERE competition_id = %(cid)s
            )
            ORDER BY c.name
            """,
            params={"cid": club_comp_id},
        )
        if clubs_in_league_df.empty:
            st.warning("No clubs found for this competition.")
            club_id = None
        else:
            club_choice = st.selectbox(
                "Club", options=clubs_in_league_df["name"].tolist(), key="club_pick"
            )
            club_id = int(clubs_in_league_df.loc[clubs_in_league_df["name"] == club_choice, "club_id"].iloc[0])

    with fc3:
        if club_id is not None:
            latest_club_df = run_query(
                "SELECT MAX(season) AS latest FROM gold.fact_appearances WHERE club_id = %(cid)s",
                params={"cid": club_id},
            )
            latest_club_season = (
                int(latest_club_df["latest"].iloc[0])
                if not latest_club_df.empty and latest_club_df["latest"].iloc[0] is not None
                else None
            )
        else:
            latest_club_season = None

        season_options = sorted(seasons_df["season"].tolist(), reverse=True)
        club_season_sel = st.selectbox(
            "Season",
            options=season_options,
            index=season_options.index(latest_club_season) if latest_club_season in season_options else 0,
            key="club_season_pick",
        )

    if club_id is not None:
        # ---- Club info: stadium name + manager are pulled per-season from
        # silver.games (which has both fields per match) rather than
        # gold.dim_clubs, so they update correctly when the season changes.
        # dim_clubs.coach_name/stadium_name are frozen "current" snapshots --
        # not season-accurate (no history tracking, per the FK-nulling /
        # SCD Type 2 limitation discussed elsewhere). Capacity has no
        # per-match equivalent in games, so it stays sourced from dim_clubs
        # and is labeled "current" rather than season-specific.
        season_info_sql = """
            SELECT stadium, home_club_manager_name AS manager
            FROM silver.games
            WHERE home_club_id = %(cid)s AND season = %(season)s AND competition_id = %(comp_id)s
            ORDER BY date DESC
            LIMIT 1
        """
        season_info_df = run_query(
            season_info_sql, params={"cid": club_id, "season": club_season_sel, "comp_id": club_comp_id}
        )
        capacity_df = run_query(
            "SELECT stadium_seats FROM gold.dim_clubs WHERE club_id = %(cid)s",
            params={"cid": club_id},
        )

        st.markdown(f"### {club_choice}")
        info_c1, info_c2, info_c3 = st.columns(3)
        if not season_info_df.empty:
            row = season_info_df.iloc[0]
            info_c1.metric(f"Stadium ({club_season_sel})", row["stadium"] or "Unknown")
            info_c3.metric(f"Manager ({club_season_sel})", row["manager"] or "Unknown")
        else:
            info_c1.metric(f"Stadium ({club_season_sel})", "No match data")
            info_c3.metric(f"Manager ({club_season_sel})", "No match data")

        if not capacity_df.empty and capacity_df.iloc[0]["stadium_seats"] is not None:
            info_c2.metric("Capacity (current)", f"{int(capacity_df.iloc[0]['stadium_seats']):,}")
        else:
            info_c2.metric("Capacity (current)", "Unknown")

        # ---- Attendance by season -- home matches only, since attendance
        # reflects crowd size at THIS club's own stadium, not matches they
        # played away. Sourced from silver.games (Gold has no attendance fact).
        # NULLs (e.g. 2020, behind-closed-doors matches) are excluded by AVG()
        # automatically -- shows as a gap in the chart, not a misleading zero.
        attendance_sql = """
            SELECT season, AVG(attendance) AS avg_attendance
            FROM silver.games
            WHERE home_club_id = %(cid)s AND attendance IS NOT NULL
            GROUP BY season
            ORDER BY season
        """
        attendance_df = run_query(attendance_sql, params={"cid": club_id})
        if not attendance_df.empty:
            st.markdown("#### Home Attendance by Season")
            fig = px.bar(attendance_df, x="season", y="avg_attendance")
            fig.update_layout(
                xaxis_title="Season", yaxis_title="Avg. Attendance",
                xaxis=dict(type="category"),
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No attendance data available for this club.")

        st.divider()

        st.markdown(f"### {club_choice} — {club_league_choice} — {club_season_sel} Season")

        # Filtered by club_comp_id too -- without it, a player's goals/assists
        # from every competition they played that club_id in (e.g. a club that
        # appears in both a domestic league and a cup) would get mixed together.
        club_stats_sql = f"""
            SELECT {PLAYER_NAME_EXPR} AS player, SUM(f.goals) AS goals, SUM(f.assists) AS assists
            FROM gold.fact_appearances f
            JOIN gold.dim_players p ON p.player_id = f.player_id
            WHERE f.club_id = %(cid)s
              AND f.competition_id = %(comp_id)s
              AND f.season = %(season)s
              AND {PLAYER_NAME_EXPR} <> ''
            GROUP BY player
        """
        club_stats_df = run_query(
            club_stats_sql,
            params={"cid": club_id, "comp_id": club_comp_id, "season": club_season_sel},
        )

        st.markdown("#### Top Scorers")
        scorers_df = club_stats_df[club_stats_df["goals"] > 0].sort_values(
            "goals", ascending=False
        ).head(15)
        scorers_table, scorers_chart = st.columns(2)
        with scorers_table:
            if not scorers_df.empty:
                st.dataframe(
                    scorers_df[["player", "goals"]].reset_index(drop=True),
                    hide_index=True, width="stretch",
                )
            else:
                st.info("No scoring data for this club in this competition/season.")
        with scorers_chart:
            if not scorers_df.empty:
                fig = px.bar(scorers_df, x="goals", y="player", orientation="h",
                             hover_data=["assists"])
                fig.update_layout(yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig, width="stretch")

        st.divider()

        st.markdown("#### Top Assists")
        assists_df = club_stats_df[club_stats_df["assists"] > 0].sort_values(
            "assists", ascending=False
        ).head(15)
        assists_table, assists_chart = st.columns(2)
        with assists_table:
            if not assists_df.empty:
                st.dataframe(
                    assists_df[["player", "assists"]].reset_index(drop=True),
                    hide_index=True, width="stretch",
                )
            else:
                st.info("No assist data for this club in this competition/season.")
        with assists_chart:
            if not assists_df.empty:
                fig = px.bar(assists_df, x="assists", y="player", orientation="h",
                             hover_data=["goals"])
                fig.update_layout(yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig, width="stretch")