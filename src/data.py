import gspread
import numpy as np
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

# Unifica categorias de Tipo (columna N) que representan el mismo concepto
# o que se agrupan a pedido bajo un nombre comun.
TIPO_MAP = {
    "ALQUILER": "Alquiler",
    "ALQUILERES": "Alquiler",
    "FERTILIZACION": "Labores",
    "PULVERIZACION": "Labores",
    "SIEMBRA": "Labores",
    "TAREA": "Labores",
    "LABOR": "Labores",
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
    df["Tipo_display"] = df["Tipo_norm"].map(TIPO_MAP).fillna(df["Tipo_norm"])
    df["c_norm"] = df["c"].astype(str).str.strip().str.upper()
    df["Prod_labor"] = df["Prod_labor"].astype(str).str.strip()
    df["Activ_norm"] = df["Activ"].astype(str).str.strip().str.upper()
    df["Cultivo"] = df["Activ_norm"].map(ACTIV_MAP).fillna(df["Activ_norm"])
    df["Accion_norm"] = df["Accion"].astype(str).str.strip().str.upper()

    df["Sup"] = pd.to_numeric(df["Sup"], errors="coerce")
    df["Dosis"] = pd.to_numeric(df["Dosis"], errors="coerce")
    df["Total u$"] = pd.to_numeric(df["Total u$"], errors="coerce")
    df["Prec_Unitario"] = pd.to_numeric(df["Prec_Unitario"], errors="coerce")

    return df


# Cultivos (codigo Activ) excluidos del calculo de superficie fisica sembrada:
# S2DA y M 2DA se siembran sobre la misma superficie que el cultivo de 1ra
# (doble cultivo); GAN, VI, MOHA y SG se excluyen a pedido (no son
# agricultura de los cultivos principales que se quiere ver en esta evolucion).
CULTIVOS_EXCLUIDOS_AREA = {"S2DA", "M 2DA", "GAN", "VI", "MOHA", "SG"}


def area_sembrada(df: pd.DataFrame, by: str = "Campo") -> pd.DataFrame:
    # Ademas de Tipo = Siembra, se exige Accion = Siembra: hay filas con
    # Tipo = Siembra pero Accion de otra labor (ej. "Labor"/Rolo picador)
    # mal etiquetadas, que duplicarian la superficie si no se filtran.
    siembra = df[
        (df["Tipo_norm"] == "SIEMBRA")
        & (df["Accion_norm"] == "SIEMBRA")
        & (~df["Activ_norm"].isin(CULTIVOS_EXCLUIDOS_AREA))
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


def costo_total(df: pd.DataFrame, by: str = "Campo") -> pd.DataFrame:
    """Costo total (Total u$) en filas con columna c = 'v'."""
    gastos = df[df["c_norm"] == "V"]
    return (
        gastos.groupby(["Campaña", by], as_index=False)["Total u$"]
        .sum()
        .rename(columns={"Total u$": "Costo total (u$)"})
    )


def costo_por_tipo_por_ha(df: pd.DataFrame, by: str = "Campo") -> pd.DataFrame:
    """Costo por Tipo (columna N), en filas con c = 'v', dividido por las
    hectáreas cosechadas (Sup en filas con Tipo = Cosecha), agrupado por
    Campaña y `by` (Campo o Cultivo)."""
    cosechada = (
        df[df["Tipo_norm"] == "COSECHA"]
        .groupby(["Campaña", by], as_index=False)["Sup"]
        .sum()
        .rename(columns={"Sup": "Has cosechadas"})
    )

    costo_tipo = (
        df[df["c_norm"] == "V"]
        .groupby(["Campaña", by, "Tipo_display"], as_index=False)["Total u$"]
        .sum()
        .rename(columns={"Total u$": "Costo total (u$)", "Tipo_display": "Tipo"})
    )

    resultado = costo_tipo.merge(cosechada, on=["Campaña", by])
    resultado = resultado[resultado["Has cosechadas"] > 0]
    resultado["Costo por ha cosechada (u$/ha)"] = (
        resultado["Costo total (u$)"] / resultado["Has cosechadas"]
    )
    return resultado


def costo_por_tipo_por_tn(df: pd.DataFrame, by: str = "Campo") -> pd.DataFrame:
    """Costo por ha cosechada (por Tipo) dividido por el rendimiento
    (t/ha) del mismo periodo: costo por tonelada producida."""
    costo_ha = costo_por_tipo_por_ha(df, by=by)
    rinde = rendimiento(df, by=("Campaña", by))[["Campaña", by, "Rendimiento (t/ha)"]]

    resultado = costo_ha.merge(rinde, on=["Campaña", by])
    resultado = resultado[resultado["Rendimiento (t/ha)"] > 0]
    resultado["Costo por Tn producida (u$/t)"] = (
        resultado["Costo por ha cosechada (u$/ha)"] / resultado["Rendimiento (t/ha)"]
    )
    return resultado


def ingresos_rendimiento_precio(df: pd.DataFrame, by: list[str] = ("Campaña", "Cultivo")) -> pd.DataFrame:
    """Para filas con c = 'P' (excluyendo Flete en Prod_labor): Rendimiento
    (Dosis) y Total u$ / Sup, ambos ponderados por superficie."""
    excluido = df["Prod_labor"].str.lower().str.contains("flete", regex=False)
    base = df[
        (df["c_norm"] == "P")
        & (~excluido)
        & df["Sup"].notna()
        & (df["Sup"] > 0)
        & df["Dosis"].notna()
        & df["Total u$"].notna()
    ].copy()
    base["_dosis_pond"] = base["Dosis"] * base["Sup"]

    grouped = base.groupby(list(by), as_index=False).agg(
        _sum_dosis_pond=("_dosis_pond", "sum"),
        _sum_sup=("Sup", "sum"),
        _sum_total_usd=("Total u$", "sum"),
        Registros=("Dosis", "count"),
    )
    grouped["Rendimiento (t/ha)"] = grouped["_sum_dosis_pond"] / grouped["_sum_sup"]
    grouped["Total u$ / Sup (u$/ha)"] = grouped["_sum_total_usd"] / grouped["_sum_sup"]
    return grouped.drop(columns=["_sum_dosis_pond", "_sum_sup", "_sum_total_usd"])


def precio_venta(df: pd.DataFrame, by: list[str] = ("Campaña", "Cultivo")) -> pd.DataFrame:
    """Precio de venta (Prec_Unitario) ponderado por Dosis, en filas con
    c = 'P', excluyendo Flete en Prod_labor."""
    excluido = df["Prod_labor"].str.lower().str.contains("flete", regex=False)
    base = df[
        (df["c_norm"] == "P") & (~excluido) & df["Dosis"].notna() & (df["Dosis"] > 0) & df["Prec_Unitario"].notna()
    ].copy()
    base["_precio_pond"] = base["Prec_Unitario"] * base["Dosis"]

    grouped = base.groupby(list(by), as_index=False).agg(
        _sum_precio_pond=("_precio_pond", "sum"),
        _sum_dosis=("Dosis", "sum"),
        Registros=("Dosis", "count"),
    )
    grouped["Precio de venta (u$/t)"] = grouped["_sum_precio_pond"] / grouped["_sum_dosis"]
    return grouped.drop(columns=["_sum_precio_pond", "_sum_dosis"])


def flete_por_tn(df: pd.DataFrame, by: list[str] = ("Campaña", "Cultivo")) -> pd.DataFrame:
    """Flete por tonelada, ponderado por toneladas, en filas de Flete
    (c = 'P', Prod_labor = Flete). En estas filas Dosis siempre vale 1
    (es un flag) y las toneladas reales estan en Sup (en negativo);
    Prec_Unitario ya viene expresado en u$/tonelada."""
    es_flete = df["Prod_labor"].str.lower().str.contains("flete", regex=False)
    base = df[
        (df["c_norm"] == "P") & es_flete & df["Prec_Unitario"].notna() & df["Sup"].notna()
    ].copy()
    base["_toneladas"] = base["Sup"].abs()
    base = base[base["_toneladas"] > 0]
    base["_flete_pond"] = base["Prec_Unitario"] * base["_toneladas"]

    grouped = base.groupby(list(by), as_index=False).agg(
        _sum_flete_pond=("_flete_pond", "sum"),
        _sum_toneladas=("_toneladas", "sum"),
    )
    grouped["Flete (u$/t)"] = grouped["_sum_flete_pond"] / grouped["_sum_toneladas"]
    return grouped.drop(columns=["_sum_flete_pond", "_sum_toneladas"])


def precio_semaforo(df: pd.DataFrame) -> pd.DataFrame:
    """Precio de venta de cada campaña vs. el promedio historico ponderado
    del mismo cultivo (todas las campañas), como indice (%)."""
    por_campana = precio_venta(df, by=("Campaña", "Cultivo"))
    promedio_historico = precio_venta(df, by=("Cultivo",)).rename(
        columns={"Precio de venta (u$/t)": "Promedio histórico (u$/t)"}
    )[["Cultivo", "Promedio histórico (u$/t)"]]

    resultado = por_campana.merge(promedio_historico, on="Cultivo")
    resultado["Índice (%)"] = (
        resultado["Precio de venta (u$/t)"] / resultado["Promedio histórico (u$/t)"] * 100
    )
    return resultado


def factor_ingreso(df: pd.DataFrame) -> pd.DataFrame:
    """Compara, por Campaña y Cultivo, el indice de Rendimiento vs. el
    indice de Precio de venta (ambos contra su promedio historico
    ponderado) para identificar que factor explica mejor el ingreso."""
    rend = rendimiento_semaforo(df)[["Campaña", "Cultivo", "Índice (%)"]].rename(
        columns={"Índice (%)": "Índice Rendimiento (%)"}
    )
    precio = precio_semaforo(df)[["Campaña", "Cultivo", "Índice (%)"]].rename(
        columns={"Índice (%)": "Índice Precio (%)"}
    )

    resultado = rend.merge(precio, on=["Campaña", "Cultivo"])
    dist_rend = (resultado["Índice Rendimiento (%)"] - 100).abs()
    dist_precio = (resultado["Índice Precio (%)"] - 100).abs()
    resultado["Factor dominante"] = pd.Series(
        ["Rendimiento" if r >= p else "Precio" for r, p in zip(dist_rend, dist_precio)]
    )
    return resultado


def ingreso_total(df: pd.DataFrame, by: str = "Campo") -> pd.DataFrame:
    """Ingreso total (Total u$) en filas con columna c = 'P'."""
    ingresos = df[df["c_norm"] == "P"]
    return (
        ingresos.groupby(["Campaña", by], as_index=False)["Total u$"]
        .sum()
        .rename(columns={"Total u$": "Ingreso total (u$)"})
    )


def margen(df: pd.DataFrame, by: str = "Campo") -> pd.DataFrame:
    """Margen = Ingreso total (c='P') - Costo total (c='v'), y Margen por
    hectarea sembrada (usando la misma superficie que area_sembrada)."""
    ing = ingreso_total(df, by=by)
    cos = costo_total(df, by=by)
    sup = area_sembrada(df, by=by)[["Campaña", by, "Superficie sembrada (ha)"]]

    resultado = ing.merge(cos, on=["Campaña", by], how="outer").merge(
        sup, on=["Campaña", by], how="outer"
    )
    resultado["Ingreso total (u$)"] = resultado["Ingreso total (u$)"].fillna(0)
    resultado["Costo total (u$)"] = resultado["Costo total (u$)"].fillna(0)
    resultado["Margen (u$)"] = resultado["Ingreso total (u$)"] - resultado["Costo total (u$)"]

    resultado = resultado[resultado["Superficie sembrada (ha)"] > 0]
    resultado["Margen (u$/ha)"] = resultado["Margen (u$)"] / resultado["Superficie sembrada (ha)"]
    return resultado


def resultado_por_ha_cosechada(
    df: pd.DataFrame, by: list[str] = ("Campaña", "Campo", "Cultivo")
) -> pd.DataFrame:
    """Ingreso neto, Costo y Resultado (Margen), todos por hectarea
    cosechada (Sup en filas con Tipo = Cosecha), a la granularidad `by`."""
    by = list(by)
    cosechada = (
        df[df["Tipo_norm"] == "COSECHA"]
        .groupby(by, as_index=False)["Sup"]
        .sum()
        .rename(columns={"Sup": "Has cosechadas"})
    )
    ing = (
        df[df["c_norm"] == "P"]
        .groupby(by, as_index=False)["Total u$"]
        .sum()
        .rename(columns={"Total u$": "Ingreso total (u$)"})
    )
    cos = (
        df[df["c_norm"] == "V"]
        .groupby(by, as_index=False)["Total u$"]
        .sum()
        .rename(columns={"Total u$": "Costo total (u$)"})
    )

    resultado = cosechada.merge(ing, on=by, how="left").merge(cos, on=by, how="left")
    resultado["Ingreso total (u$)"] = resultado["Ingreso total (u$)"].fillna(0)
    resultado["Costo total (u$)"] = resultado["Costo total (u$)"].fillna(0)
    resultado = resultado[resultado["Has cosechadas"] > 0]

    resultado["Ingreso neto (u$/ha)"] = resultado["Ingreso total (u$)"] / resultado["Has cosechadas"]
    resultado["Costo (u$/ha)"] = resultado["Costo total (u$)"] / resultado["Has cosechadas"]
    resultado["Resultado (u$/ha)"] = resultado["Ingreso neto (u$/ha)"] - resultado["Costo (u$/ha)"]
    return resultado


def costo_por_tipo_detalle(
    df: pd.DataFrame, by: list[str] = ("Campaña", "Campo", "Cultivo")
) -> pd.DataFrame:
    """Costo por Tipo (Total u$, c = 'v') por hectarea cosechada, a la
    granularidad `by`."""
    by = list(by)
    cosechada = (
        df[df["Tipo_norm"] == "COSECHA"]
        .groupby(by, as_index=False)["Sup"]
        .sum()
        .rename(columns={"Sup": "Has cosechadas"})
    )
    costo_tipo = (
        df[df["c_norm"] == "V"]
        .groupby(by + ["Tipo_display"], as_index=False)["Total u$"]
        .sum()
        .rename(columns={"Total u$": "Costo total (u$)", "Tipo_display": "Tipo"})
    )

    resultado = costo_tipo.merge(cosechada, on=by)
    resultado = resultado[resultado["Has cosechadas"] > 0]
    resultado["Costo por ha cosechada (u$/ha)"] = (
        resultado["Costo total (u$)"] / resultado["Has cosechadas"]
    )
    return resultado


def correlacion_costos_resultado(
    df: pd.DataFrame, by: list[str] = ("Campaña", "Campo", "Cultivo")
) -> pd.DataFrame:
    """Para cada Tipo de gasto (costo por ha cosechada), calcula la
    correlacion (Pearson) y el retorno marginal (pendiente de una
    regresion lineal simple) contra el Resultado (u$/ha) y contra el
    Rendimiento (t/ha), a traves de las observaciones (una por cada
    combinacion de `by`)."""
    by = list(by)
    resultado = resultado_por_ha_cosechada(df, by=by)[by + ["Resultado (u$/ha)"]]
    rinde = rendimiento(df, by=by)[by + ["Rendimiento (t/ha)"]]
    costo_detalle = costo_por_tipo_detalle(df, by=by)

    pivot = costo_detalle.pivot_table(
        index=by, columns="Tipo", values="Costo por ha cosechada (u$/ha)", fill_value=0
    ).reset_index()

    merged = pivot.merge(resultado, on=by, how="inner").merge(rinde, on=by, how="inner")
    tipos = [c for c in pivot.columns if c not in by]

    objetivos = [
        ("Resultado (u$/ha)", "Resultado"),
        ("Rendimiento (t/ha)", "Rendimiento"),
    ]

    filas = []
    for tipo in tipos:
        x = merged[tipo]
        if x.std() == 0:
            continue
        fila = {"Tipo": tipo, "Observaciones": len(merged)}
        valido = False
        for col_objetivo, etiqueta in objetivos:
            y = merged[col_objetivo]
            if y.std() == 0:
                continue
            fila[f"Correlación con {etiqueta}"] = x.corr(y)
            fila[f"Retorno marginal ({etiqueta})"] = np.polyfit(x, y, 1)[0]
            valido = True
        if valido:
            filas.append(fila)

    corr_df = pd.DataFrame(filas)
    if corr_df.empty:
        return corr_df
    return corr_df.reindex(
        corr_df["Correlación con Resultado"].abs().sort_values(ascending=False).index
    )


def indiferencia(df: pd.DataFrame, by: list[str] = ("Campaña", "Campo", "Cultivo")) -> pd.DataFrame:
    """Rinde y precio de indiferencia (los que harian Resultado = 0),
    manteniendo fijo el otro factor en su valor real observado, a la
    granularidad `by`. El precio se usa neto de Flete (el bruto sobre-
    estima lo que realmente se cobra por tonelada)."""
    by = list(by)
    resultado = resultado_por_ha_cosechada(df, by=by)
    rinde = rendimiento(df, by=by)[by + ["Rendimiento (t/ha)"]]
    precio = precio_venta(df, by=by)[by + ["Precio de venta (u$/t)"]].rename(
        columns={"Precio de venta (u$/t)": "Precio de venta Bruto (u$/t)"}
    )
    flete = flete_por_tn(df, by=by)

    merged = (
        resultado.merge(rinde, on=by, how="left")
        .merge(precio, on=by, how="left")
        .merge(flete, on=by, how="left")
    )
    merged["Flete (u$/t)"] = merged["Flete (u$/t)"].fillna(0)
    merged["Precio de venta Neto (u$/t)"] = (
        merged["Precio de venta Bruto (u$/t)"] - merged["Flete (u$/t)"]
    )

    con_precio = merged["Precio de venta Neto (u$/t)"] > 0
    merged.loc[con_precio, "Rinde de indiferencia (t/ha)"] = (
        merged.loc[con_precio, "Costo (u$/ha)"] / merged.loc[con_precio, "Precio de venta Neto (u$/t)"]
    )

    con_rinde = merged["Rendimiento (t/ha)"] > 0
    merged.loc[con_rinde, "Precio de indiferencia Neto (u$/t)"] = (
        merged.loc[con_rinde, "Costo (u$/ha)"] / merged.loc[con_rinde, "Rendimiento (t/ha)"]
    )
    merged["Precio de indiferencia Bruto (u$/t)"] = (
        merged["Precio de indiferencia Neto (u$/t)"] + merged["Flete (u$/t)"]
    )

    merged["Margen de seguridad rinde (%)"] = (
        (merged["Rendimiento (t/ha)"] - merged["Rinde de indiferencia (t/ha)"])
        / merged["Rendimiento (t/ha)"]
        * 100
    )
    merged["Margen de seguridad precio (%)"] = (
        (merged["Precio de venta Neto (u$/t)"] - merged["Precio de indiferencia Neto (u$/t)"])
        / merged["Precio de venta Neto (u$/t)"]
        * 100
    )
    return merged


# Orden de las filas fijas en la tabla de analisis por lote (los Tipos de
# gasto, que varian segun los datos, se insertan ordenados alfabeticamente
# entre ORDEN_INGRESO_NETO y ORDEN_GASTOS_TOTALES).
ORDEN_HAS = 0
ORDEN_INGRESO = {"Flete": 1, "GRANOS": 2, "SEGURO": 3}
ORDEN_INGRESO_NETO = 10
ORDEN_GASTOS_TOTALES = 900
ORDEN_MARGEN_NETO = 901
ORDEN_RENTABILIDAD = 902
ORDEN_RENDIMIENTO = 903
ORDEN_RINDE_INDIFERENCIA = 904
ORDEN_PRECIO_INDIFERENCIA = 905


def lote_tabla(
    df: pd.DataFrame, by: list[str] = ("Campo", "Cultivo"), has_excluye_solapados: bool = False
) -> pd.DataFrame:
    """Tabla de analisis por lote: Has cosechadas, desglose de Ingreso
    (Flete / GRANOS / SEGURO, segun Prod_labor) y de Gastos (por Tipo,
    sin unificar categorias), Ingreso Neto, Gastos totales, Margen Neto,
    Rentabilidad, Rendimiento y Rinde/Precio de indiferencia — todo por
    hectarea cosechada, a la granularidad `by` (debe incluir "Campo").

    Si `has_excluye_solapados` es True (usar cuando `by` no incluye
    Cultivo, ej. la columna "Total" de un Campo), las Has de cultivos de
    2da (Soja 2da, Maiz 2da, etc.) se excluyen del calculo de Has: esos
    cultivos se siembran sobre la misma superficie fisica que el cultivo
    de 1ra, y sumarlas duplicaria la superficie. El Ingreso y el Gasto de
    esos cultivos igual se incluyen en los totales; solo cambia el
    denominador (hectareas fisicas reales, no "hectareas-cultivo")."""
    by = list(by)

    cosecha = df[df["Tipo_norm"] == "COSECHA"]
    if has_excluye_solapados:
        cosecha = cosecha[~cosecha["Activ_norm"].isin(CULTIVOS_EXCLUIDOS_AREA)]
    has = cosecha.groupby(by, as_index=False)["Sup"].sum().rename(columns={"Sup": "Has"})
    has = has[has["Has"] > 0]
    if has.empty:
        return pd.DataFrame(columns=by + ["Métrica", "Etiqueta", "Valor", "Orden"])

    # --- Ingreso (c='P'), clasificado por Prod_labor en Flete/GRANOS/SEGURO ---
    ingresos = df[df["c_norm"] == "P"].copy()
    prod_lower = ingresos["Prod_labor"].str.lower()
    ingresos["Etiqueta"] = "GRANOS"
    ingresos.loc[prod_lower.str.contains("flete", na=False), "Etiqueta"] = "Flete"
    ingresos.loc[prod_lower.str.contains("seguro", na=False), "Etiqueta"] = "SEGURO"

    ingreso_tipo = (
        ingresos.groupby(by + ["Etiqueta"], as_index=False)["Total u$"]
        .sum()
        .rename(columns={"Total u$": "_total"})
    )
    # "Métrica" es la clave unica usada para pivotear (evita colisionar con
    # el Tipo de gasto "SEGURO", que es un concepto distinto).
    ingreso_tipo["Métrica"] = "ingreso:" + ingreso_tipo["Etiqueta"]
    ingreso_tipo["Orden"] = ingreso_tipo["Etiqueta"].map(ORDEN_INGRESO)

    # --- Gastos (c='v'), por Tipo crudo (sin unificar) ---
    gastos = df[df["c_norm"] == "V"]
    gasto_tipo = (
        gastos.groupby(by + ["Tipo_norm"], as_index=False)["Total u$"]
        .sum()
        .rename(columns={"Tipo_norm": "Etiqueta", "Total u$": "_total"})
    )
    gasto_tipo["Métrica"] = "gasto:" + gasto_tipo["Etiqueta"]
    tipos_gasto_orden = {t: 20 + i for i, t in enumerate(sorted(gasto_tipo["Etiqueta"].unique()))}
    gasto_tipo["Orden"] = gasto_tipo["Etiqueta"].map(tipos_gasto_orden)

    detalle = pd.concat([ingreso_tipo, gasto_tipo], ignore_index=True)
    detalle = detalle.merge(has, on=by, how="inner")
    detalle["Valor"] = detalle["_total"] / detalle["Has"]

    # --- Totales por seccion ---
    ingreso_neto = ingreso_tipo.groupby(by, as_index=False)["_total"].sum().merge(has, on=by)
    ingreso_neto["Valor"] = ingreso_neto["_total"] / ingreso_neto["Has"]
    ingreso_neto["Métrica"] = "Ingreso Neto"
    ingreso_neto["Etiqueta"] = "Ingreso Neto"
    ingreso_neto["Orden"] = ORDEN_INGRESO_NETO

    gastos_totales = gasto_tipo.groupby(by, as_index=False)["_total"].sum().merge(has, on=by)
    gastos_totales["Valor"] = gastos_totales["_total"] / gastos_totales["Has"]
    gastos_totales["Métrica"] = "Gastos totales"
    gastos_totales["Etiqueta"] = "Gastos totales"
    gastos_totales["Orden"] = ORDEN_GASTOS_TOTALES

    margen_neto = ingreso_neto[by + ["Valor"]].rename(columns={"Valor": "_ing"}).merge(
        gastos_totales[by + ["Valor"]].rename(columns={"Valor": "_cos"}), on=by
    )
    margen_neto["Valor"] = margen_neto["_ing"] - margen_neto["_cos"]
    margen_neto["Métrica"] = "Margen Neto"
    margen_neto["Etiqueta"] = "Margen Neto"
    margen_neto["Orden"] = ORDEN_MARGEN_NETO

    rentabilidad = margen_neto[by + ["Valor"]].rename(columns={"Valor": "_margen"}).merge(
        ingreso_neto[by + ["Valor"]].rename(columns={"Valor": "_ing"}), on=by
    )
    rentabilidad["Valor"] = (rentabilidad["_margen"] / rentabilidad["_ing"] * 100).where(
        rentabilidad["_ing"] != 0
    )
    rentabilidad["Métrica"] = "Rentabilidad (%)"
    rentabilidad["Etiqueta"] = "Rentabilidad (%)"
    rentabilidad["Orden"] = ORDEN_RENTABILIDAD

    # --- Rendimiento y rinde/precio de indiferencia ---
    rend = rendimiento(df, by=by)[by + ["Rendimiento (t/ha)"]].rename(
        columns={"Rendimiento (t/ha)": "Valor"}
    )
    rend["Métrica"] = "Rendimiento Presupuestado (t/ha)"
    rend["Etiqueta"] = "Rendimiento Presupuestado (t/ha)"
    rend["Orden"] = ORDEN_RENDIMIENTO

    indif = indiferencia(df, by=by)
    rinde_indif = indif[by + ["Rinde de indiferencia (t/ha)"]].rename(
        columns={"Rinde de indiferencia (t/ha)": "Valor"}
    )
    rinde_indif["Métrica"] = "Rinde indiferencia (t/ha)"
    rinde_indif["Etiqueta"] = "Rinde indiferencia (t/ha)"
    rinde_indif["Orden"] = ORDEN_RINDE_INDIFERENCIA

    precio_indif = indif[by + ["Precio de indiferencia Neto (u$/t)"]].rename(
        columns={"Precio de indiferencia Neto (u$/t)": "Valor"}
    )
    precio_indif["Métrica"] = "Precio Neto Indiferencia (u$/t)"
    precio_indif["Etiqueta"] = "Precio Neto Indiferencia (u$/t)"
    precio_indif["Orden"] = ORDEN_PRECIO_INDIFERENCIA

    filas_has = has.rename(columns={"Has": "Valor"}).copy()
    filas_has["Métrica"] = "Has"
    filas_has["Etiqueta"] = "Has"
    filas_has["Orden"] = ORDEN_HAS

    cols = by + ["Métrica", "Etiqueta", "Orden", "Valor"]
    resultado = pd.concat(
        [
            filas_has[cols],
            detalle[cols],
            ingreso_neto[cols],
            gastos_totales[cols],
            margen_neto[cols],
            rentabilidad[cols],
            rend[cols],
            rinde_indif[cols],
            precio_indif[cols],
        ],
        ignore_index=True,
    )
    return resultado
