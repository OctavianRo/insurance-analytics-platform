"""Interactive mortality, drift, and client reporting workbench."""

from functools import wraps
from threading import RLock

import plotly.express as px
from dash import Dash, Input, Output, dash_table, dcc, html

from .monitoring import drift_report
from .mortality import Assumptions, prepare, summarize
from .reporting import premium_report
from .synthetic import applications, experience, premium_transactions

_CHART_LOCK = RLock()


def _serialized_chart(function):
    """Plotly 5 initializes shared template objects lazily; serialize callbacks."""

    @wraps(function)
    def call(*args, **kwargs):
        with _CHART_LOCK:
            return function(*args, **kwargs)

    return call


def create_dashboard():
    app = Dash(__name__, title="Insurance Analytics Workbench")
    study, apps = experience(), applications()
    app.layout = html.Div(
        [
            html.P(
                "LIFE & HEALTH · ANALYTICS LAB", style={"letterSpacing": "3px", "color": "#167d8d"}
            ),
            html.H1("Insurance analytics workbench", style={"fontSize": "40px"}),
            html.P(
                "Explore mortality assumptions, model stability, and reinsurance reporting on synthetic data."
            ),
            dcc.Tabs(
                [
                    dcc.Tab(
                        label="Mortality experience",
                        children=[
                            html.H3("Assumption sensitivity"),
                            html.Label("Expected mortality multiplier"),
                            dcc.Slider(
                                id="multiplier",
                                min=0.5,
                                max=1.5,
                                step=0.05,
                                value=1,
                                marks={0.5: "0.50×", 1: "1.00×", 1.5: "1.50×"},
                            ),
                            html.Label("Client"),
                            dcc.Dropdown(
                                id="client",
                                options=["All", "Aster", "Birch", "Cedar"],
                                value="All",
                                clearable=False,
                            ),
                            html.Div(id="kpis"),
                            dcc.Graph(id="mortality-chart"),
                            html.P("Exact Poisson count A/E intervals. Illustrative assumptions."),
                        ],
                    ),
                    dcc.Tab(
                        label="Model monitoring",
                        children=[
                            html.H3("Current population shift"),
                            html.Label("Simulated BMI shift"),
                            dcc.Slider(
                                id="shift",
                                min=0,
                                max=8,
                                step=0.5,
                                value=4,
                                marks={0: "0", 4: "+4", 8: "+8"},
                            ),
                            dcc.Graph(id="drift-chart"),
                            html.Div(id="drift-table"),
                            html.P(
                                "Reference-fixed PSI bins; KS tests with multiple-testing correction. Alerts require investigation."
                            ),
                        ],
                    ),
                    dcc.Tab(
                        label="Client reporting",
                        children=[
                            html.H3("Premium and volume report"),
                            html.P(
                                "Money is in integer cents. Volume uses each policy’s last transaction in the month."
                            ),
                            dcc.Dropdown(
                                id="report-client",
                                options=["All", "Aster", "Birch", "Cedar"],
                                value="All",
                                clearable=False,
                            ),
                            html.Div(id="premium-table"),
                            dcc.Graph(id="premium-chart"),
                        ],
                    ),
                ]
            ),
            html.Hr(),
            html.Small(
                "Independent portfolio implementation · Synthetic data only · Research and human review"
            ),
        ],
        style={
            "fontFamily": "system-ui, sans-serif",
            "maxWidth": "1250px",
            "margin": "auto",
            "padding": "32px",
            "color": "#183047",
        },
    )

    @app.callback(
        Output("kpis", "children"),
        Output("mortality-chart", "figure"),
        Input("multiplier", "value"),
        Input("client", "value"),
    )
    @_serialized_chart
    def mortality_view(multiplier, client):
        data = study if client == "All" else study.loc[study.client == client]
        prepared = prepare(data, Assumptions(multiplier=multiplier))
        summary = summarize(prepared).iloc[0]
        groups = summarize(prepared.assign(age_band=(prepared.age // 10) * 10), ["age_band"])
        groups["error_plus"], groups["error_minus"] = (
            groups.ae_upper - groups.ae_count,
            groups.ae_count - groups.ae_lower,
        )
        fig = px.bar(
            groups,
            x="age_band",
            y="ae_count",
            error_y="error_plus",
            error_y_minus="error_minus",
            title="Actual / expected deaths by age band",
            template="plotly_white",
        )
        fig.add_hline(y=1, line_dash="dash")
        return html.H3(
            f"{summary.deaths:.0f} deaths · {summary.expected_deaths:.1f} expected · {summary.ae_count:.2f} A/E"
        ), fig

    @app.callback(
        Output("drift-chart", "figure"), Output("drift-table", "children"), Input("shift", "value")
    )
    @_serialized_chart
    def drift_view(shift):
        current = apps.iloc[-600:].copy()
        current["bmi"] += shift
        report = drift_report(apps.iloc[:2000], current, ["age", "bmi", "a1c", "rx_count"])
        fig = px.bar(
            report,
            x="feature",
            y="psi",
            color="alert",
            title="Population stability index",
            template="plotly_white",
        )
        return fig, dash_table.DataTable(
            data=report.round(5).to_dict("records"), page_size=10, style_table={"overflowX": "auto"}
        )

    @app.callback(
        Output("premium-table", "children"),
        Output("premium-chart", "figure"),
        Input("report-client", "value"),
    )
    @_serialized_chart
    def premium_view(client):
        report = premium_report(premium_transactions())
        if client != "All":
            report = report.loc[report.client == client]
        fig = px.line(
            report,
            x="month",
            y="ceded_cents",
            color="client",
            markers=True,
            title="Ceded premium by month (USD cents)",
            template="plotly_white",
        )
        return dash_table.DataTable(
            data=report.to_dict("records"),
            page_size=10,
            sort_action="native",
            export_format="csv",
            style_table={"overflowX": "auto"},
        ), fig

    return app
