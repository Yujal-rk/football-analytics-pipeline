"""
football_pipeline_dag.py
-------------------------
Airflow DAG for the full Bronze -> Silver -> Gold football pipeline.

DB_HOST is overridden to host.docker.internal for every task, since
these bash commands run inside the Airflow container, where "localhost"
refers to the container itself, not the Windows host machine where
Postgres (football_db) actually runs.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.task_group import TaskGroup

PROJECT_DIR = "/opt/airflow/project"

TASK_ENV = {"DB_HOST": "host.docker.internal"}

default_args = {
    "owner": "data-eng-student",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="football_pipeline",
    description="Bronze -> Silver -> Gold pipeline for the Transfermarkt player-performance project",
    default_args=default_args,
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["football", "final-project"],
) as dag:

    with TaskGroup("bronze_loads") as bronze_loads:
        BashOperator(
            task_id="load_competitions",
            bash_command=f"cd {PROJECT_DIR}/bronze && python load_competitions.py",
            env=TASK_ENV, append_env=True,
        )
        BashOperator(
            task_id="load_clubs",
            bash_command=f"cd {PROJECT_DIR}/bronze && python load_clubs.py",
            env=TASK_ENV, append_env=True,
        )
        BashOperator(
            task_id="load_players",
            bash_command=f"cd {PROJECT_DIR}/bronze && python load_players.py",
            env=TASK_ENV, append_env=True,
        )
        BashOperator(
            task_id="load_games",
            bash_command=f"cd {PROJECT_DIR}/bronze && python load_games.py",
            env=TASK_ENV, append_env=True,
        )
        BashOperator(
            task_id="load_appearances",
            bash_command=f"cd {PROJECT_DIR}/bronze && python load_appearances.py",
            env=TASK_ENV, append_env=True,
        )

    silver_migration = BashOperator(
        task_id="silver_migration",
        bash_command=f"cd {PROJECT_DIR}/silver && python migrate_to_silver.py",
        env=TASK_ENV, append_env=True,
        trigger_rule="all_success",
    )

    gold_pipeline = BashOperator(
        task_id="gold_pipeline",
        bash_command=f"cd {PROJECT_DIR}/gold && python pipeline.py",
        env=TASK_ENV, append_env=True,
        trigger_rule="all_success",
    )

    bronze_loads >> silver_migration >> gold_pipeline