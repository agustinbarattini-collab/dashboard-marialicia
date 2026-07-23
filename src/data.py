import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1u1HNqI0CQasHj-keHOzWuBIiIzQlkZNKWvM8yhlP2NE"
TAB_NAME = "BASE"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Codigo de Activ -> nombre de cultivo para mostrar en los graficos.
ACTIV_MAP = {
    "T": "Trigo",
    "S1": "Soja 1ª",
    "S2DA": "Soja 2ª",
    "M": "Maíz",
    "M 2DA": "Maíz 2ª",
    "MT": "Maíz Tardío",
    "M SILO": "Maíz Silo",
    "G": "Girasol",
    "SG": "Sorgo Granífero",
    "MOHA": "Moha",
    "GAN": "Ganadería",
    "P RG": "Pastura/Raigrás",
    "VI": "Vicia",
}


@st.cache_resource
def _get_client() -> gspread.Client:
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=SCOPES
    )
    return gspread.authorize(creds)


@st.cache_data(ttl=600, show_spinner="Cargando datos de la planilla...")
def load_base_df() -> pd.DataFrame:
    ws = _get_client().open_by_key(SPREADSHEET_ID).worksheet(TAB_NAME)
    records = ws.get_all_records(value_render_option="UNFORMATTED_VALUE")
    df = pd.DataFrame(records)

    df["Campaña"] = df["Campaña"].astype(str).str.strip()
    df["Campo"] = df["Campo"].astype(str).str.strip().str.title()
    df["Tipo_norm"] = df["Tipo"].astype(str).str.strip().str.upper()
    df["c_norm"] = df["c"].astype(str).str.strip().str.upper()
    df["Prod_labor"] = df["Prod_labor"].astype(str).str.strip()
    df["Activ_norm"] = df["Activ"].astype(str).str.strip().str.upper()
    df["Cultivo"] = df["Activ_norm"].map(ACTIV_MAP).fillna(df["Activ_norm"])

    df["Sup"] = pd.to_numeric(df["Sup"], errors="coerce")
    df["Dosis"] = pd.to_numeric(df["Dosis"], errors="coerce")

    return df


def area_sembrada(df: pd.DataFrame, by: str = "Campo") -> pd.DataFrame:
    # La Soja 2da se siembra sobre la misma superficie fisica que el cultivo
    # de 1ra (doble cultivo), asi que se excluye para no duplicar hectareas.
    siembra = df[(df["Tipo_norm"] == "SIEMBRA") & (df["Activ_norm"] != "S2DA")]
    return (
        siembra.groupby(["Campaña", by], as_index=False)["Sup"]
        .sum()
        .rename(columns={"Sup": "Superficie sembrada (ha)"})
    )


def rendimiento(df: pd.DataFrame) -> pd.DataFrame:
    prod_labor_excluido = df["Prod_labor"].str.lower().str.contains("flete|seguro", regex=True)
    rinde = df[(df["c_norm"] == "P") & (~prod_labor_excluido)]
    return (
        rinde.groupby(["Campaña", "Campo", "Cultivo"], as_index=False)
        .agg(**{"Rendimiento (t/ha)": ("Dosis", "mean"), "Registros": ("Dosis", "count")})
    )
