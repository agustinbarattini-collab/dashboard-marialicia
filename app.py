import pandas as pd
import plotly.express as px
import streamlit as st

from src import auth, data

px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = px.colors.qualitative.Set2

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

    campana_orden = sorted(df["Campaña"].dropna().unique())

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
        category_orders={"Campaña": campana_orden},
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
        category_orders={"Campaña": campana_orden},
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

    # --- Rendimiento por cultivo ---
    st.header("Rendimiento por cultivo")
    rend_cultivo_df = data.rendimiento(df[df["Campo"].isin(campos_sel)], by=("Campaña", "Cultivo"))
    rend_cultivo_df = rend_cultivo_df[rend_cultivo_df["Cultivo"].isin(cultivos_sel)]

    fig_rend_cultivo = px.line(
        rend_cultivo_df.sort_values("Campaña"),
        x="Campaña",
        y="Rendimiento (t/ha)",
        color="Cultivo",
        markers=True,
        line_shape="spline",
        category_orders={"Campaña": campana_orden},
    )
    fig_rend_cultivo.update_traces(line=dict(width=3.5), marker=dict(size=9, line=dict(width=1, color="white")))
    fig_rend_cultivo.update_layout(hovermode="x unified", legend_title_text="Cultivo")
    st.plotly_chart(fig_rend_cultivo, use_container_width=True)

    with st.expander("Ver tabla de rendimiento por cultivo"):
        st.dataframe(rend_cultivo_df.sort_values(["Campaña", "Cultivo"]), use_container_width=True)

    # --- Rendimiento por cultivo y campo ---
    st.header("Rendimiento por cultivo y campo")
    rend_df = data.rendimiento(df, by=("Campaña", "Campo", "Cultivo"))
    rend_df = rend_df[rend_df["Campo"].isin(campos_sel) & rend_df["Cultivo"].isin(cultivos_sel)]

    fig_rend = px.line(
        rend_df.sort_values("Campaña"),
        x="Campaña",
        y="Rendimiento (t/ha)",
        color="Cultivo",
        markers=True,
        line_shape="spline",
        facet_col="Campo",
        facet_col_wrap=2,
        category_orders={"Campaña": campana_orden},
    )
    fig_rend.update_traces(line=dict(width=3), marker=dict(size=7, line=dict(width=1, color="white")))
    fig_rend.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1], font=dict(size=13)))
    fig_rend.update_layout(legend_title_text="Cultivo", height=650)
    st.plotly_chart(fig_rend, use_container_width=True)

    with st.expander("Ver tabla de rendimiento por cultivo y campo"):
        st.dataframe(rend_df.sort_values(["Campaña", "Campo", "Cultivo"]), use_container_width=True)

    st.caption(
        "Rendimiento ponderado por superficie: suma(Dosis × Sup) / suma(Sup), en filas "
        "con c = 'P' (producción/venta), excluyendo Flete y Seguro."
    )

    # --- Semáforo: rendimiento vs. promedio histórico del cultivo ---
    st.subheader("Semáforo de rendimiento vs. promedio histórico")

    semaforo_df = data.rendimiento_semaforo(df[df["Campo"].isin(campos_sel)])
    semaforo_df = semaforo_df[semaforo_df["Cultivo"].isin(cultivos_sel)]

    pivot = semaforo_df.pivot(index="Cultivo", columns="Campaña", values="Índice (%)")
    pivot = pivot.reindex(columns=[c for c in campana_orden if c in pivot.columns])

    def _color_semaforo(val: float) -> str:
        if pd.isna(val):
            return ""
        if val > 105:
            return "background-color: #1b5e20; color: white"
        if val >= 95:
            return "background-color: #a5d6a7; color: black"
        if val >= 90:
            return "background-color: #fff59d; color: black"
        return "background-color: #ef5350; color: white"

    styled_pivot = pivot.style.map(_color_semaforo).format("{:.0f}%", na_rep="—")
    st.dataframe(styled_pivot, use_container_width=True)

    st.caption(
        "Índice = rendimiento de la campaña / promedio histórico ponderado del cultivo "
        "(todas las campañas disponibles). Verde oscuro >105% · Verde claro 95–105% · "
        "Amarillo 90–95% · Rojo <90%."
    )

elif seccion.startswith("2"):
    st.title("Costos e ingresos")
    st.info("Próximamente. Avisame y seguimos con esta sección.")

else:
    st.title("Resultados - Márgenes y rentabilidad")
    st.info("Próximamente. Avisame y seguimos con esta sección.")
