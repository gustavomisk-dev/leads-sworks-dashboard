"""
Dashboard de leads SWorks — Streamlit Community Cloud.
Dados lidos do repositorio privado leads-sworks-data via GitHub API.
"""

import json
import time
import requests
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta
from collections import defaultdict

# ── Pagina ───────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Zilieads",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
[data-testid="collapsedControl"] { display: none; }

.kpi-row { display: flex; gap: 12px; margin: 16px 0 24px; flex-wrap: wrap; }
.kpi-card {
    flex: 1; min-width: 130px;
    background: #131210; border-radius: 10px;
    padding: 16px 18px; border: 1px solid #272420; text-align: center;
}
.kpi-label { color: #94a3b8; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; margin-bottom: 6px; }
.kpi-value { color: #FEC52E; font-size: 24px; font-weight: 700; line-height: 1.1; }
.kpi-sub   { color: #64748b; font-size: 11px; margin-top: 5px; }

.sec { color: #FEC52E; font-size: 15px; font-weight: 600; margin: 28px 0 8px;
       border-bottom: 1px solid #272420; padding-bottom: 6px; }
.periodo { color: #64748b; font-size: 13px; margin-bottom: 4px; }

/* HTML data tables */
.dtbl-title { font-size: 14px; font-weight: 600; color: #e2e8f0; margin-bottom: 12px; }
.dtbl-wrap { overflow-x: auto; }
.dtbl { width: 100%; border-collapse: collapse; font-size: 12px; color: #cbd5e1; }
.dtbl thead th {
    background: #1c1a0e; color: #d4b84a;
    padding: 8px 12px; font-size: 11px; font-weight: 600;
    letter-spacing: 0.3px; text-transform: uppercase;
    text-align: left; white-space: nowrap;
    border-bottom: 1px solid rgba(254,197,46,0.18);
}
.dtbl thead th.r { text-align: right; }
.dtbl thead th.c { text-align: center; }
.dtbl tbody tr.g0 { background: #1a1814; }
.dtbl tbody tr.g1 { background: #131210; }
.dtbl tbody tr.g0:hover, .dtbl tbody tr.g1:hover { background: rgba(254,197,46,0.05); }
.dtbl tbody td {
    padding: 6px 12px; border-bottom: 1px solid rgba(255,255,255,0.04);
    white-space: nowrap; max-width: 360px;
}
.dtbl tbody td.wrap { white-space: normal; word-break: break-word; }
.dtbl tbody td.r { text-align: right; }
.dtbl tbody td.c { text-align: center; }
</style>
""", unsafe_allow_html=True)

# ── Secrets ───────────────────────────────────────────────────────────────────

try:
    _TOKEN = st.secrets["github"]["token"]
    _REPO  = st.secrets["github"]["repo"]
except Exception:
    st.error("Secrets do GitHub não configurados. Adicione [github] token e repo em Settings > Secrets.")
    st.stop()

_HEADERS_RAW  = {"Authorization": f"Bearer {_TOKEN}", "Accept": "application/vnd.github.v3.raw"}
_HEADERS_JSON = {"Authorization": f"Bearer {_TOKEN}"}

# ── Constantes ────────────────────────────────────────────────────────────────

_STATUS_NOMES = {
    0: "Novo", 1: "Pendente", 2: "Em Processamento", 3: "Aprovado",
    4: "Reprovado", 5: "Suspenso", 6: "Pendente Manual",
    7: "Pendente Falha", 8: "Cancelado",
}
_STATUS_CORES = {
    3: "#22c55e", 4: "#ef4444", 5: "#f59e0b", 2: "#3b82f6",
    0: "#94a3b8", 7: "#a855f7", 8: "#64748b", 1: "#6366f1", 6: "#ec4899",
}

_ETAPAS_ANTES = frozenset({"Já Reprovado (reentrada)", "Validações Internas"})

_ETAPA_WORKFLOW_ORDER = [
    "Já Reprovado (reentrada)",
    "Validações Internas",
    "Receita Federal PF",
    "Consulta Dataprev",
    "Receita Federal PJ",
    "Análise PH3A (PJ)",
    "SCR",
    "Análise PH3A (PF)",
    "Cálculo de Proposta",
]

_TEMPLATE = "plotly_dark"
_CONF     = {"displayModeBar": False, "responsive": True}
_GRID     = "rgba(255,255,255,0.06)"
_BG       = "rgba(0,0,0,0)"
_TF       = dict(size=15, color="#FEC52E")
_AF       = dict(size=13, color="#94a3b8")

_TV_N_SLIDES   = 12
_TV_INTERVAL_S = 15  # seconds per slide

# ── GitHub API ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def listar_datas() -> list:
    url = f"https://api.github.com/repos/{_REPO}/contents/dados"
    r = requests.get(url, headers=_HEADERS_JSON, timeout=15)
    if r.status_code != 200:
        return []
    datas = []
    for arq in r.json():
        nome = arq.get("name", "")
        if nome.endswith(".json") and len(nome) == 13 and nome[:8].isdigit():
            datas.append(nome[:8])
    return sorted(datas)


@st.cache_data(ttl=300)
def carregar_dia(dia_str: str) -> dict:
    url = f"https://api.github.com/repos/{_REPO}/contents/dados/{dia_str}.json"
    r = requests.get(url, headers=_HEADERS_RAW, timeout=15)
    if r.status_code == 200:
        try:
            return json.loads(r.text)
        except Exception:
            pass
    return {}

# ── Agregacao ─────────────────────────────────────────────────────────────────

def agregar(dias_raw: list) -> dict:
    d_status     = defaultdict(int)
    fin_n        = defaultdict(int)
    fin_total    = defaultdict(float)
    fin_min      = {}
    fin_max      = {}
    fin_med_sum  = defaultdict(float)
    evolucao_d   = defaultdict(lambda: defaultdict(int))
    evolucao_h   = defaultdict(lambda: defaultdict(int))
    motivos      = defaultdict(int)
    motivos_det  = defaultdict(int)
    empregadores = defaultdict(int)
    cbos         = defaultdict(int)
    emp_rep      = defaultdict(int)
    cnaes        = defaultdict(int)
    cbos_rep     = defaultdict(int)
    ufs          = defaultdict(int)
    bloqueios    = defaultdict(int)
    etapas       = defaultdict(int)
    etapa_motivos = defaultdict(lambda: defaultdict(int))
    valores_cont = []
    aguardando   = 0

    for d in dias_raw:
        for k, v in d.get("funil", {}).get("_d_status", {}).items():
            d_status[int(k)] += v

        for campo, s in d.get("financeiro", {}).items():
            n = s.get("n", 0)
            if n > 0:
                fin_n[campo]      += n
                fin_total[campo]  += s.get("total", 0.0)
                fin_med_sum[campo] += s.get("mediana", 0.0) * n
                fin_min[campo] = min(fin_min.get(campo, float("inf")),  s.get("min", float("inf")))
                fin_max[campo] = max(fin_max.get(campo, float("-inf")), s.get("max", float("-inf")))

        for dt, cont in d.get("evolucao_diaria", {}).items():
            for sk, cnt in cont.items():
                evolucao_d[dt][int(sk)] += cnt

        for hr, cont in d.get("evolucao_horaria", {}).items():
            for sk, cnt in cont.items():
                evolucao_h[hr][int(sk)] += cnt

        for k, v in d.get("top_motivos", {}).items():
            if k:
                motivos[k] += v
        for k, v in d.get("top_motivos_det", {}).items():
            if k:
                motivos_det[k] += v
        for k, v in d.get("top_empregadores", {}).items():
            if k:
                empregadores[k] += v
        for k, v in d.get("top_cbos", {}).items():
            if k:
                cbos[k] += v
        for k, v in d.get("top_empregadores_rep", {}).items():
            if k:
                emp_rep[k] += v
        for k, v in d.get("top_cnaes", {}).items():
            if k:
                cnaes[k] += v
        for k, v in d.get("top_cbos_rep", {}).items():
            if k:
                cbos_rep[k] += v
        for k, v in d.get("top_ufs", {}).items():
            if k:
                ufs[k] += v

        for k, v in d.get("bloqueios", {}).items():
            bloqueios[k] += v
        for k, v in d.get("etapas", {}).items():
            etapas[k] += v

        for etapa, mots in d.get("etapa_motivos", {}).items():
            for label, cnt in mots.items():
                etapa_motivos[etapa][label] += cnt

        valores_cont.extend(d.get("valores_contratacao", []))
        aguardando += d.get("aguardando", 0)

    aprovados  = d_status.get(3, 0)
    reprovados = d_status.get(4, 0)
    cancelados = d_status.get(8, 0)
    terminais  = aprovados + reprovados + cancelados
    em_curso   = sum(v for k, v in d_status.items() if k not in {3, 4, 8})
    total      = sum(d_status.values())

    funil = {
        "total":           total,
        "aprovados":       aprovados,
        "reprovados":      reprovados,
        "cancelados":      cancelados,
        "terminais":       terminais,
        "em_curso":        em_curso,
        "taxa_aprovacao":  aprovados  / terminais * 100 if terminais else 0.0,
        "taxa_reprovacao": reprovados / terminais * 100 if terminais else 0.0,
        "_d_status":       dict(d_status),
    }

    financeiro = {}
    for campo in fin_n:
        n = fin_n[campo]
        financeiro[campo] = {
            "n":      n,
            "media":  fin_total[campo] / n,
            "mediana": fin_med_sum[campo] / n,
            "total":  fin_total[campo],
            "min":    fin_min[campo],
            "max":    fin_max[campo],
        }

    def _top(dd, n):
        return dict(sorted(dd.items(), key=lambda x: -x[1])[:n])

    return {
        "funil":             funil,
        "financeiro":        financeiro,
        "evolucao_diaria":   {k: dict(v) for k, v in sorted(evolucao_d.items())},
        "evolucao_horaria":  {k: dict(v) for k, v in sorted(evolucao_h.items())},
        "top_motivos":       _top(motivos,      20),
        "top_motivos_det":   _top(motivos_det,  20),
        "top_empregadores":  _top(empregadores, 15),
        "top_cbos":          _top(cbos,         15),
        "top_emp_rep":       _top(emp_rep,      20),
        "top_cnaes":         _top(cnaes,        20),
        "top_cbos_rep":      _top(cbos_rep,     20),
        "top_ufs":           _top(ufs,          27),
        "bloqueios":         dict(bloqueios),
        "etapas":            dict(etapas),
        "etapa_motivos":     {e: dict(m) for e, m in etapa_motivos.items()},
        "valores_contratacao": valores_cont,
        "aguardando":        aguardando,
    }

# ── Chart builders ────────────────────────────────────────────────────────────

def _fig_donut(d_status: dict):
    items  = sorted([(s, n) for s, n in d_status.items() if n > 0], key=lambda x: -x[1])
    labels = [_STATUS_NOMES.get(s, f"Status {s}") for s, _ in items]
    values = [n for _, n in items]
    colors = [_STATUS_CORES.get(s, "#666") for s, _ in items]
    total  = sum(values)
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors, line=dict(color="#0d0c0a", width=2)),
        hole=0.46,
        textinfo="label+percent",
        textfont=dict(size=11, color="#e2e8f0"),
        hovertemplate="%{label}: <b>%{value:,}</b> (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text="Distribuição por Status", font=_TF),
        legend=dict(font=dict(size=10, color="#94a3b8"), bgcolor=_BG,
                    orientation="v", x=1.02, y=0.5),
        margin=dict(t=50, b=10, l=10, r=10), height=360,
        annotations=[dict(text=f"<b>{total:,}</b><br><span style='font-size:10px'>leads</span>",
                          x=0.5, y=0.5, font=dict(size=14, color="#e2e8f0"), showarrow=False)],
    )
    return fig


def _fig_funil_rico(funil: dict):
    d_st = funil.get("_d_status", {})
    total = funil.get("total", 0)
    if total == 0:
        return None
    _ORDEM = [0, 1, 2, 5, 6, 7, 3, 4, 8]
    presentes = [s for s in _ORDEM if d_st.get(s, 0) > 0]
    extras    = [s for s in sorted(d_st) if s not in _ORDEM and d_st.get(s, 0) > 0]
    steps = [("Total de Leads", total, "#3b82f6")] + [
        (_STATUS_NOMES.get(s, str(s)), d_st[s], _STATUS_CORES.get(s, "#9ca3af"))
        for s in presentes + extras if d_st.get(s, 0) > 0
    ]
    if len(steps) < 2:
        return None
    labels, values, colors = zip(*steps)
    fig = go.Figure(go.Funnel(
        y=list(labels), x=list(values),
        marker=dict(color=list(colors), line=dict(color="#0d0c0a", width=1.5)),
        texttemplate="%{value:,}<br>%{percentInitial:.1%}",
        textfont=dict(size=12, color="#e2e8f0"),
        connector=dict(line=dict(color="rgba(255,255,255,0.2)", width=1)),
        hovertemplate="<b>%{y}</b><br>%{x:,} leads · %{percentInitial:.2%}<extra></extra>",
    ))
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text="Funil de Conversão", font=_TF),
        margin=dict(t=50, b=10, l=140, r=40), height=360,
    )
    return fig


def _fig_evolucao(agg: dict, n_dias: int, dias_raw: list = None, datas_sel: list = None):
    slots = [f"{h:02d}:{m:02d}" for h in range(24) for m in range(0, 60, 15)]
    if n_dias == 1:
        ev         = agg["evolucao_horaria"]
        eixo       = slots
        titulo     = "Evolução por 15 min"
        xlab       = "Hora"
        xaxis_extra = {}
        trace_mode = "lines+markers"
    else:
        # Série temporal completa: 96 slots × N dias, tick só nas datas.
        # Usa datas_sel como base do eixo-x para garantir que todos os dias
        # selecionados apareçam, mesmo que o JSON de algum dia não tenha carregado.
        dia_map = {d.get("data", ""): d for d in (dias_raw or [])}
        # Ordena pela string da data (YYYYMMDD) — mesma ordem de datas_sel
        dias_base = sorted(datas_sel or list(dia_map.keys()))
        eixo, ev_ts, tickvals, ticktext = [], {}, [], []
        for dia_str in dias_base:
            d    = dia_map.get(dia_str, {})           # {} se não carregou
            raw  = dia_str                             # "20260620"
            lbl  = f"{raw[6:8]}/{raw[4:6]}"           # "20/06"
            ev_h = d.get("evolucao_horaria", {})
            for slot in slots:
                key = f"{lbl} {slot}"
                eixo.append(key)
                # converte chaves string→int (formato JSON) para .get(s, 0) funcionar
                ev_ts[key] = {int(k): v for k, v in ev_h.get(slot, {}).items()}
            tickvals.append(f"{lbl} 00:00")
            ticktext.append(lbl)
        ev         = ev_ts
        titulo     = "Evolução Diária (15 min)"
        xlab       = "Data"
        xaxis_extra = dict(tickmode="array", tickvals=tickvals, ticktext=ticktext)
        trace_mode = "lines"

    if not eixo:
        return None
    fig = go.Figure()
    for s in [3, 4, 5, 2, 0, 7, 8, 1, 6]:
        y = [ev.get(x, {}).get(s, 0) for x in eixo]
        if sum(y) == 0:
            continue
        fig.add_trace(go.Scatter(
            x=eixo, y=y,
            name=_STATUS_NOMES.get(s, str(s)),
            mode=trace_mode,
            line=dict(color=_STATUS_CORES.get(s, "#aaa"), width=2),
            marker=dict(size=5),
            fill="tozeroy" if s == 3 else "none",
            fillcolor="rgba(34,197,94,0.08)" if s == 3 else None,
            hovertemplate=f"{_STATUS_NOMES.get(s, str(s))}: %{{y:,}}<extra></extra>",
        ))
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text=titulo, font=_TF),
        xaxis=dict(title=xlab, tickfont=_AF, showgrid=True, gridcolor=_GRID, **xaxis_extra),
        yaxis=dict(title="Leads", tickfont=_AF, showgrid=True, gridcolor=_GRID),
        legend=dict(font=dict(size=10, color="#94a3b8"), bgcolor=_BG,
                    orientation="h", y=-0.22, x=0.5, xanchor="center"),
        margin=dict(t=50, b=70, l=10, r=10), height=360,
        hovermode="x unified",
    )
    return fig


def _sem_codigo(d: dict) -> dict:
    """Remove 'CODIGO — ' prefix das chaves, mantendo só a descrição."""
    out: dict = {}
    for k, v in d.items():
        label = k.split(" — ", 1)[1] if " — " in k else k
        out[label] = out.get(label, 0) + v
    return out


def _fig_barras_h(data_dict: dict, titulo: str, color: str, n: int = 15, pct_base: int = 0):
    items = list(data_dict.items())[:n]
    if not items:
        return None
    labels = [k for k, _ in items]
    values = [v for _, v in items]
    max_v  = max(values) if values else 1
    if pct_base > 0:
        shades = [f"rgba(96,165,250,{0.40 + 0.55*(v/max_v):.2f})" for v in values]
        texts  = [f"{100*v/pct_base:.1f}%" for v in values]
        tpos   = "inside"
    else:
        shades = color
        texts  = [f"{v:,}" for v in values]
        tpos   = "outside"
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker=dict(color=shades, line=dict(color="#0d0c0a", width=0.5)),
        text=texts, textposition=tpos,
        insidetextanchor="end" if pct_base else None,
        textfont=dict(size=13, color="rgba(255,255,255,0.85)" if pct_base else "#94a3b8"),
        hovertemplate="%{y}: <b>%{x:,}</b><extra></extra>",
    ))
    h = max(280, len(items) * 34 + 80)
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text=titulo, font=_TF),
        xaxis=dict(tickfont=_AF, showgrid=True, gridcolor=_GRID, zeroline=False),
        yaxis=dict(tickfont=dict(size=13, color="#cbd5e1"), autorange="reversed", automargin=True),
        margin=dict(t=50, b=20, l=20, r=60), height=h,
        uniformtext_minsize=11, uniformtext_mode="hide",
    )
    return fig


def _fig_histograma(valores: list):
    if len(valores) < 3:
        return None
    import statistics as _st
    mediana = _st.median(valores)
    media   = _st.mean(valores)
    fig = go.Figure(go.Histogram(
        x=valores, nbinsx=35,
        marker=dict(color="#3b82f6", opacity=0.8, line=dict(color="#0d0c0a", width=0.5)),
        hovertemplate="R$ %{x:,.0f}: %{y:,} contratos<extra></extra>",
    ))
    fig.add_vline(x=mediana, line=dict(color="#f87171", dash="dash", width=2.5))
    fig.add_vline(x=media,   line=dict(color="#fb923c", dash="dot",  width=2))
    fig.add_annotation(x=0.98, y=0.97, xref="paper", yref="paper",
        text=f"Mediana: R$ {mediana:,.0f}", font=dict(color="#f87171", size=12),
        showarrow=False, xanchor="right", yanchor="top",
        bgcolor="rgba(13,12,10,0.88)", borderpad=6,
        bordercolor="rgba(248,113,113,0.35)", borderwidth=1)
    fig.add_annotation(x=0.98, y=0.84, xref="paper", yref="paper",
        text=f"Média: R$ {media:,.0f}", font=dict(color="#fb923c", size=12),
        showarrow=False, xanchor="right", yanchor="top",
        bgcolor="rgba(13,12,10,0.88)", borderpad=6,
        bordercolor="rgba(251,146,60,0.35)", borderwidth=1)
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text="Distribuição do Valor Contratado (Aprovados)", font=_TF),
        xaxis=dict(title="Valor (R$)", tickformat=",.0f", tickfont=_AF,
                   showgrid=True, gridcolor=_GRID),
        yaxis=dict(title="Contratos", tickfont=_AF, showgrid=True, gridcolor=_GRID),
        margin=dict(t=50, b=50, l=10, r=10), height=340, showlegend=False, bargap=0.04,
    )
    return fig


def _fig_etapas_split(etapas: dict, n_rep: int):
    if not etapas or n_rep == 0:
        return None
    n_antes = sum(etapas.get(e, 0) for e in _ETAPAS_ANTES)
    n_corte = n_rep - n_antes
    antes_sorted  = sorted([(n, v) for n, v in etapas.items() if n in _ETAPAS_ANTES],     key=lambda x: x[1])
    depois_sorted = sorted([(n, v) for n, v in etapas.items() if n not in _ETAPAS_ANTES], key=lambda x: x[1])
    _GAP = " "
    all_items = depois_sorted + [(_GAP, 0)] + antes_sorted
    y_labs = [n for n, _ in all_items]
    x_vals = [v for _, v in all_items]
    max_v  = max((v for v in x_vals if v), default=1)
    colors, texts, hovers = [], [], []
    for name, v in all_items:
        if name == _GAP:
            colors.append("rgba(0,0,0,0)"); texts.append(""); hovers.append(""); continue
        shade = 0.40 + 0.55 * (v / max_v)
        is_antes = name in _ETAPAS_ANTES
        denom = n_antes if is_antes else n_corte
        pct   = 100 * v / denom if denom else 0
        gc    = "rgba(251,146,60," if is_antes else "rgba(96,165,250,"
        gl    = (f"dos {n_antes:,} reprov. antes do clique"
                 if is_antes else f"dos {n_corte:,} reprov. após clique")
        colors.append(f"{gc}{shade:.2f})")
        texts.append(f"{v:,} ({pct:.1f}%)")
        hovers.append(f"<b>{name}</b><br>{v:,} leads · {pct:.2f}% {gl}")
    n_dep = len(depois_sorted)
    n_ant = len(antes_sorted)
    shapes = [
        dict(type="line", x0=0, x1=1, xref="paper", y0=n_dep-0.5, y1=n_dep-0.5, yref="y",
             line=dict(color="rgba(255,255,255,0.10)", width=1, dash="dot")),
        dict(type="line", x0=0, x1=1, xref="paper", y0=n_dep+0.5, y1=n_dep+0.5, yref="y",
             line=dict(color="rgba(255,255,255,0.10)", width=1, dash="dot")),
    ]
    annotations = []
    if n_ant > 0:
        annotations.append(dict(xref="paper", yref="y", x=1.02, y=n_dep+1+(n_ant-1)/2,
            text="<b>Antes<br>do clique</b>", showarrow=False, xanchor="left",
            font=dict(size=12, color="#fb923c"), align="left"))
    if n_dep > 0:
        annotations.append(dict(xref="paper", yref="y", x=1.02, y=(n_dep-1)/2,
            text="<b>Depois<br>do clique</b>", showarrow=False, xanchor="left",
            font=dict(size=12, color="#60a5fa"), align="left"))
    bar_h = max(360, len(all_items) * 34 + 90)
    fig = go.Figure(go.Bar(
        x=x_vals, y=y_labs, orientation="h",
        marker=dict(color=colors, line=dict(color="#0d0c0a", width=0.5)),
        text=texts, textposition="inside", insidetextanchor="end",
        textfont=dict(size=13, color="rgba(255,255,255,0.85)"),
        hovertemplate="%{customdata}<extra></extra>", customdata=hovers,
    ))
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text="Reprovados por Etapa — Antes vs. Depois do Clique", font=_TF),
        xaxis=dict(title="Ocorrências", tickfont=_AF, showgrid=True, gridcolor=_GRID, zeroline=False),
        yaxis=dict(tickfont=dict(size=13, color="#cbd5e1"), automargin=True, zeroline=False),
        uniformtext_minsize=11, uniformtext_mode="hide",
        shapes=shapes, annotations=annotations,
        margin=dict(t=50, b=30, l=20, r=110), height=bar_h,
    )
    return fig


def _fig_funil_etapa(etapas: dict, n_rep: int):
    if not etapas or n_rep == 0:
        return None
    _order_idx = {e: i for i, e in enumerate(_ETAPA_WORKFLOW_ORDER)}
    etapas_sorted = sorted(etapas.keys(), key=lambda e: _order_idx.get(e, 999))
    restante = n_rep
    rows = []
    for etapa in etapas_sorted:
        n_rej = etapas.get(etapa, 0)
        pct   = 100 * n_rej / restante if restante > 0 else 0
        rows.append({"etapa": etapa, "chegaram": restante, "rejeitados": n_rej,
                     "pct": pct, "restante_apos": restante - n_rej})
        restante -= n_rej
    if not rows:
        return None
    rows_r   = list(reversed(rows))
    y_labels = [r["etapa"] for r in rows_r]
    rej_colors = []
    for r in rows_r:
        shade = 0.50 + 0.45 * (r["rejeitados"] / n_rep)
        if r["etapa"] in _ETAPAS_ANTES:
            rej_colors.append(f"rgba(251,146,60,{shade:.2f})")
        else:
            rej_colors.append(f"rgba(96,165,250,{shade:.2f})")
    rej_hover = [
        f"<b>{r['etapa']}</b><br>Chegaram: {r['chegaram']:,}<br>"
        f"Reprovados aqui: {r['rejeitados']:,} ({r['pct']:.1f}%)<br>"
        f"Avançaram: {r['restante_apos']:,}"
        for r in rows_r
    ]
    bar_h = max(360, len(rows) * 52 + 90)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[r["rejeitados"] for r in rows_r], y=y_labels, orientation="h",
        name="Reprovados",
        marker=dict(color=rej_colors, line=dict(color="#0d0c0a", width=0.5)),
        text=[f"{r['rejeitados']:,} ({r['pct']:.1f}%)" for r in rows_r],
        textposition="inside", insidetextanchor="middle",
        textfont=dict(size=13, color="rgba(255,255,255,0.90)"),
        hovertemplate="%{customdata}<extra></extra>", customdata=rej_hover,
    ))
    fig.add_trace(go.Bar(
        x=[r["restante_apos"] for r in rows_r], y=y_labels, orientation="h",
        name="Avançaram",
        marker=dict(color="rgba(255,255,255,0.07)", line=dict(color="#0d0c0a", width=0.5)),
        text=[f"{r['restante_apos']:,}" if r["restante_apos"] > 0 else "" for r in rows_r],
        textposition="inside", insidetextanchor="middle",
        textfont=dict(size=12, color="rgba(255,255,255,0.35)"),
        hovertemplate="%{y}: %{x:,} avançaram<extra></extra>",
    ))
    fig.update_layout(
        barmode="stack",
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text="Funil de Reprovação por Etapa", font=_TF),
        xaxis=dict(title="Leads", tickfont=_AF, showgrid=True, gridcolor=_GRID, zeroline=False),
        yaxis=dict(tickfont=dict(size=13, color="#cbd5e1"), automargin=True),
        legend=dict(font=dict(size=12, color="#94a3b8"), bgcolor=_BG,
                    orientation="h", y=-0.10, x=0.5, xanchor="center"),
        uniformtext_minsize=11, uniformtext_mode="hide",
        margin=dict(t=50, b=60, l=20, r=40), height=bar_h,
    )
    return fig, rows  # retorna rows para a tabela resumo


def _fig_bloqueios(bloqueios: dict, n_rep: int = 0):
    if not any(bloqueios.values()):
        return None
    nomes = {"cpf": "CPF Bloqueado", "cnpj": "CNPJ Bloqueado",
             "cnae": "CNAE Bloqueado", "cbo": "CBO Bloqueado"}
    cores = {"cpf": "#f87171", "cnpj": "#fb923c", "cnae": "#a78bfa", "cbo": "#60a5fa"}
    labels = [nomes.get(k, k) for k, v in bloqueios.items() if v > 0]
    values = [v for v in bloqueios.values() if v > 0]
    pcts   = [100*v/n_rep if n_rep else 0 for v in values]
    colors = [cores.get(k, "#666") for k, v in bloqueios.items() if v > 0]
    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker=dict(color=colors, line=dict(color="#0d0c0a", width=1), opacity=0.88),
        text=[f"{v:,}<br>{p:.1f}%" for v, p in zip(values, pcts)],
        textposition="outside",
        textfont=dict(size=12, color="#e2e8f0"),
        hovertemplate="%{x}: <b>%{y:,}</b><extra></extra>",
    ))
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text="Leads com Bloqueio por Tipo", font=_TF),
        xaxis=dict(tickfont=dict(size=12, color="#cbd5e1")),
        yaxis=dict(tickfont=_AF, showgrid=True, gridcolor=_GRID),
        margin=dict(t=50, b=20, l=10, r=10), height=300,
    )
    return fig


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _html_tabela_ranking(data_dict: dict, titulo_col: str, n_total: int,
                          subtitulo: str = "",
                          code_col_title: str = "Código",
                          n: int = 15) -> str:
    """Tabela compacta de ranking: #, [código,] nome, leads, %.
    Se as chaves tiverem formato 'CODIGO — Descrição', exibe 2 colunas separadas."""
    if not data_dict:
        return ""
    _SEP = " — "
    _items = list(data_dict.items())[:n]
    has_sep = any(_SEP in str(k) for k, _ in _items[:5])
    rows_html = []
    for i, (label, cnt) in enumerate(_items):
        pct = f"{100*cnt/n_total:.1f}%" if n_total else "—"
        rc = "g0" if i % 2 == 0 else "g1"
        if has_sep and _SEP in str(label):
            code, desc = str(label).split(_SEP, 1)
            rows_html.append(
                f'<tr class="{rc}">'
                f'<td class="c" style="color:#64748b;width:28px">{i+1}</td>'
                f'<td style="color:#94a3b8;white-space:nowrap">{code}</td>'
                f'<td class="wrap">{desc}</td>'
                f'<td class="r">{cnt:,}</td>'
                f'<td class="r" style="color:#94a3b8">{pct}</td>'
                f'</tr>'
            )
        else:
            rows_html.append(
                f'<tr class="{rc}">'
                f'<td class="c" style="color:#64748b;width:28px">{i+1}</td>'
                f'<td class="wrap">{label}</td>'
                f'<td class="r">{cnt:,}</td>'
                f'<td class="r" style="color:#94a3b8">{pct}</td>'
                f'</tr>'
            )
    if has_sep:
        thead = (
            f'<thead><tr><th class="c">#</th><th>{code_col_title}</th><th>{titulo_col}</th>'
            '<th class="r">Leads</th><th class="r">%</th>'
            '</tr></thead>'
        )
    else:
        thead = (
            f'<thead><tr><th class="c">#</th><th>{titulo_col}</th>'
            '<th class="r">Leads</th><th class="r">%</th>'
            '</tr></thead>'
        )
    titulo_html = f'<div class="dtbl-title" style="margin-top:14px">{subtitulo}</div>' if subtitulo else ""
    return (
        titulo_html
        + '<div class="dtbl-wrap"><table class="dtbl">'
        + thead
        + '<tbody>' + "".join(rows_html) + '</tbody>'
        + '</table></div>'
    )


def _html_diagrama(etapas: dict, n_rep: int) -> str:
    """HTML do Workflow 37 portado de gerar_relatorio_html.py."""
    if not etapas or not n_rep:
        return ""

    _PRE  = [("Inicializa Dados", ["Já Reprovado (reentrada)"])]
    _MC   = [
        ("Validações Internas", ["Validações Internas"]),
        ("Receita Federal PF",  ["Receita Federal PF"]),
        ("Consulta Dataprev",   ["Consulta Dataprev"]),
        ("Receita Federal PJ",  ["Receita Federal PJ"]),
        ("PH3A PJ",             ["Análise PH3A (PJ)"]),
        ("SCR",                 ["SCR"]),
        ("PH3A PF",             ["Análise PH3A (PF)"]),
    ]
    _POST = [
        ("Cálculo Proposta",    ["Cálculo de Proposta"]),
        ("Proposta Leilão",     []),
        ("Cadastro Proposta",   []),
        ("Formalização",        [], True),
        ("Obter CCB",           []),
        ("Averbação Dataprev",  []),
        ("Antifraude",          []),
        ("Pagamento Pix",       []),
        ("Aprovação",           []),
    ]

    _BOX_W = "min-width:58px;max-width:78px;line-height:1.35;white-space:normal;"
    _S_OK  = ("background:#1a3560;border:1px solid rgba(96,165,250,0.25);"
               f"color:#93c5fd;border-radius:8px;padding:6px 10px;"
               f"font-size:11px;font-weight:500;text-align:center;{_BOX_W}")
    _S_REJ = ("background:#431407;border:1.5px solid #f97316;"
               f"color:#fed7aa;border-radius:8px;padding:6px 10px;"
               f"font-size:11px;font-weight:500;text-align:center;{_BOX_W}")
    _ARR   = '<div style="padding:9px 4px 0;color:#374151;font-size:12px;flex-shrink:0;">&#9654;</div>'

    def _unit(name, etapa_keys, nowrap=False):
        count = sum(etapas.get(e, 0) for e in etapa_keys)
        pct   = 100 * count / n_rep if n_rep and count else 0
        _s = _S_REJ if count else _S_OK
        if nowrap:
            _s = _s.replace("max-width:78px;", "").replace("white-space:normal;", "white-space:nowrap;")
        box   = f'<div style="{_s}">{name}</div>'
        below = ""
        if count:
            sub = "".join(
                f'<div style="font-size:8px;color:#94a3b8;overflow:hidden;'
                f'text-overflow:ellipsis;white-space:nowrap;max-width:70px;">'
                f'&#8226; {e}: {etapas[e]:,}</div>'
                for e in etapa_keys if etapas.get(e, 0)
            )
            below = (
                f'<div style="font-size:9px;color:#f97316;margin-top:4px;'
                f'font-weight:700;white-space:nowrap;text-align:center;">'
                f'&#11015; {count:,}&nbsp;({pct:.1f}%)</div>{sub}'
            )
        return (
            f'<div style="display:flex;flex-direction:column;'
            f'align-items:center;flex-shrink:0;">{box}{below}</div>'
        )

    inicio = (
        '<div style="display:flex;flex-direction:column;align-items:center;'
        'flex-shrink:0;padding-top:7px;">'
        '<div style="width:22px;height:22px;border-radius:50%;background:#22c55e;'
        'border:2px solid #16a34a;"></div>'
        '<div style="font-size:9px;color:#64748b;margin-top:4px;">Início</div>'
        '</div>'
    )

    pre_html = inicio
    for name, etapa_keys in _PRE:
        pre_html += _ARR + _unit(name, etapa_keys)

    mc_inner = ""
    for i, (name, etapa_keys) in enumerate(_MC):
        if i > 0:
            mc_inner += _ARR
        mc_inner += _unit(name, etapa_keys)

    mc_label = (
        '<div style="font-size:9px;color:#a5b4fc;font-weight:700;'
        'text-align:center;padding-bottom:6px;white-space:nowrap;'
        'text-transform:uppercase;letter-spacing:0.5px;">Motor de Cr&#233;dito</div>'
    )
    mc_flow = (
        '<div style="display:flex;align-items:flex-start;'
        'border:1px solid rgba(99,102,241,0.40);border-radius:10px;'
        'padding:6px;background:rgba(99,102,241,0.06);">'
        + mc_inner + '</div>'
    )
    mc_html = (
        _ARR
        + '<div style="display:flex;flex-direction:column;flex-shrink:0;">'
        + mc_label + mc_flow + '</div>'
    )

    post_html = ""
    for _entry in _POST:
        _nm, _ek = _entry[0], _entry[1]
        post_html += _ARR + _unit(_nm, _ek, _entry[2] if len(_entry) > 2 else False)

    fim_html = (
        _ARR
        + '<div style="display:flex;flex-direction:column;align-items:center;'
          'flex-shrink:0;padding-top:7px;">'
          '<div style="width:22px;height:22px;border-radius:50%;background:#dc2626;'
          'border:2px solid #b91c1c;"></div>'
          '<div style="font-size:9px;color:#64748b;margin-top:4px;">Aprovado</div>'
          '</div>'
    )

    legend = (
        '<div style="display:flex;gap:20px;margin-top:14px;flex-wrap:wrap;">'
        '<div style="display:flex;align-items:center;gap:6px;font-size:10px;color:#94a3b8;">'
        '<div style="width:12px;height:12px;border-radius:3px;background:#431407;'
        'border:1.5px solid #f97316;flex-shrink:0;"></div>Com reprovações</div>'
        '<div style="display:flex;align-items:center;gap:6px;font-size:10px;color:#94a3b8;">'
        '<div style="width:12px;height:12px;border-radius:3px;background:#1a3560;'
        'border:1px solid rgba(96,165,250,0.25);flex-shrink:0;"></div>Sem reprovações</div>'
        '<div style="display:flex;align-items:center;gap:6px;font-size:10px;color:#94a3b8;">'
        '<div style="width:30px;height:12px;border-radius:3px;'
        'border:1px solid rgba(99,102,241,0.40);'
        'background:rgba(99,102,241,0.06);flex-shrink:0;"></div>'
        'Motor de Cr&#233;dito</div>'
        '</div>'
    )

    title_html = (
        '<div style="font-size:10px;color:#475569;text-transform:uppercase;'
        'letter-spacing:0.6px;margin-bottom:12px;font-weight:600;">'
        'Fluxo do Workflow 37 &#8212; Motor de Cr&#233;dito expandido</div>'
    )

    flow = (
        '<div style="overflow-x:auto;">'
        '<div style="display:flex;align-items:flex-start;gap:0;'
        'min-width:max-content;padding:4px 0 10px;">'
        + pre_html + mc_html + post_html + fim_html
        + '</div></div>'
    )

    return title_html + flow + legend


def _html_tabela_etapa_motivo(etapa_motivos: dict, etapas: dict, n_rep: int) -> str:
    if not etapa_motivos or not etapas or n_rep == 0:
        return ""
    _order_idx = {e: i for i, e in enumerate(_ETAPA_WORKFLOW_ORDER)}
    etapas_sorted = sorted(etapas.keys(), key=lambda e: (_order_idx.get(e, 999), -etapas.get(e, 0)))

    n_antes = sum(etapas.get(e, 0) for e in _ETAPAS_ANTES)
    n_corte = n_rep - n_antes
    show_corte = n_corte > 0 and n_antes > 0

    _SEP_ANT = (
        "background:#1c1a0e;color:#d4b84a;font-size:10px;font-weight:700;"
        "letter-spacing:0.5px;text-transform:uppercase;"
        "padding:9px 12px 7px;border-top:10px solid #0d0c0a;"
        "border-bottom:1px solid rgba(254,197,46,0.2);"
    )
    _SEP_DEP = (
        "background:#0a1a2e;color:#93c5fd;font-size:10px;font-weight:700;"
        "letter-spacing:0.5px;text-transform:uppercase;"
        "padding:9px 12px 7px;border-top:10px solid #0d0c0a;"
        "border-bottom:1px solid rgba(96,165,250,0.2);"
    )

    thead = (
        "<thead><tr>"
        "<th>Etapa</th><th>Motivo de Reprovação</th>"
        '<th class="r">Leads</th><th class="r">%</th>'
        "</tr></thead>"
    )

    tbody_rows = []
    shade_idx  = -1
    prev_group = None

    for etapa in etapas_sorted:
        if etapa not in etapa_motivos and etapas.get(etapa, 0) == 0:
            continue
        is_antes = etapa in _ETAPAS_ANTES
        group    = "antes" if is_antes else "depois"

        if show_corte and group != prev_group:
            label_sep = ("Antes do cliente clicar na proposta" if group == "antes"
                         else "Depois do cliente clicar na proposta")
            sep_style = _SEP_ANT if group == "antes" else _SEP_DEP
            tbody_rows.append(f'<tr><td colspan="4" style="{sep_style}">{label_sep}</td></tr>')
            prev_group = group

        motivos_etapa = sorted(etapa_motivos.get(etapa, {}).items(), key=lambda x: -x[1])
        if not motivos_etapa:
            # etapa sem motivos detalhados — mostra total
            motivos_etapa = [("—", etapas.get(etapa, 0))]

        shade_idx += 1
        rc = "g0" if shade_idx % 2 == 0 else "g1"
        denom = n_antes if is_antes else n_corte
        for i, (motivo, cnt) in enumerate(motivos_etapa):
            pct = f"{100*cnt/denom:.1f}%" if denom else "—"
            tbody_rows.append(
                f'<tr class="{rc}">'
                f"<td>{etapa if i == 0 else ''}</td>"
                f'<td class="wrap">{motivo}</td>'
                f'<td class="r">{cnt:,}</td>'
                f'<td class="r">{pct}</td>'
                f"</tr>"
            )

    if not tbody_rows:
        return ""
    tbody = "<tbody>" + "".join(tbody_rows) + "</tbody>"
    return (
        '<div class="dtbl-title">Detalhamento por Etapa × Motivo</div>'
        '<div class="dtbl-wrap"><table class="dtbl">'
        + thead + tbody
        + "</table></div>"
    )


def _html_tabela_resumo_funil(rows: list) -> str:
    if not rows:
        return ""
    _C_ANT = "#fb923c"
    _C_DEP = "#60a5fa"
    _C_Z   = "#64748b"
    trs = []
    for r in rows:
        cor     = _C_ANT if r["etapa"] in _ETAPAS_ANTES else (_C_DEP if r["rejeitados"] else _C_Z)
        pct_str = f"{r['pct']:.1f}%" if r["rejeitados"] else "—"
        trs.append(
            f'<tr>'
            f'<td style="color:{cor};font-weight:600">{r["etapa"]}</td>'
            f'<td style="text-align:right">{r["chegaram"]:,}</td>'
            f'<td style="text-align:right">{r["rejeitados"]:,}</td>'
            f'<td style="text-align:right;color:{cor}">{pct_str}</td>'
            f'<td style="text-align:right;color:#64748b">{r["restante_apos"]:,}</td>'
            f'</tr>'
        )
    return (
        '<div style="margin-top:18px;overflow-x:auto">'
        '<table class="dtbl" style="max-width:680px">'
        '<thead><tr>'
        '<th>Etapa</th><th class="r">Chegaram</th><th class="r">Reprovados</th>'
        '<th class="r">% dos chegados</th><th class="r">Restante</th>'
        '</tr></thead>'
        f'<tbody>{"".join(trs)}</tbody>'
        '</table></div>'
    )


def _html_tabela_financeira(fin: dict) -> str:
    campos = [
        ("ValorContratacao", "Valor Contratado",  lambda x: f"R$ {x:,.2f}"),
        ("RendaLiquida",     "Renda Líquida",      lambda x: f"R$ {x:,.2f}"),
        ("Prazo",            "Prazo (meses)",       lambda x: f"{x:.0f}"),
        ("Taxa",             "Taxa Mensal (%)",     lambda x: f"{x:.2f}"),
    ]
    rows_html = []
    for campo, label, fmt in campos:
        v = fin.get(campo, {})
        if v.get("n", 0) < 1:
            continue
        total_s = fmt(v["total"]) if campo == "ValorContratacao" else "—"
        rc = "g0" if len(rows_html) % 2 == 0 else "g1"
        rows_html.append(
            f'<tr class="{rc}">'
            f'<td>{label}</td>'
            f'<td class="r">{v["n"]:,}</td>'
            f'<td class="r">{fmt(v["media"])}</td>'
            f'<td class="r">{fmt(v["mediana"])}</td>'
            f'<td class="r">{fmt(v["min"])}</td>'
            f'<td class="r">{fmt(v["max"])}</td>'
            f'<td class="r">{total_s}</td>'
            f'</tr>'
        )
    if not rows_html:
        return ""
    return (
        '<div class="dtbl-title">Estatísticas Financeiras — Aprovados</div>'
        '<div class="dtbl-wrap"><table class="dtbl">'
        '<thead><tr>'
        '<th>Campo</th><th class="r">N</th><th class="r">Média</th>'
        '<th class="r">Mediana*</th><th class="r">Mínimo</th><th class="r">Máximo</th>'
        '<th class="r">Total</th>'
        '</tr></thead>'
        '<tbody>' + "".join(rows_html) + '</tbody>'
        '</table></div>'
    )


# ── Modo TV ───────────────────────────────────────────────────────────────────

def _tv_nav(slide: int) -> None:
    """Barra de progresso dourada + dots + setas ‹ › ao redor (todos position:fixed)."""
    prev_s = (slide - 1) % _TV_N_SLIDES
    next_s = (slide + 1) % _TV_N_SLIDES
    tv_ini = st.query_params.get("tv_ini", "")
    _ini_param = f"&tv_ini={tv_ini}" if tv_ini else ""
    prev_url = f"?tv=1&slide={prev_s}{_ini_param}"
    next_url = f"?tv=1&slide={next_s}{_ini_param}"

    dots = "".join(
        f'<div style="width:8px;height:8px;border-radius:50%;background:'
        f'{"#FEC52E" if i == slide else "#2a2820"};flex-shrink:0"></div>'
        for i in range(_TV_N_SLIDES)
    )
    arrow = (
        "color:#FEC52E;text-decoration:none;font-size:18px;"
        "opacity:0.5;line-height:1;user-select:none"
    )
    # Nome único por slide: força o browser a reiniciar a animação em cada slide
    _ap = f"tvp{slide}"   # progress bar
    _af = f"tvf{slide}"   # fade-in do conteúdo
    st.markdown(f"""
    <style>
      @keyframes {_ap}{{from{{width:0%}}to{{width:100%}}}}
      @keyframes {_af}{{from{{opacity:0}}to{{opacity:1}}}}
      a.tv-arr:hover{{opacity:1!important}}
      body,html{{background:#0f0e0b!important}}
      section.main>.block-container{{animation:{_af} .4s ease}}
    </style>
    <div style="position:fixed;bottom:0;left:0;right:0;height:3px;background:#1a1814;z-index:9999">
      <div style="height:100%;background:#FEC52E;
           animation:{_ap} {_TV_INTERVAL_S}s linear forwards"></div>
    </div>
    <div style="position:fixed;bottom:10px;left:50%;transform:translateX(-50%);
         display:flex;gap:6px;align-items:center;z-index:9999">
      <a href="{prev_url}" class="tv-arr" style="{arrow}" target="_self">‹</a>
      {dots}
      <a href="{next_url}" class="tv-arr" style="{arrow}" target="_self">›</a>
    </div>
    <div style="position:fixed;top:10px;right:16px;color:#475569;
         font-size:11px;font-family:monospace;z-index:9999">
      {slide+1}/{_TV_N_SLIDES}</div>
    """, unsafe_allow_html=True)


def _tv_h(titulo: str, periodo: str = "") -> None:
    sub = f'<span style="color:#475569;font-size:13px;margin-left:12px">{periodo}</span>' if periodo else ""
    st.markdown(
        f'<div style="color:#FEC52E;font-size:17px;font-weight:700;'
        f'border-bottom:1px solid #272420;padding-bottom:8px;margin-bottom:14px">'
        f'{titulo}{sub}</div>',
        unsafe_allow_html=True,
    )


def _render_tv_slide(slide, _agg, _f, _fin, _n_dias, _dias_raw, _datas_sel, _periodo):
    n_rep = _f.get("reprovados", 0)
    n_ap  = _f.get("aprovados", 0)

    st.markdown("""
    <style>
    body,html{background:#0f0e0b!important}
    body,html,[data-testid="stAppViewContainer"],[data-testid="stMain"],section.main{
        overflow:hidden!important;height:100vh!important}
    header[data-testid="stHeader"]{display:none!important}
    footer{display:none!important}
    #MainMenu{display:none!important}
    [data-testid="stDeployButton"]{display:none!important}
    [data-testid="stStatusWidget"]{display:none!important}
    section.main>.block-container{
        padding:.5rem 1.5rem 2.5rem!important;max-width:100%!important;
        max-height:100vh!important;overflow:hidden!important}
    .js-plotly-plot .legend text,.js-plotly-plot .legendtext{
        font-size:14px!important}
    </style>
    """, unsafe_allow_html=True)

    if slide == 0:
        _tv_h("KPIs · Distribuição por Status · Funil de Conversão", _periodo)
        taxa  = f"{_f['taxa_aprovacao']:.1f}%" if _f.get("terminais") else "—"
        vol   = _fin.get("ValorContratacao", {})
        vol_s = f"R$ {vol['total']:,.0f}" if vol.get("total") else "—"
        ag    = _agg.get("aguardando", 0)
        st.markdown(f"""
        <div class="kpi-row">
          <div class="kpi-card"><div class="kpi-label">Total de leads</div>
            <div class="kpi-value">{_f['total']:,}</div><div class="kpi-sub">{_periodo}</div></div>
          <div class="kpi-card"><div class="kpi-label">Aprovados</div>
            <div class="kpi-value">{_f['aprovados']:,}</div><div class="kpi-sub">taxa: {taxa}</div></div>
          <div class="kpi-card"><div class="kpi-label">Taxa aprovação</div>
            <div class="kpi-value">{taxa}</div><div class="kpi-sub">{_f['terminais']:,} finalizados</div></div>
          <div class="kpi-card"><div class="kpi-label">Reprovados</div>
            <div class="kpi-value">{_f['reprovados']:,}</div>
            <div class="kpi-sub">{_f['taxa_reprovacao']:.1f}% dos finalizados</div></div>
          <div class="kpi-card"><div class="kpi-label">Volume aprovado</div>
            <div class="kpi-value">{vol_s}</div><div class="kpi-sub">valor contratado</div></div>
          <div class="kpi-card"><div class="kpi-label">Aguardando 24h</div>
            <div class="kpi-value">{ag:,}</div><div class="kpi-sub">BLOQUEIO_TEMPORARIO</div></div>
        </div>
        """, unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            fig = _fig_donut(_f.get("_d_status", {}))
            if fig:
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True, config=_CONF)
        with c2:
            fig = _fig_funil_rico(_f)
            if fig:
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True, config=_CONF)

    elif slide == 1:
        _tv_h("Evolução Temporal", _periodo)
        fig = _fig_evolucao(_agg, _n_dias, dias_raw=_dias_raw, datas_sel=_datas_sel)
        if fig:
            fig.update_layout(
                height=650, title=dict(text=""),
                margin=dict(t=20, b=20, l=10, r=20),
                legend=dict(orientation="v", x=0.70, y=1,
                            xanchor="left", yanchor="top",
                            bgcolor="rgba(15,14,11,0.80)",
                            bordercolor="rgba(255,255,255,0.08)",
                            borderwidth=1,
                            font=dict(size=14)),
            )
            st.plotly_chart(fig, use_container_width=True, config=_CONF)

    elif slide == 2:
        _tv_h("Estatísticas Financeiras dos Aprovados · Distribuição do Valor Contratado", _periodo)
        c1, c2 = st.columns(2)
        with c1:
            html = _html_tabela_financeira(_fin)
            if html:
                st.markdown(html, unsafe_allow_html=True)
        with c2:
            fig = _fig_histograma(_agg.get("valores_contratacao", []))
            if fig:
                fig.update_layout(height=430)
                st.plotly_chart(fig, use_container_width=True, config=_CONF)

    elif slide == 3:
        _tv_h("Etapas de Reprovação · Visão Detalhada", _periodo)
        etapas_d = _agg.get("etapas", {})
        if etapas_d and n_rep > 0:
            html_d = _html_diagrama(etapas_d, n_rep)
            if html_d:
                st.markdown(html_d, unsafe_allow_html=True)
            fig_d = _fig_etapas_split(etapas_d, n_rep)
            if fig_d:
                fig_d.update_traces(textposition="outside", cliponaxis=False)
                fig_d.update_layout(height=320, margin=dict(r=160))
                st.plotly_chart(fig_d, use_container_width=True, config=_CONF)
        else:
            st.info("Sem dados de etapas.")

    elif slide == 4:
        _tv_h("Etapas de Reprovação · Visão de Funil", _periodo)
        etapas_d = _agg.get("etapas", {})
        if etapas_d and n_rep > 0:
            html_d = _html_diagrama(etapas_d, n_rep)
            if html_d:
                st.markdown(html_d, unsafe_allow_html=True)
            result_f = _fig_funil_etapa(etapas_d, n_rep)
            if result_f:
                fig_f, _ = result_f
                fig_f.update_layout(
                    height=430,
                    legend=dict(orientation="v", x=0.82, y=0.04,
                                xanchor="left", yanchor="bottom",
                                bgcolor="rgba(15,14,11,0.80)",
                                bordercolor="rgba(255,255,255,0.08)",
                                borderwidth=1, font=dict(size=13)),
                    margin=dict(b=50),
                )
                st.plotly_chart(fig_f, use_container_width=True, config=_CONF)
        else:
            st.info("Sem dados de etapas.")

    elif slide == 5:
        _tv_h("Motivos de Reprovação — Alto Nível e Detalhado", _periodo)
        c1, c2 = st.columns(2)
        with c1:
            fig = _fig_barras_h(_agg.get("top_motivos", {}),
                                "Motivo — Alto Nível", "#ef4444", pct_base=n_rep)
            if fig:
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True, config=_CONF)
            else:
                st.info("Sem dados de motivos.")
        with c2:
            mot_det = _agg.get("top_motivos_det", {})
            if mot_det:
                n_det = sum(mot_det.values())
                fig = _fig_barras_h(mot_det, "Motivo — Detalhado", "#f97316", pct_base=n_det)
                if fig:
                    fig.update_layout(height=500)
                    st.plotly_chart(fig, use_container_width=True, config=_CONF)
            else:
                st.info("Sem dados de motivos detalhados.")

    elif slide == 6:
        _tv_h("Leads com Bloqueio por Tipo", _periodo)
        fig = _fig_bloqueios(_agg.get("bloqueios", {}), n_rep=n_rep)
        if fig:
            _, cc, _ = st.columns([1, 2, 1])
            with cc:
                fig.update_layout(height=400, margin=dict(t=60, b=30, l=10, r=10))
                st.plotly_chart(fig, use_container_width=True, config=_CONF)
        else:
            st.info("Sem dados de bloqueios.")

    elif slide == 7:
        _tv_h("Top Empregadores dos Reprovados · UF dos Reprovados", _periodo)
        c1, c2 = st.columns(2)
        with c1:
            emp_rep = _agg.get("top_emp_rep", {})
            if emp_rep:
                fig = _fig_barras_h(emp_rep, "Top Empregadores (Reprovados)", "#ef4444", pct_base=n_rep)
                if fig:
                    fig.update_layout(height=480)
                    st.plotly_chart(fig, use_container_width=True, config=_CONF)
            else:
                st.info("Sem dados de empregadores dos reprovados.")
        with c2:
            ufs = _agg.get("top_ufs", {})
            if ufs:
                n_ufs = sum(ufs.values())
                fig = _fig_barras_h(ufs, "UF dos Reprovados", "#3b82f6", n=10, pct_base=n_ufs)
                if fig:
                    fig.update_layout(height=480)
                    st.plotly_chart(fig, use_container_width=True, config=_CONF)
            else:
                st.info("Sem dados de UF.")

    elif slide == 8:
        _tv_h("CNAEs Bloqueados dos Reprovados", _periodo)
        cnaes = _agg.get("top_cnaes", {})
        if cnaes:
            n_cnae = sum(cnaes.values())
            c1, c2 = st.columns(2)
            with c1:
                fig = _fig_barras_h(_sem_codigo(cnaes), "Top CNAEs Bloqueados", "#eab308", pct_base=n_cnae)
                if fig:
                    fig.update_layout(height=500)
                    st.plotly_chart(fig, use_container_width=True, config=_CONF)
            with c2:
                tbl = _html_tabela_ranking(cnaes, "Descrição CNAE", n_cnae,
                                           code_col_title="Código CNAE")
                if tbl:
                    st.markdown(tbl, unsafe_allow_html=True)
        else:
            st.info("Sem dados de CNAE bloqueado.")

    elif slide == 9:
        _tv_h("CBOs Bloqueados dos Reprovados", _periodo)
        cbos_rep = _agg.get("top_cbos_rep", {})
        if cbos_rep:
            n_cbo_r = sum(cbos_rep.values())
            c1, c2 = st.columns(2)
            with c1:
                fig = _fig_barras_h(_sem_codigo(cbos_rep), "Top CBOs Bloqueados", "#a855f7", pct_base=n_cbo_r)
                if fig:
                    fig.update_layout(height=500)
                    st.plotly_chart(fig, use_container_width=True, config=_CONF)
            with c2:
                tbl = _html_tabela_ranking(cbos_rep, "Descrição CBO", n_cbo_r,
                                           code_col_title="Código CBO")
                if tbl:
                    st.markdown(tbl, unsafe_allow_html=True)
        else:
            st.info("Sem dados de CBO dos reprovados.")

    elif slide == 10:
        _tv_h("Top Empregadores dos Aprovados", _periodo)
        emp_ap = _agg.get("top_empregadores", {})
        if emp_ap:
            c1, c2 = st.columns(2)
            with c1:
                fig = _fig_barras_h(emp_ap, "Top Empregadores (Aprovados)", "#22c55e", pct_base=n_ap)
                if fig:
                    fig.update_layout(height=500)
                    st.plotly_chart(fig, use_container_width=True, config=_CONF)
            with c2:
                tbl = _html_tabela_ranking(emp_ap, "Razão Social", n_ap)
                if tbl:
                    st.markdown(tbl, unsafe_allow_html=True)
        else:
            st.info("Sem dados de empregadores dos aprovados.")

    elif slide == 11:
        _tv_h("Top CBOs dos Aprovados", _periodo)
        cbos_ap = _agg.get("top_cbos", {})
        if cbos_ap:
            c1, c2 = st.columns(2)
            with c1:
                fig = _fig_barras_h(_sem_codigo(cbos_ap), "Top CBOs (Aprovados)", "#3b82f6", pct_base=n_ap)
                if fig:
                    fig.update_layout(height=500)
                    st.plotly_chart(fig, use_container_width=True, config=_CONF)
            with c2:
                tbl = _html_tabela_ranking(cbos_ap, "Descrição CBO", n_ap,
                                           code_col_title="Código CBO")
                if tbl:
                    st.markdown(tbl, unsafe_allow_html=True)
        else:
            st.info("Sem dados de CBO dos aprovados.")

    _tv_nav(slide)


# ── Carrega datas disponiveis ─────────────────────────────────────────────────

datas = listar_datas()
if not datas:
    st.error("Sem dados disponíveis ou erro ao acessar o repositório.")
    st.stop()

data_min = datetime.strptime(datas[0],  "%Y%m%d").date()
data_max = datetime.strptime(datas[-1], "%Y%m%d").date()
d_ini_default = max(data_min, data_max - timedelta(days=1))

# ── Modo TV: atalho completo ──────────────────────────────────────────────────
if st.query_params.get("tv", "0") == "1":
    _tv_slide = int(st.query_params.get("slide", "0")) % _TV_N_SLIDES

    # CSS TV antecipado (evita flash antes de _render_tv_slide)
    st.markdown("""<style>
    body,html{background:#0f0e0b!important}
    body,html,[data-testid="stAppViewContainer"],[data-testid="stMain"],section.main{
        overflow:hidden!important;height:100vh!important}
    header[data-testid="stHeader"]{display:none!important}
    footer{display:none!important}
    #MainMenu{display:none!important}
    [data-testid="stDeployButton"]{display:none!important}
    [data-testid="stStatusWidget"]{display:none!important}
    section.main>.block-container{
        padding:.3rem 1.5rem 2rem!important;max-width:100%!important;
        max-height:100vh!important;overflow:hidden!important}
    .js-plotly-plot .legend text,.js-plotly-plot .legendtext{
        font-size:14px!important}
    </style>""", unsafe_allow_html=True)

    # Seletor de período
    _default_d_ini = max(data_min, data_max - timedelta(days=1))
    _tv_ini_raw = st.query_params.get("tv_ini", "")
    try:
        _d_ini_tv = (datetime.strptime(_tv_ini_raw, "%Y%m%d").date()
                     if _tv_ini_raw else _default_d_ini)
        _d_ini_tv = max(data_min, min(_d_ini_tv, data_max))
    except ValueError:
        _d_ini_tv = _default_d_ini

    _cp1, _cp2, _cp3, _cp4 = st.columns([1, 2, 4, 2])
    with _cp1:
        st.markdown(
            "<p style='margin:6px 0 0;color:#94a3b8;font-size:13px'>📅 Desde:</p>",
            unsafe_allow_html=True,
        )
    with _cp2:
        _new_ini = st.date_input(
            "", value=_d_ini_tv,
            min_value=data_min, max_value=data_max,
            key="tv_ini_picker", label_visibility="collapsed",
        )
    with _cp3:
        st.empty()
    with _cp4:
        if st.button("Sair do modo TV", key="tv_exit", use_container_width=True):
            st.query_params.clear()
            st.rerun()

    if _new_ini != _d_ini_tv:
        st.query_params["tv_ini"] = _new_ini.strftime("%Y%m%d")
        st.query_params["slide"] = "0"
        st.rerun()
    _d_ini_tv = _new_ini

    _datas_sel_tv = [d for d in datas
                     if _d_ini_tv <= datetime.strptime(d, "%Y%m%d").date() <= data_max]
    with st.spinner("Carregando..."):
        _dias_raw_tv = [d for d in [carregar_dia(d) for d in _datas_sel_tv] if d]
    if not _dias_raw_tv:
        st.warning("Sem dados para o período selecionado.")
        st.stop()
    _agg_tv = agregar(_dias_raw_tv)
    _periodo_tv = (
        _d_ini_tv.strftime("%d/%m/%Y") if _d_ini_tv == data_max
        else f"{_d_ini_tv.strftime('%d/%m/%Y')} — {data_max.strftime('%d/%m/%Y')}"
    )
    _render_tv_slide(
        _tv_slide, _agg_tv, _agg_tv["funil"], _agg_tv["financeiro"],
        len(_datas_sel_tv), _dias_raw_tv, _datas_sel_tv, _periodo_tv,
    )
    time.sleep(_TV_INTERVAL_S)
    st.query_params["slide"] = str((_tv_slide + 1) % _TV_N_SLIDES)
    st.rerun()

# ── Header + seletor ──────────────────────────────────────────────────────────

col_title, col_picker = st.columns([1, 1])

with col_title:
    _c_tit, _c_tv = st.columns([3, 1])
    with _c_tit:
        st.markdown(
            '<div style="display:flex;align-items:flex-end;gap:4px;margin:4px 0 6px">'
            '<svg viewBox="0 0 483 462" xmlns="http://www.w3.org/2000/svg" '
            'style="height:44px;width:auto;flex-shrink:0;display:block;'
            'margin-bottom:5px">'
            '<path d="M400.738 373.763C392.772 365.797 377.074 359.276 365.814 '
            '359.276H214.153C202.893 359.276 198.725 351.579 204.876 342.134L'
            '224.641 311.882C230.792 302.471 229.313 288.252 221.38 280.286L'
            '178.053 236.959C170.087 228.993 158.524 230.17 152.306 239.581L'
            '18.191 443.14C12.0063 452.551 16.1406 460.215 27.4009 460.215H'
            '466.753C478.014 460.215 480.703 453.694 472.736 445.728L400.738 '
            '373.729V373.763Z" fill="#FEC52E"/>'
            '<path d="M219.065 100.939C230.325 100.939 234.46 108.636 228.275 '
            '118.014L197.889 164.131C191.704 173.543 193.15 187.727 201.116 '
            '195.693L244.174 238.751C252.14 246.717 263.669 245.508 269.854 '
            '236.096L412.944 17.1424C419.095 7.73085 414.927 0 403.667 0H'
            '10.5652C-0.695032 0 -3.38405 6.52066 4.58217 14.4869L76.5807 '
            '86.4856C84.547 94.4518 100.244 100.972 111.504 100.972H219.065V'
            '100.939Z" fill="#FEC52E"/>'
            '</svg>'
            '<span style="font-size:28px;font-weight:700;line-height:1;'
            'color:#e2e8f0;letter-spacing:-0.5px">ilieads</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="periodo">Dados de {data_min.strftime("%d/%m/%Y")} '
            f'até {data_max.strftime("%d/%m/%Y")}</div>',
            unsafe_allow_html=True,
        )
    with _c_tv:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("📺 Modo TV", use_container_width=True):
            st.query_params["tv"] = "1"
            st.query_params["slide"] = "0"
            st.rerun()

with col_picker:
    intervalo = st.date_input(
        "Período de análise",
        value=(d_ini_default, data_max),
        min_value=data_min, max_value=data_max,
        format="DD/MM/YYYY",
    )

if isinstance(intervalo, (list, tuple)):
    d_ini, d_fim = (intervalo[0], intervalo[1]) if len(intervalo) == 2 else (intervalo[0], intervalo[0])
else:
    d_ini = d_fim = data_max

datas_sel = [d for d in datas if d_ini <= datetime.strptime(d, "%Y%m%d").date() <= d_fim]
n_dias    = len(datas_sel)

if not datas_sel:
    st.warning("Nenhum dado no período selecionado.")
    st.stop()

# ── Carrega e agrega ──────────────────────────────────────────────────────────

with st.spinner(f"Carregando {n_dias} dia(s)..."):
    dias_raw = [d for d in [carregar_dia(d) for d in datas_sel] if d]

if not dias_raw:
    st.warning("Sem dados para o período selecionado.")
    st.stop()

agg = agregar(dias_raw)
f   = agg["funil"]
fin = agg["financeiro"]

periodo_label = (
    d_ini.strftime("%d/%m/%Y") if d_ini == d_fim
    else f"{d_ini.strftime('%d/%m/%Y')} — {d_fim.strftime('%d/%m/%Y')}"
)

# ── KPIs ──────────────────────────────────────────────────────────────────────

taxa  = f"{f['taxa_aprovacao']:.1f}%" if f.get("terminais") else "—"
vol   = fin.get("ValorContratacao", {})
vol_s = f"R$ {vol['total']:,.0f}" if vol.get("total") else "—"
ag    = agg.get("aguardando", 0)

st.markdown(f"""
<div class="kpi-row">
  <div class="kpi-card">
    <div class="kpi-label">Total de leads</div>
    <div class="kpi-value">{f['total']:,}</div>
    <div class="kpi-sub">{periodo_label} · {n_dias} dia(s)</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Aprovados</div>
    <div class="kpi-value">{f['aprovados']:,}</div>
    <div class="kpi-sub">taxa: {taxa}</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Taxa de aprovação</div>
    <div class="kpi-value">{taxa}</div>
    <div class="kpi-sub">{f['terminais']:,} finalizados</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Reprovados</div>
    <div class="kpi-value">{f['reprovados']:,}</div>
    <div class="kpi-sub">{f['taxa_reprovacao']:.1f}% dos finalizados</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Volume aprovado</div>
    <div class="kpi-value">{vol_s}</div>
    <div class="kpi-sub">valor contratado total</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Aguardando 24h</div>
    <div class="kpi-value">{ag:,}</div>
    <div class="kpi-sub">BLOQUEIO_TEMPORARIO</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── 1. Distribuição por Status ────────────────────────────────────────────────

st.markdown('<div class="sec">1. Distribuição por Status</div>', unsafe_allow_html=True)

col_d, col_f = st.columns(2)
with col_d:
    fig = _fig_donut(f.get("_d_status", {}))
    if fig:
        st.plotly_chart(fig, use_container_width=True, config=_CONF)
with col_f:
    fig = _fig_funil_rico(f)
    if fig:
        st.plotly_chart(fig, use_container_width=True, config=_CONF)

# ── 2. Evolução Temporal ──────────────────────────────────────────────────────

st.markdown('<div class="sec">2. Evolução Temporal</div>', unsafe_allow_html=True)

fig = _fig_evolucao(agg, n_dias, dias_raw=dias_raw, datas_sel=datas_sel)
if fig:
    st.plotly_chart(fig, use_container_width=True, config=_CONF)

# ── 3. Perfil Financeiro — Aprovados ─────────────────────────────────────────

st.markdown('<div class="sec">3. Perfil Financeiro — Aprovados</div>', unsafe_allow_html=True)

html_fin = _html_tabela_financeira(fin)
if html_fin:
    st.markdown(html_fin, unsafe_allow_html=True)
    if n_dias > 1:
        st.caption("*Mediana = média ponderada das medianas diárias")

fig = _fig_histograma(agg.get("valores_contratacao", []))
if fig:
    st.plotly_chart(fig, use_container_width=True, config=_CONF)

# ── 4. Etapa de Reprovação ────────────────────────────────────────────────────

st.markdown('<div class="sec">4. Etapa de Reprovação</div>', unsafe_allow_html=True)

n_rep    = f.get("reprovados", 0)
etapas_d = agg.get("etapas", {})
etapa_motivos_d = agg.get("etapa_motivos", {})

# Diagrama do Workflow
diagrama_html = _html_diagrama(etapas_d, n_rep)
if diagrama_html:
    st.markdown(diagrama_html, unsafe_allow_html=True)
    st.markdown("")

# 3 abas: Visão Geral | Visão Detalhada | Visão de Funil
if etapas_d and n_rep > 0:
    tab_g, tab_d, tab_f = st.tabs(["Visão Geral", "Visão Detalhada", "Visão de Funil"])

    with tab_g:
        _order_idx = {e: i for i, e in enumerate(_ETAPA_WORKFLOW_ORDER)}
        ordered = sorted(
            [(e, etapas_d.get(e, 0)) for e in etapas_d if etapas_d.get(e, 0) > 0],
            key=lambda x: _order_idx.get(x[0], 999)
        )
        max_v = max(v for _, v in ordered) if ordered else 1
        y  = [e for e, _ in reversed(ordered)]
        x  = [v for _, v in reversed(ordered)]
        ps = [f"{100*v/n_rep:.1f}%" for v in reversed([v for _, v in ordered])]
        shades = [f"rgba(96,165,250,{0.40 + 0.55*(v/max_v):.2f})" for v in x]

        fig_g = go.Figure(go.Bar(
            x=x, y=y, orientation="h",
            marker=dict(color=shades, line=dict(color="#0d0c0a", width=0.5)),
            text=[f"{v:,} ({p})" for v, p in zip(x, ps)],
            textposition="inside", insidetextanchor="end",
            textfont=dict(size=11, color="rgba(255,255,255,0.85)"),
            hovertemplate="%{y}: <b>%{x:,}</b><extra></extra>",
        ))
        h = max(300, len(ordered) * 40 + 80)
        fig_g.update_layout(
            template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
            title=dict(text="Reprovados por Etapa de Workflow", font=_TF),
            xaxis=dict(title="Ocorrências", tickfont=_AF, showgrid=True, gridcolor=_GRID, zeroline=False),
            yaxis=dict(tickfont=dict(size=11, color="#cbd5e1"), automargin=True, zeroline=False),
            uniformtext_minsize=9, uniformtext_mode="hide",
            margin=dict(t=50, b=30, l=20, r=40), height=h,
        )
        st.plotly_chart(fig_g, use_container_width=True, config=_CONF)

        tbl_g = _html_tabela_etapa_motivo(etapa_motivos_d, etapas_d, n_rep)
        if tbl_g:
            st.markdown(tbl_g, unsafe_allow_html=True)

    with tab_d:
        fig_d = _fig_etapas_split(etapas_d, n_rep)
        if fig_d:
            st.plotly_chart(fig_d, use_container_width=True, config=_CONF)

        tbl_d = _html_tabela_etapa_motivo(etapa_motivos_d, etapas_d, n_rep)
        if tbl_d:
            st.markdown(tbl_d, unsafe_allow_html=True)

    with tab_f:
        result_f = _fig_funil_etapa(etapas_d, n_rep)
        if result_f:
            fig_f, rows_f = result_f
            st.plotly_chart(fig_f, use_container_width=True, config=_CONF)
            tbl_resumo = _html_tabela_resumo_funil(rows_f)
            if tbl_resumo:
                st.markdown(tbl_resumo, unsafe_allow_html=True)
else:
    st.info("Sem dados de etapas (JSONs desta data ainda não possuem o campo).")

# ── 5. Motivos de Reprovação ──────────────────────────────────────────────────

st.markdown('<div class="sec">5. Motivos de Reprovação</div>', unsafe_allow_html=True)

col_m1, col_m2 = st.columns(2)

with col_m1:
    fig = _fig_barras_h(agg.get("top_motivos", {}),
                        "Motivo de Reprovação — Alto Nível", "#ef4444", pct_base=n_rep)
    if fig:
        st.plotly_chart(fig, use_container_width=True, config=_CONF)
    else:
        st.info("Sem dados de motivos.")

with col_m2:
    mot_det = agg.get("top_motivos_det", {})
    if mot_det:
        n_det = sum(mot_det.values())
        fig = _fig_barras_h(mot_det, "Motivo de Reprovação — Detalhado", "#f97316",
                            pct_base=n_det)
        if fig:
            st.plotly_chart(fig, use_container_width=True, config=_CONF)
    else:
        st.info("Motivos detalhados ainda não disponíveis (requer nova exportação dos JSONs).")

# ── 6. Bloqueios ──────────────────────────────────────────────────────────────

st.markdown('<div class="sec">6. Bloqueios por Tipo</div>', unsafe_allow_html=True)

fig = _fig_bloqueios(agg.get("bloqueios", {}), n_rep=n_rep)
if fig:
    col_bl, _ = st.columns([1, 1])
    with col_bl:
        st.plotly_chart(fig, use_container_width=True, config=_CONF)
else:
    st.info("Sem dados de bloqueios.")

# ── 7. Segmentação — Reprovados ───────────────────────────────────────────────

st.markdown('<div class="sec">7. Segmentação — Reprovados</div>', unsafe_allow_html=True)

col_s1, col_s2 = st.columns(2)

with col_s1:
    emp_rep = agg.get("top_emp_rep", {})
    if emp_rep:
        fig = _fig_barras_h(emp_rep, "Top Empregadores dos Reprovados", "#ef4444", pct_base=n_rep)
        if fig:
            st.plotly_chart(fig, use_container_width=True, config=_CONF)
        tbl = _html_tabela_ranking(emp_rep, "Razão Social", n_rep)
        if tbl:
            st.markdown(tbl, unsafe_allow_html=True)
    else:
        st.info("Sem dados de empregadores dos reprovados (requer nova exportação dos JSONs).")

with col_s2:
    ufs = agg.get("top_ufs", {})
    if ufs:
        n_ufs = sum(ufs.values())
        fig = _fig_barras_h(ufs, "UF dos Reprovados", "#3b82f6", pct_base=n_ufs)
        if fig:
            st.plotly_chart(fig, use_container_width=True, config=_CONF)
        tbl = _html_tabela_ranking(ufs, "UF", n_ufs)
        if tbl:
            st.markdown(tbl, unsafe_allow_html=True)
    else:
        st.info("Sem dados de UF dos reprovados.")

col_s3, col_s4 = st.columns(2)

with col_s3:
    cnaes = agg.get("top_cnaes", {})
    if cnaes:
        n_cnae = sum(cnaes.values())
        fig = _fig_barras_h(_sem_codigo(cnaes), "Top CNAEs Bloqueados (Reprovados)", "#eab308",
                            pct_base=n_cnae)
        if fig:
            st.plotly_chart(fig, use_container_width=True, config=_CONF)
        tbl = _html_tabela_ranking(cnaes, "Descrição CNAE", n_cnae, code_col_title="Código CNAE")
        if tbl:
            st.markdown(tbl, unsafe_allow_html=True)
    else:
        st.info("Sem dados de CNAE bloqueado.")

with col_s4:
    cbos_rep = agg.get("top_cbos_rep", {})
    if cbos_rep:
        n_cbo_r = sum(cbos_rep.values())
        fig = _fig_barras_h(_sem_codigo(cbos_rep), "Top CBOs Bloqueados (Reprovados)", "#a855f7",
                            pct_base=n_cbo_r)
        if fig:
            st.plotly_chart(fig, use_container_width=True, config=_CONF)
        tbl = _html_tabela_ranking(cbos_rep, "Descrição CBO", n_cbo_r, code_col_title="Código CBO")
        if tbl:
            st.markdown(tbl, unsafe_allow_html=True)
    else:
        st.info("Sem dados de CBO dos reprovados.")

# ── 8. Aprovados — Empregadores e CBOs ───────────────────────────────────────

st.markdown('<div class="sec">8. Aprovados — Empregadores e CBOs</div>', unsafe_allow_html=True)

n_ap = f.get("aprovados", 0)

col_e, col_c = st.columns(2)

with col_e:
    emp_ap = agg.get("top_empregadores", {})
    fig = _fig_barras_h(emp_ap, "Top Empregadores (Aprovados)", "#22c55e", pct_base=n_ap)
    if fig:
        st.plotly_chart(fig, use_container_width=True, config=_CONF)
    tbl = _html_tabela_ranking(emp_ap, "Razão Social", n_ap)
    if tbl:
        st.markdown(tbl, unsafe_allow_html=True)

with col_c:
    cbos_ap = agg.get("top_cbos", {})
    fig = _fig_barras_h(_sem_codigo(cbos_ap), "Top CBOs (Aprovados)", "#3b82f6", pct_base=n_ap)
    if fig:
        st.plotly_chart(fig, use_container_width=True, config=_CONF)
    tbl = _html_tabela_ranking(cbos_ap, "Descrição CBO", n_ap, code_col_title="Código CBO")
    if tbl:
        st.markdown(tbl, unsafe_allow_html=True)
