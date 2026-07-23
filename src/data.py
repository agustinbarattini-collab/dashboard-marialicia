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


# Cultivos (codigo Activ) excluidos del calculo de superficie fisica sembrada:
# S2DA se siembra sobre la misma superficie que el cultivo de 1ra (doble
# cultivo); GAN, VI, MOHA y SG se excluyen a pedido (no son agricultura de
# los cultivos principales que se quiere ver en esta evolucion).
CULTIVOS_EXCLUIDOS_AREA = {"S2DA", "GAN", "VI", "MOHA", "SG"}


def area_sembrada(df: pd.DataFrame, by: str = "Campo") -> pd.DataFrame:
    siembra = df[
        (df["Tipo_norm"] == "SIEMBRA") & (~df["Activ_norm"].isin(CULTIVOS_EXCLUIDOS_AREA))
    ]
    return (
        siembra.groupby(["Campaña", by], as_index=False)["Sup"]
        .sum()
        .rename(columns={"Sup": "Superficie sembrada (ha)"})
    )


def rendimiento(df: pd.DataFrame, by: list[str] = ("Campaña", "Campo", "Cultivo")) -> pd.DataFrame:
    """Rendimiento ponderado por superficie: sum(Dosis*Sup) / sum(Sup)."""
    prod_labor_excluido = df["Prod_labor"].str.lower().str.contains("flete|seguro", regex=True)
    rinde = df[
        (df["c_norm"] == "P") & (~prod_labor_excluido) & df["Sup"].notna() & (df["Sup"] > 0) & df["Dosis"].notna()
    ].copy()
    rinde["_ponderado"] = rinde["Dosis"] * rinde["Sup"]

    grouped = rinde.groupby(list(by), as_index=False).agg(
        _sum_ponderado=("_ponderado", "sum"),
        _sum_sup=("Sup", "sum"),
        Registros=("Dosis", "count"),
    )
    grouped["Rendimiento (t/ha)"] = grouped["_sum_ponderado"] / grouped["_sum_sup"]
    return grouped.drop(columns=["_sum_ponderado", "_sum_sup"])


def rendimiento_semaforo(df: pd.DataFrame) -> pd.DataFrame:
    """Rendimiento de cada campaña vs. el promedio historico ponderado del
    mismo cultivo (todas las campañas), como indice (%)."""
    por_campana = rendimiento(df, by=("Campaña", "Cultivo"))
    promedio_historico = rendimiento(df, by=("Cultivo",)).rename(
        columns={"Rendimiento (t/ha)": "Promedio histórico (t/ha)"}
    )[["Cultivo", "Promedio histórico (t/ha)"]]

    resultado = por_campana.merge(promedio_historico, on="Cultivo")
    resultado["Índice (%)"] = (
        resultado["Rendimiento (t/ha)"] / resultado["Promedio histórico (t/ha)"] * 100
    )
    return resultado
