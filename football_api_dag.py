from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import http.client
import json
import pandas as pd
import boto3
import os
from dotenv import load_dotenv


load_dotenv()  # Charge le fichier .env
# Accès aux variables
# Paramètres API
API_HOST = "v3.football.api-sports.io"
API_KEY = os.getenv("API_KEY")
LEAGUE_ID = 39
SEASON = 2022  # (payant pour la saison en cours)

# Paramètres S3
BUCKET_NAME = os.getenv("BUCKET_NAME")
S3_KEY = 'football_data/standings_data.csv'

# Fonctions pour les tâches
def is_football_api_ready():
    try:
        conn = http.client.HTTPSConnection(API_HOST)
        headers = {
            'x-rapidapi-host': API_HOST,
            'x-rapidapi-key': API_KEY
        }
        conn.request("GET", f"/status", headers=headers)
        res = conn.getresponse()
        if res.status == 200:
            print("API is ready")
        else:
            raise Exception("API is not ready")
    except Exception as e:
        raise Exception(f"API check failed: {e}")

def extract_data():
    conn = http.client.HTTPSConnection(API_HOST)
    headers = {
        'x-rapidapi-host': API_HOST,
        'x-rapidapi-key': API_KEY
    }
    conn.request("GET", f"/standings?league={LEAGUE_ID}&season={SEASON}", headers=headers)
    res = conn.getresponse()
    data = res.read()
    json_data = json.loads(data.decode("utf-8"))
    return json_data

def transform_data(**context):
    json_data = context['ti'].xcom_pull(task_ids='extract_data')
    standings_data = json_data['response'][0]['league']['standings'][0]
    df = pd.json_normalize(standings_data, sep="_")
    df.to_csv('/tmp/standings_data.csv', index=False)
    print("Data transformed and saved to /tmp/standings_data.csv")

def save_to_s3():
    s3_client = boto3.client('s3')
    s3_client.upload_file('/tmp/standings_data.csv', BUCKET_NAME, S3_KEY)
    print(f"File uploaded to S3: s3://{BUCKET_NAME}/{S3_KEY}")

# Définition du DAG
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2023, 10, 27),
    'retries': 1,
    'retry_delay': timedelta(minutes=5)
}

with DAG('football_api_pipeline', default_args=default_args, schedule_interval=timedelta(days=1)) as dag:
    is_football_api_ready_task = PythonOperator(
        task_id='is_football_api_ready',
        python_callable=is_football_api_ready
    )

    extract_data_task = PythonOperator(
        task_id='extract_data',
        python_callable=extract_data
    )

    transform_data_task = PythonOperator(
        task_id='transform_data',
        python_callable=transform_data,
        provide_context=True
    )

    save_to_s3_task = PythonOperator(
        task_id='save_to_s3',
        python_callable=save_to_s3
    )

    # Dépendances entre les tâches
    is_football_api_ready_task >> extract_data_task >> transform_data_task >> save_to_s3_task
