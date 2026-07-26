import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src import auth, data

px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = px.colors.qualitative.Set2


def add_series_averages(fig: go.Figure) -> go.Figure:
    """Agrega una línea punteada horizontal con el promedio de cada serie
    (misma traza/color, en su propio panel si hay facetas)."""
    extra_traces = []
    for trace in fig.data:
        y_values = [v for v in trace.y if v is not None]
        if not y_values:
            continue
        avg = sum(y_values) / len(y_values)
        extra_traces.append(
            go.Scatter(
                x=[trace.x[0], trace.x[-1]],
                y=[avg, avg],
                mode="lines",
                line=dict(color=trace.line.color, width=1.5, dash="dot"),
                xaxis=trace.xaxis,
                yaxis=trace.yaxis,
                showlegend=False,
                hovertemplate=f"Promedio {trace.name}: {avg:.2f}<extra></extra>",
            )
        )
    fig.add_traces(extra_traces)
    return fig


st.set_page_config(page_title="Marialicia · Dashboard", layout="wide", page_icon="🌾")
auth.require_login()

st.markdown(
    """
    <style>
    [data-testid="stSidebar"] [data-testid="stMultiSelect"] label p {
        font-weight: 600;
        font-size: 0.95rem;
    }
    [data-testid="stSidebar"] span[data-baseweb="tag"] {
        background-color: #4c7a4c !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.sidebar.title("🌾 Marialicia")
seccion = st.sidebar.radio(
    "Sección",
    [
        "1. Datos históricos productivos",
        "2. Costos",
        "3. Ingresos",
        "4. Resultados",
    ],
)

if st.sidebar.button("↻ Actualizar datos"):
    st.cache_data.clear()
    st.rerun()

df = data.load_base_df()

st.sidebar.divider()
st.sidebar.markdown("#### 🔎 Filtros")

campos_disponibles = sorted(df["Campo"].dropna().unique())
campos_sel = st.sidebar.multiselect("📍 Campo", campos_disponibles, default=campos_disponibles)

cultivos_disponibles = sorted(df["Cultivo"].dropna().unique())
cultivos_sel = st.sidebar.multiselect("🌱 Cultivo", cultivos_disponibles, default=cultivos_disponibles)

campana_orden = sorted(df["Campaña"].dropna().unique())
campanas_sel = st.sidebar.multiselect("📅 Campaña", campana_orden, default=campana_orden)

df_f = df[df["Campaña"].isin(campanas_sel)]

if seccion.startswith("1"):
    st.title("Datos históricos productivos")

    # --- Área sembrada por campo ---
    st.header("Evolución de área sembrada por campo")
    area_campo_df = data.area_sembrada(df_f, by="Campo")
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
        "No incluye Soja 2ª ni Maíz 2ª (comparten superficie física con el "
        "cultivo de 1ª) ni Ganadería, Vicia, Moha o Sorgo Granífero."
    )

    # --- Área sembrada por cultivo ---
    st.header("Evolución de área sembrada por cultivo")
    area_cultivo_df = data.area_sembrada(df_f, by="Cultivo")
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
        "No incluye Soja 2ª ni Maíz 2ª (comparten superficie física con el "
        "cultivo de 1ª) ni Ganadería, Vicia, Moha o Sorgo Granífero."
    )

    st.divider()

    # --- Rendimiento por cultivo ---
    st.header("Rendimiento por cultivo")
    rend_cultivo_df = data.rendimiento(df_f[df_f["Campo"].isin(campos_sel)], by=("Campaña", "Cultivo"))
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
    add_series_averages(fig_rend_cultivo)
    st.plotly_chart(fig_rend_cultivo, use_container_width=True)

    with st.expander("Ver tabla de rendimiento por cultivo"):
        st.dataframe(rend_cultivo_df.sort_values(["Campaña", "Cultivo"]), use_container_width=True)

    # --- Rendimiento por cultivo y campo ---
    st.header("Rendimiento por cultivo y campo")
    rend_df = data.rendimiento(df_f, by=("Campaña", "Campo", "Cultivo"))
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
    add_series_averages(fig_rend)
    st.plotly_chart(fig_rend, use_container_width=True)

    with st.expander("Ver tabla de rendimiento por cultivo y campo"):
        st.dataframe(rend_df.sort_values(["Campaña", "Campo", "Cultivo"]), use_container_width=True)

    st.caption(
        "Rendimiento ponderado por superficie: suma(Dosis × Sup) / suma(Sup), en filas "
        "con c = 'P' (producción/venta), excluyendo Flete y Seguro. La línea punteada "
        "marca el promedio de cada serie en el período filtrado."
    )

    # --- Semáforo: rendimiento vs. promedio histórico del cultivo ---
    st.subheader("Semáforo de rendimiento vs. promedio histórico")

    semaforo_df = data.rendimiento_semaforo(df_f[df_f["Campo"].isin(campos_sel)])
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
        "(campañas seleccionadas en el filtro). Verde oscuro >105% · Verde claro 95–105% · "
        "Amarillo 90–95% · Rojo <90%."
    )

elif seccion.startswith("2"):
    st.title("Costos")

    # --- Costo total por campaña y campo ---
    st.header("Costo total por campaña y campo")
    costo_campo_df = data.costo_total(df_f, by="Campo")
    costo_campo_df = costo_campo_df[costo_campo_df["Campo"].isin(campos_sel)]

    fig_costo_campo = px.bar(
        costo_campo_df.sort_values("Campaña"),
        x="Campaña",
        y="Costo total (u$)",
        color="Campo",
        barmode="stack",
        text_auto=".2s",
        category_orders={"Campaña": campana_orden},
    )
    fig_costo_campo.update_traces(textposition="inside")
    st.plotly_chart(fig_costo_campo, use_container_width=True)

    with st.expander("Ver tabla de costo total por campo"):
        st.dataframe(costo_campo_df.sort_values(["Campaña", "Campo"]), use_container_width=True)

    # --- Costo total por campaña y cultivo ---
    st.header("Costo total por campaña y cultivo")
    costo_cultivo_df = data.costo_total(df_f, by="Cultivo")
    costo_cultivo_df = costo_cultivo_df[costo_cultivo_df["Cultivo"].isin(cultivos_sel)]

    fig_costo_cultivo = px.bar(
        costo_cultivo_df.sort_values("Campaña"),
        x="Campaña",
        y="Costo total (u$)",
        color="Cultivo",
        barmode="stack",
        text_auto=".2s",
        category_orders={"Campaña": campana_orden},
    )
    fig_costo_cultivo.update_traces(textposition="inside")
    st.plotly_chart(fig_costo_cultivo, use_container_width=True)

    with st.expander("Ver tabla de costo total por cultivo"):
        st.dataframe(costo_cultivo_df.sort_values(["Campaña", "Cultivo"]), use_container_width=True)

    st.caption("Costo total = suma de Total u$ en filas con columna c = 'v'.")

    st.divider()

    # --- Costo por hectárea cosechada, por Tipo ---
    st.header("Costo por hectárea cosechada, por Tipo")

    tipo_paleta = px.colors.qualitative.Dark24

    st.subheader("Por Tipo y Campo")
    costo_tipo_campo_df = data.costo_por_tipo_por_ha(df_f, by="Campo")
    costo_tipo_campo_df = costo_tipo_campo_df[costo_tipo_campo_df["Campo"].isin(campos_sel)]

    fig_costo_tipo_campo = px.bar(
        costo_tipo_campo_df.sort_values("Campaña"),
        x="Campaña",
        y="Costo por ha cosechada (u$/ha)",
        color="Tipo",
        barmode="stack",
        facet_col="Campo",
        facet_col_wrap=2,
        category_orders={"Campaña": campana_orden},
        color_discrete_sequence=tipo_paleta,
    )
    fig_costo_tipo_campo.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1], font=dict(size=13)))
    fig_costo_tipo_campo.update_layout(height=650)
    st.plotly_chart(fig_costo_tipo_campo, use_container_width=True)

    with st.expander("Ver tabla de costo por ha, por Tipo y Campo"):
        st.dataframe(
            costo_tipo_campo_df.sort_values(["Campaña", "Campo", "Tipo"]), use_container_width=True
        )

    st.subheader("Por Tipo y Cultivo")
    costo_tipo_cultivo_df = data.costo_por_tipo_por_ha(df_f, by="Cultivo")
    costo_tipo_cultivo_df = costo_tipo_cultivo_df[costo_tipo_cultivo_df["Cultivo"].isin(cultivos_sel)]

    fig_costo_tipo_cultivo = px.bar(
        costo_tipo_cultivo_df.sort_values("Campaña"),
        x="Campaña",
        y="Costo por ha cosechada (u$/ha)",
        color="Tipo",
        barmode="stack",
        facet_col="Cultivo",
        facet_col_wrap=2,
        category_orders={"Campaña": campana_orden},
        color_discrete_sequence=tipo_paleta,
    )
    fig_costo_tipo_cultivo.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1], font=dict(size=13)))
    fig_costo_tipo_cultivo.update_layout(height=650)
    st.plotly_chart(fig_costo_tipo_cultivo, use_container_width=True)

    with st.expander("Ver tabla de costo por ha, por Tipo y Cultivo"):
        st.dataframe(
            costo_tipo_cultivo_df.sort_values(["Campaña", "Cultivo", "Tipo"]), use_container_width=True
        )

    st.caption(
        "Costo por ha cosechada = suma de Total u$ por Tipo (columna N, en filas con "
        "c = 'v') / hectáreas cosechadas (Sup en filas con Tipo = Cosecha), agrupado "
        "por Campaña y Campo (o Cultivo)."
    )

    st.divider()

    # --- Costo por tonelada producida, por Tipo ---
    st.header("Costo por tonelada producida, por Tipo")

    st.subheader("Por Tipo y Campo")
    costo_tn_campo_df = data.costo_por_tipo_por_tn(df_f, by="Campo")
    costo_tn_campo_df = costo_tn_campo_df[costo_tn_campo_df["Campo"].isin(campos_sel)]

    fig_costo_tn_campo = px.bar(
        costo_tn_campo_df.sort_values("Campaña"),
        x="Campaña",
        y="Costo por Tn producida (u$/t)",
        color="Tipo",
        barmode="stack",
        facet_col="Campo",
        facet_col_wrap=2,
        category_orders={"Campaña": campana_orden},
        color_discrete_sequence=tipo_paleta,
    )
    fig_costo_tn_campo.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1], font=dict(size=13)))
    fig_costo_tn_campo.update_layout(height=650)
    st.plotly_chart(fig_costo_tn_campo, use_container_width=True)

    with st.expander("Ver tabla de costo por Tn, por Tipo y Campo"):
        st.dataframe(
            costo_tn_campo_df.sort_values(["Campaña", "Campo", "Tipo"]), use_container_width=True
        )

    st.subheader("Por Tipo y Cultivo")
    costo_tn_cultivo_df = data.costo_por_tipo_por_tn(df_f, by="Cultivo")
    costo_tn_cultivo_df = costo_tn_cultivo_df[costo_tn_cultivo_df["Cultivo"].isin(cultivos_sel)]

    fig_costo_tn_cultivo = px.bar(
        costo_tn_cultivo_df.sort_values("Campaña"),
        x="Campaña",
        y="Costo por Tn producida (u$/t)",
        color="Tipo",
        barmode="stack",
        facet_col="Cultivo",
        facet_col_wrap=2,
        category_orders={"Campaña": campana_orden},
        color_discrete_sequence=tipo_paleta,
    )
    fig_costo_tn_cultivo.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1], font=dict(size=13)))
    fig_costo_tn_cultivo.update_layout(height=650)
    st.plotly_chart(fig_costo_tn_cultivo, use_container_width=True)

    with st.expander("Ver tabla de costo por Tn, por Tipo y Cultivo"):
        st.dataframe(
            costo_tn_cultivo_df.sort_values(["Campaña", "Cultivo", "Tipo"]), use_container_width=True
        )

    st.caption(
        "Costo por Tn producida = Costo por ha cosechada (u$/ha) / Rendimiento (t/ha) "
        "del mismo Campaña y Campo (o Cultivo)."
    )

elif seccion.startswith("3"):
    st.title("Ingresos")

    st.header("Rendimiento y Total u$ / Sup, por campaña y cultivo")

    ing_df = data.ingresos_rendimiento_precio(df_f, by=("Campaña", "Cultivo"))
    ing_df = ing_df[ing_df["Cultivo"].isin(cultivos_sel)]

    ing_prom_df = data.ingresos_rendimiento_precio(df_f, by=("Cultivo",))
    ing_prom_df = ing_prom_df[ing_prom_df["Cultivo"].isin(cultivos_sel)].copy()
    ing_prom_df["Campaña"] = "Promedio"

    paleta = px.colors.qualitative.Set2
    cultivos_presentes = sorted(ing_df["Cultivo"].dropna().unique())
    campana_orden_prom = list(campana_orden) + ["Promedio"]

    fig_ing = make_subplots(specs=[[{"secondary_y": True}]])
    for i, cultivo in enumerate(cultivos_presentes):
        sub = pd.concat(
            [ing_df[ing_df["Cultivo"] == cultivo], ing_prom_df[ing_prom_df["Cultivo"] == cultivo]]
        )
        sub["Campaña"] = pd.Categorical(sub["Campaña"], categories=campana_orden_prom, ordered=True)
        sub = sub.sort_values("Campaña")
        color = paleta[i % len(paleta)]
        fig_ing.add_trace(
            go.Bar(
                x=sub["Campaña"],
                y=sub["Rendimiento (t/ha)"],
                name=f"{cultivo} · Rendimiento",
                marker_color=color,
                opacity=0.75,
                legendgroup=cultivo,
                text=sub["Rendimiento (t/ha)"].round(1),
                texttemplate="%{text:.1f}",
                textposition="outside",
            ),
            secondary_y=False,
        )
        fig_ing.add_trace(
            go.Scatter(
                x=sub["Campaña"],
                y=sub["Total u$ / Sup (u$/ha)"],
                name=f"{cultivo} · u$/ha",
                mode="lines+markers+text",
                line=dict(color=color, width=3, dash="dot"),
                marker=dict(size=8, line=dict(width=1, color="white")),
                legendgroup=cultivo,
                text=sub["Total u$ / Sup (u$/ha)"].round(0),
                texttemplate="%{text:.0f}",
                textposition="top center",
            ),
            secondary_y=True,
        )

    fig_ing.update_xaxes(categoryorder="array", categoryarray=campana_orden_prom, title_text="Campaña")
    fig_ing.update_yaxes(title_text="Rendimiento (t/ha)", secondary_y=False)
    fig_ing.update_yaxes(title_text="Total u$ / Sup (u$/ha)", secondary_y=True)
    fig_ing.update_layout(template="plotly_white", barmode="group", height=600, hovermode="x unified")
    st.plotly_chart(fig_ing, use_container_width=True)

    with st.expander("Ver tabla de rendimiento y u$/ha por campaña y cultivo"):
        st.dataframe(
            pd.concat([ing_df, ing_prom_df]).sort_values(["Cultivo", "Campaña"]),
            use_container_width=True,
        )

    st.caption(
        "Columnas = Rendimiento (Dosis, t/ha, ponderado por Sup). Línea punteada = "
        "Total u\\$ / Sup (u\\$/ha, ponderado por Sup). Filas con c = 'P', excluyendo Flete. "
        "\"Promedio\" = promedio histórico ponderado del cultivo en el período filtrado."
    )

    st.divider()

    # --- Precio de venta ---
    st.header("Precio de venta por campaña y cultivo")

    precio_df = data.precio_venta(df_f, by=("Campaña", "Cultivo"))
    precio_df = precio_df[precio_df["Cultivo"].isin(cultivos_sel)]

    fig_precio = px.line(
        precio_df.sort_values("Campaña"),
        x="Campaña",
        y="Precio de venta (u$/t)",
        color="Cultivo",
        markers=True,
        line_shape="spline",
        text=precio_df["Precio de venta (u$/t)"].round(0),
        category_orders={"Campaña": campana_orden},
    )
    fig_precio.update_traces(
        mode="lines+markers+text",
        line=dict(width=3),
        marker=dict(size=8, line=dict(width=1, color="white")),
        texttemplate="%{text:.0f}",
        textposition="top center",
    )
    fig_precio.update_layout(hovermode="x unified", legend_title_text="Cultivo")
    add_series_averages(fig_precio)
    st.plotly_chart(fig_precio, use_container_width=True)

    with st.expander("Ver tabla de precio de venta"):
        st.dataframe(precio_df.sort_values(["Campaña", "Cultivo"]), use_container_width=True)

    st.caption(
        "Precio de venta = Prec_Unitario ponderado por Dosis, en filas con c = 'P', "
        "excluyendo Flete. La línea punteada marca el promedio de cada serie en el "
        "período filtrado."
    )

    st.divider()

    # --- Factor del ingreso: rendimiento vs. precio ---
    st.header("¿Qué explica el ingreso de cada campaña: rendimiento o precio?")

    factor_df = data.factor_ingreso(df_f)
    factor_df = factor_df[factor_df["Cultivo"].isin(cultivos_sel)]

    def _color_indice(val: float) -> str:
        if pd.isna(val):
            return ""
        if val > 105:
            return "background-color: #1b5e20; color: white"
        if val >= 95:
            return "background-color: #a5d6a7; color: black"
        if val >= 90:
            return "background-color: #fff59d; color: black"
        return "background-color: #ef5350; color: white"

    styled_factor = (
        factor_df.sort_values(["Cultivo", "Campaña"])
        .style.map(_color_indice, subset=["Índice Rendimiento (%)", "Índice Precio (%)"])
        .format({"Índice Rendimiento (%)": "{:.0f}%", "Índice Precio (%)": "{:.0f}%"})
    )
    st.dataframe(styled_factor, use_container_width=True, hide_index=True)

    st.caption(
        "Cada índice compara la campaña contra el promedio histórico ponderado del "
        "mismo cultivo (100% = igual al promedio). \"Factor dominante\" = el que más "
        "se aleja del 100%, es decir el que más explica que el ingreso de esa campaña "
        "haya sido mejor o peor que lo habitual."
    )

else:
    st.title("Resultados")

    # --- Margen por campo ---
    st.header("Margen por campo")

    margen_campo_df = data.margen(df_f, by="Campo")
    margen_campo_df = margen_campo_df[margen_campo_df["Campo"].isin(campos_sel)]

    st.subheader("Margen total (u$)")
    fig_margen_campo_total = px.bar(
        margen_campo_df.sort_values("Campaña"),
        x="Campaña",
        y="Margen (u$)",
        color="Campo",
        barmode="stack",
        text_auto=".2s",
        category_orders={"Campaña": campana_orden},
    )
    fig_margen_campo_total.update_traces(textposition="inside")
    st.plotly_chart(fig_margen_campo_total, use_container_width=True)

    st.subheader("Margen por ha sembrada (u$/ha)")
    fig_margen_campo_ha = px.line(
        margen_campo_df.sort_values("Campaña"),
        x="Campaña",
        y="Margen (u$/ha)",
        color="Campo",
        markers=True,
        line_shape="spline",
        text=margen_campo_df["Margen (u$/ha)"].round(0),
        category_orders={"Campaña": campana_orden},
    )
    fig_margen_campo_ha.update_traces(
        mode="lines+markers+text",
        line=dict(width=3),
        marker=dict(size=8, line=dict(width=1, color="white")),
        texttemplate="%{text:.0f}",
        textposition="top center",
    )
    fig_margen_campo_ha.update_layout(hovermode="x unified", legend_title_text="Campo")
    add_series_averages(fig_margen_campo_ha)
    st.plotly_chart(fig_margen_campo_ha, use_container_width=True)

    with st.expander("Ver tabla de margen por campo"):
        st.dataframe(margen_campo_df.sort_values(["Campaña", "Campo"]), use_container_width=True)

    st.divider()

    # --- Margen por actividad (cultivo) ---
    st.header("Margen por actividad (cultivo)")

    margen_cultivo_df = data.margen(df_f, by="Cultivo")
    margen_cultivo_df = margen_cultivo_df[margen_cultivo_df["Cultivo"].isin(cultivos_sel)]

    st.subheader("Margen total (u$)")
    fig_margen_cultivo_total = px.bar(
        margen_cultivo_df.sort_values("Campaña"),
        x="Campaña",
        y="Margen (u$)",
        color="Cultivo",
        barmode="stack",
        text_auto=".2s",
        category_orders={"Campaña": campana_orden},
    )
    fig_margen_cultivo_total.update_traces(textposition="inside")
    st.plotly_chart(fig_margen_cultivo_total, use_container_width=True)

    st.subheader("Margen por ha sembrada (u$/ha)")
    fig_margen_cultivo_ha = px.line(
        margen_cultivo_df.sort_values("Campaña"),
        x="Campaña",
        y="Margen (u$/ha)",
        color="Cultivo",
        markers=True,
        line_shape="spline",
        text=margen_cultivo_df["Margen (u$/ha)"].round(0),
        category_orders={"Campaña": campana_orden},
    )
    fig_margen_cultivo_ha.update_traces(
        mode="lines+markers+text",
        line=dict(width=3),
        marker=dict(size=8, line=dict(width=1, color="white")),
        texttemplate="%{text:.0f}",
        textposition="top center",
    )
    fig_margen_cultivo_ha.update_layout(hovermode="x unified", legend_title_text="Cultivo")
    add_series_averages(fig_margen_cultivo_ha)
    st.plotly_chart(fig_margen_cultivo_ha, use_container_width=True)

    with st.expander("Ver tabla de margen por actividad"):
        st.dataframe(margen_cultivo_df.sort_values(["Campaña", "Cultivo"]), use_container_width=True)

    st.caption(
        "Margen = Ingreso total (suma de Total u\\$ en filas con c = 'P') − Costo total "
        "(suma de Total u\\$ en filas con c = 'v'). Margen por ha = Margen / Superficie "
        "sembrada (mismo cálculo que en la Sección 1, sin Soja 2ª, Maíz 2ª, Ganadería, "
        "Vicia, Moha ni Sorgo Granífero)."
    )
