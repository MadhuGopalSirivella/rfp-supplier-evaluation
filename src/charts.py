from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

PALETTE = ["#2f75ff", "#16b8a6", "#87c95f", "#f4a340", "#ee6d73"]


def score_chart(results: list[dict[str, Any]]) -> go.Figure:
    frame = pd.DataFrame(results).sort_values("final_rank")
    figure = px.bar(frame, x="supplier_name", y="absolute_score", color="supplier_name",
                    color_discrete_sequence=PALETTE, text_auto=".1f", labels={
                        "supplier_name": "Supplier", "absolute_score": "Absolute score / 100"
                    })
    figure.update_layout(showlegend=False, yaxis_range=[0, 100], margin=dict(t=20, b=20))
    return figure


def ppi_chart(results: list[dict[str, Any]]) -> go.Figure:
    frame = pd.DataFrame(results).sort_values("final_rank")
    figure = px.bar(frame, x="supplier_name", y="ppi", color="supplier_name",
                    color_discrete_sequence=PALETTE, text_auto=".1f", labels={
                        "supplier_name": "Supplier", "ppi": "Peer Performance Index"
                    })
    figure.update_layout(showlegend=False, yaxis_range=[0, 110], margin=dict(t=20, b=20))
    return figure


def criterion_heatmap(results: list[dict[str, Any]]) -> go.Figure:
    rows = []
    for result in results:
        rows.extend({"Supplier": result["supplier_name"], "Criterion": item["name"],
                     "Normalized score": item["normalized_score"]}
                    for item in result["criteria"])
    frame = pd.DataFrame(rows)
    return px.density_heatmap(frame, x="Criterion", y="Supplier", z="Normalized score",
                              histfunc="avg", color_continuous_scale=["#edf3ff", "#2f75ff", "#16b8a6"],
                              range_color=[0, 100])


def experience_scatter(results: list[dict[str, Any]]) -> go.Figure:
    frame = pd.DataFrame(results)
    return px.scatter(frame, x="experience_rating", y="ppi", color="supplier_name",
                      size="absolute_score", text="supplier_name", color_discrete_sequence=PALETTE,
                      labels={"experience_rating": "Historical experience (0-10)",
                              "ppi": "Peer Performance Index"})