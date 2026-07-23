import plotly.express as px
import streamlit as st

from src import auth, data

st.set_page_config(page_title="Marialicia · Dashboard", layout="wide", page_icon="🌾")
auth.require_login()

st.sidebar.title("🌾 Marialicia")
seccion = st.sidebar.radio(
    "Sección",
    [
        "1. Datos históricos productivos",
        "2. Costos e ingresos",
        "3. Resultados - Márgenes y rentabilidad",
    ],
)

if st.sidebar.button("↻ Actualizar datos"):
    st.cache_data.clear()
    st.rerun()

df = data.load_base_df()

if seccion.startswith("1"):
    st.title("Datos históricos productivos")

    campos_disponibles = sorted(df["Campo"].dropna().unique())
    campos_sel = st.sidebar.multiselect("Campo", campos_disponibles, default=campos_disponibles)

    cultivos_disponibles = sorted(df["Cultivo"].dropna().unique())
    cultivos_sel = st.sidebar.multiselect("Cultivo", cultivos_disponibles, default=cultivos_disponibles)

    # --- Área sembrada por campo ---
    st.header("Evolución de área sembrada por campo")
    area_campo_df = data.area_sembrada(df, by="Campo")
    area_campo_df = area_campo_df[area_campo_df["Campo"].isin(campos_sel)]

    fig_area_campo = px.bar(
        area_campo_df.sort_values("Campaña"),
        x="Campaña",
        y="Superficie sembrada (ha)",
        color="Campo",
        barmode="stack",
        text_auto=".0f",
    )
    fig_area_campo.update_traces(textposition="inside")
    st.plotly_chart(fig_area_campo, use_container_width=True)

    with st.expander("Ver tabla de área sembrada por campo"):
        st.dataframe(area_campo_df.sort_values(["Campaña", "Campo"]), use_container_width=True)

    st.caption(
        "No incluye Soja 2ª (comparte superficie física con el cultivo de 1ª) "
        "ni Ganadería, Vicia, Moha o Sorgo Granífero."
    )

    # --- Área sembrada por cultivo ---
    st.header("Evolución de área sembrada por cultivo")
    area_cultivo_df = data.area_sembrada(df, by="Cultivo")
    area_cultivo_df = area_cultivo_df[area_cultivo_df["Cultivo"].isin(cultivos_sel)]

    fig_area_cultivo = px.bar(
        area_cultivo_df.sort_values("Campaña"),
        x="Campaña",
        y="Superficie sembrada (ha)",
        color="Cultivo",
        barmode="stack",
        text_auto=".0f",
    )
    fig_area_cultivo.update_traces(textposition="inside")
    st.plotly_chart(fig_area_cultivo, use_container_width=True)

    with st.expander("Ver tabla de área sembrada por cultivo"):
        st.dataframe(area_cultivo_df.sort_values(["Campaña", "Cultivo"]), use_container_width=True)

    st.caption(
        "No incluye Soja 2ª (comparte superficie física con el cultivo de 1ª) "
        "ni Ganadería, Vicia, Moha o Sorgo Granífero."
    )

    st.divider()

    # --- Rendimiento ---
    st.header("Rendimiento por campaña, campo y cultivo")

    rend_df = data.rendimiento(df)
    rend_df = rend_df[rend_df["Campo"].isin(campos_sel) & rend_df["Cultivo"].isin(cultivos_sel)]

    fig_rend = px.bar(
        rend_df.sort_values("Campaña"),
        x="Campaña",
        y="Rendimiento (t/ha)",
        color="Cultivo",
        barmode="group",
        facet_col="Campo",
        facet_col_wrap=2,
    )
    st.plotly_chart(fig_rend, use_container_width=True)

    with st.expander("Ver tabla de rendimiento"):
        st.dataframe(rend_df.sort_values(["Campaña", "Campo", "Cultivo"]), use_container_width=True)

    st.caption(
        "Rendimiento = promedio de Dosis en filas con c = 'P' (producción/venta), "
        "excluyendo Flete y Seguro, agrupado por Campaña, Campo y Cultivo (columna Activ)."
    )

elif seccion.startswith("2"):
    st.title("Costos e ingresos")
    st.info("Próximamente. Avisame y seguimos con esta sección.")

else:
    st.title("Resultados - Márgenes y rentabilidad")
    st.info("Próximamente. Avisame y seguimos con esta sección.")
