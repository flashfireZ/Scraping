import requests
import pandas as pd
from datetime import datetime, timedelta
import os
import pickle

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# ===================== CONFIG =====================
DATASET_API = "https://www.data.gouv.fr/api/1/datasets/les-offres-diffusees-sur-choisir-le-service-public/"

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.pickle"

# ===================== AUTH DRIVE =====================
def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(creds, token)

    return build("drive", "v3", credentials=creds)

def upload_to_drive(file_path):
    service = get_drive_service()
    file_metadata = {"name": os.path.basename(file_path)}
    media = MediaFileUpload(
        file_path,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        resumable=True
    )
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()

    print(f"✅ Upload Drive réussi ! ID : {file.get('id')}")

# ===================== TÉLÉCHARGEMENT CSV =====================
print("📥 Récupération du dataset officiel (toutes les offres)...")
meta = requests.get(DATASET_API).json()

csv_url = None
latest_date = ""

for res in meta.get("resources", []):
    if res.get("format") == "csv" and "offres-datagouv" in res.get("title", "").lower():
        if res.get("last_modified", "") > latest_date:
            csv_url = res["url"]
            latest_date = res.get("last_modified", "")
            print(f"✅ CSV trouvé : {res.get('title')} (mis à jour {latest_date})")
            print(f"   URL : {csv_url}")

if not csv_url:
    print("❌ Impossible de trouver le CSV")
    exit()

# ===================== LECTURE CSV ROBUSTE =====================
print("📊 Lecture du CSV (25,9 Mo)...")

df = pd.read_csv(
    csv_url,
    sep=';',
    encoding='utf-8-sig',
    on_bad_lines='skip',   # ignore les lignes cassées
    quotechar='"',
    engine='python',       # robuste pour les longues descriptions
    dtype=str              # évite les erreurs de type
)

print(f"✅ {len(df):,} offres chargées du dataset officiel.")
print("Colonnes disponibles :", list(df.columns))

# ===================== FILTRAGE BIOLOGIE =====================
keyword = "biologie"

df_filtered = df[
    df.apply(lambda row: row.astype(str).str.contains(keyword, case=False, na=False)).any(axis=1)
].copy()

print(f"🔬 {len(df_filtered)} offres contiennent le mot-clé '{keyword}'.")

# ===================== FILTRE 7 DERNIERS JOURS =====================
date_cols = [col for col in df.columns if any(x in col.lower() for x in ["date", "publi", "creation", "debut"])]

date_col = date_cols[0] if date_cols else None

if date_col:
    print(f"📅 Colonne date détectée : {date_col}")

    df_filtered[date_col] = pd.to_datetime(df_filtered[date_col], errors="coerce")
    date_limit = datetime.now() - timedelta(days=7)

    df_filtered = df_filtered[df_filtered[date_col] >= date_limit]

    print(f"⏳ Filtre 7 derniers jours appliqué ({len(df_filtered)} offres restantes).")
else:
    print("⚠️ Aucune colonne date trouvée, impossible de filtrer par date.")

# ===================== TRI + EXPORT =====================
if date_col and date_col in df_filtered.columns:
    df_filtered = df_filtered.sort_values(by=date_col, ascending=False)

print(f"📌 Total final : {len(df_filtered)} offres après filtrage complet.")

if not df_filtered.empty:
    excel_filename = "offres_service_public_biologie_filtrees.xlsx"
    df_filtered.to_excel(excel_filename, index=False)
    print(f"📊 Excel créé : {excel_filename}")

    upload_to_drive(excel_filename)
else:
    print("Aucune offre ne correspond aux critères.")

print("🎉 Terminé !")
