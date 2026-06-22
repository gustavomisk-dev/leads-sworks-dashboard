"""
Dashboard de leads SWorks — Streamlit Community Cloud.
Dados lidos do repositorio privado leads-sworks-data via GitHub API.
"""

import json
import requests
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from collections import defaultdict

# ── Pagina ───────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Leads SWorks",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* Esconde sidebar toggle */
[data-testid="collapsedControl"] { display: none; }

/* KPI cards */
.kpi-row { display: flex; gap: 12px; margin: 16px 0 24px; }
.kpi-card {
    flex: 1;
    background: #131210;
    border-radius: 10px;
    padding: 16px 18px;
    border: 1px solid #272420;
    text-align: center;
    min-width: 0;
}
.kpi-label { color: #94a3b8; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; margin-bottom: 6px; }
.kpi-value { color: #FEC52E; font-size: 26px; font-weight: 700; line-height: 1.1; }
.kpi-sub   { color: #64748b; font-size: 11px; margin-top: 5px; }

/* Secao title */
.sec { color: #FEC52E; font-size: 15px; font-weight: 600; margin: 28px 0 6px;
       border-bottom: 1px solid #272420; padding-bottom: 6px; }

/* Periodo label */
.periodo { color: #64748b; font-size: 13px; margin-bottom: 4px; }
</style>
""", unsafe_allow_html=True)

# ── Secrets ───────────────────────────────────────────────────────────────────

try:
    _TOKEN = st.secrets["github"]["token"]
    _REPO  = st.secrets["github"]["repo"]
except Exception:
    st.error("Secrets do GitHub nao configurados. Adicione [github] token e repo em Settings > Secrets.")
    st.stop()

_HEADERS_RAW  = {"Authorization": f"Bearer {_TOKEN}", "Accept": "application/vnd.github.v3.raw"}
_HEADERS_JSON = {"Authorization": f"Bearer {_TOKEN}"}

# ── Constantes ────────────────────────────────────────────────────────────────

_STATUS_NOMES = {
    0: "Novo",
    1: "Pendente",
    2: "Em Processamento",
    3: "Aprovado",
    4: "Reprovado",
    5: "Suspenso",
    6: "Pendente Manual",
    7: "Pendente Falha",
    8: "Cancelado",
}

_STATUS_CORES = {
    3: "#22c55e",
    4: "#ef4444",
    5: "#f59e0b",
    2: "#3b82f6",
    0: "#94a3b8",
    7: "#a855f7",
    8: "#64748b",
    1: "#6366f1",
    6: "#ec4899",
}

_ETAPA_ORDER = [
    "Validações Internas",
    "Receita Federal PF",
    "Consulta Dataprev",
    "Receita Federal PJ",
    "Análise PH3A (PJ)",
    "Análise PH3A (PF)",
    "SCR",
    "Cálculo de Proposta",
]

_TEMPLATE = "plotly_dark"
_CONF     = {"displayModeBar": False, "responsive": True}
_GRID     = "rgba(255,255,255,0.06)"
_BG       = "rgba(0,0,0,0)"
_TF       = dict(size=14, color="#FEC52E")
_AF       = dict(size=11, color="#94a3b8")

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
    d_status      = defaultdict(int)
    fin_n         = defaultdict(int)
    fin_total     = defaultdict(float)
    fin_min       = {}
    fin_max       = {}
    fin_med_sum   = defaultdict(float)
    evolucao_d    = defaultdict(lambda: defaultdict(int))
    evolucao_h    = defaultdict(lambda: defaultdict(int))
    motivos       = defaultdict(int)
    empregadores  = defaultdict(int)
    cbos          = defaultdict(int)
    bloqueios     = defaultdict(int)
    etapas        = defaultdict(int)
    valores_cont  = []
    aguardando    = 0

    for d in dias_raw:
        for k, v in d.get("funil", {}).get("_d_status", {}).items():
            d_status[int(k)] += v

        for campo, s in d.get("financeiro", {}).items():
            n = s.get("n", 0)
            if n > 0:
                fin_n[campo]      += n
                fin_total[campo]  += s.get("total", 0.0)
                fin_med_sum[campo] += s.get("mediana", 0.0) * n
                v_min = s.get("min", float("inf"))
                v_max = s.get("max", float("-inf"))
                fin_min[campo] = min(fin_min.get(campo, float("inf")), v_min)
                fin_max[campo] = max(fin_max.get(campo, float("-inf")), v_max)

        for dt, cont in d.get("evolucao_diaria", {}).items():
            for sk, cnt in cont.items():
                evolucao_d[dt][int(sk)] += cnt

        for hr, cont in d.get("evolucao_horaria", {}).items():
            for sk, cnt in cont.items():
                evolucao_h[hr][int(sk)] += cnt

        for k, v in d.get("top_motivos", {}).items():
            if k:
                motivos[k] += v
        for k, v in d.get("top_empregadores", {}).items():
            if k:
                empregadores[k] += v
        for k, v in d.get("top_cbos", {}).items():
            if k:
                cbos[k] += v

        for k, v in d.get("bloqueios", {}).items():
            bloqueios[k] += v
        for k, v in d.get("etapas", {}).items():
            etapas[k] += v

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

    return {
        "funil":            funil,
        "financeiro":       financeiro,
        "evolucao_diaria":  {k: dict(v) for k, v in sorted(evolucao_d.items())},
        "evolucao_horaria": {k: dict(v) for k, v in sorted(evolucao_h.items())},
        "top_motivos":      dict(sorted(motivos.items(),     key=lambda x: -x[1])[:20]),
        "top_empregadores": dict(sorted(empregadores.items(),key=lambda x: -x[1])[:15]),
        "top_cbos":         dict(sorted(cbos.items(),        key=lambda x: -x[1])[:15]),
        "bloqueios":        dict(bloqueios),
        "etapas":           dict(etapas),
        "valores_contratacao": valores_cont,
        "aguardando":       aguardando,
    }

# ── Chart builders ────────────────────────────────────────────────────────────

def _fig_donut(d_status: dict):
    items = sorted([(s, n) for s, n in d_status.items() if n > 0], key=lambda x: -x[1])
    labels = [_STATUS_NOMES.get(s, f"Status {s}") for s, _ in items]
    values = [n for _, n in items]
    colors = [_STATUS_CORES.get(s, "#666") for s, _ in items]
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
        margin=dict(t=50, b=10, l=10, r=10), height=340,
    )
    return fig


def _fig_funil(funil: dict):
    total     = funil.get("total", 0)
    terminais = funil.get("terminais", 0)
    aprovados = funil.get("aprovados", 0)

    fig = go.Figure(go.Funnel(
        y=["Total", "Finalizados", "Aprovados"],
        x=[total, terminais, aprovados],
        textposition="inside",
        textinfo="value+percent initial",
        marker=dict(
            color=["#1e3a5f", "#15406b", "#166534"],
            line=dict(color="#0d0c0a", width=1.5),
        ),
        textfont=dict(color="#e2e8f0", size=13),
        connector=dict(line=dict(color="#272420", width=2)),
        hovertemplate="%{y}: <b>%{x:,}</b><extra></extra>",
    ))
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text="Funil de Conversão", font=_TF),
        margin=dict(t=50, b=10, l=10, r=10), height=340,
    )
    return fig


def _fig_evolucao(agg: dict, n_dias: int):
    if n_dias == 1:
        ev     = agg["evolucao_horaria"]
        eixo   = sorted(ev.keys())
        titulo = "Evolução Horária"
        xlab   = "Hora"
    else:
        ev     = agg["evolucao_diaria"]
        eixo   = sorted(ev.keys())
        titulo = "Evolução Diária"
        xlab   = "Data"

    if not eixo:
        return None

    fig = go.Figure()
    for s in [3, 4, 5, 2, 0, 7, 8]:
        y = [ev.get(x, {}).get(s, 0) for x in eixo]
        if sum(y) == 0:
            continue
        fig.add_trace(go.Scatter(
            x=eixo, y=y,
            name=_STATUS_NOMES.get(s, str(s)),
            mode="lines+markers",
            line=dict(color=_STATUS_CORES.get(s, "#aaa"), width=2),
            marker=dict(size=5),
            hovertemplate=f"{_STATUS_NOMES.get(s, str(s))}: %{{y:,}}<extra></extra>",
        ))
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text=titulo, font=_TF),
        xaxis=dict(title=xlab, tickfont=_AF, showgrid=True, gridcolor=_GRID),
        yaxis=dict(title="Leads", tickfont=_AF, showgrid=True, gridcolor=_GRID),
        legend=dict(font=dict(size=10, color="#94a3b8"), bgcolor=_BG,
                    orientation="h", y=-0.20, x=0.5, xanchor="center"),
        margin=dict(t=50, b=60, l=10, r=10), height=340,
        hovermode="x unified",
    )
    return fig


def _fig_barras_h(data_dict: dict, titulo: str, color: str, n: int = 15):
    items = list(data_dict.items())[:n]
    if not items:
        return None
    labels = [k for k, _ in items]
    values = [v for _, v in items]
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker=dict(color=color, line=dict(color="#0d0c0a", width=0.5)),
        text=[f"{v:,}" for v in values],
        textposition="outside",
        textfont=dict(size=10, color="#94a3b8"),
        hovertemplate="%{y}: <b>%{x:,}</b><extra></extra>",
    ))
    h = max(280, len(items) * 32 + 80)
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text=titulo, font=_TF),
        xaxis=dict(tickfont=_AF, showgrid=True, gridcolor=_GRID, zeroline=False),
        yaxis=dict(tickfont=dict(size=10, color="#cbd5e1"), autorange="reversed",
                   automargin=True),
        margin=dict(t=50, b=20, l=20, r=60), height=h,
    )
    return fig


def _fig_etapas(etapas: dict, n_rep: int):
    if not etapas or n_rep == 0:
        return None
    ordered = [(e, etapas.get(e, 0)) for e in _ETAPA_ORDER if etapas.get(e, 0) > 0]
    ordered += [(e, v) for e, v in etapas.items() if e not in _ETAPA_ORDER and v > 0]
    if not ordered:
        return None

    labels = [e for e, _ in reversed(ordered)]
    values = [v for _, v in reversed(ordered)]
    pcts   = [f"{v/n_rep*100:.1f}%" for v in values]

    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker=dict(
            color=[f"rgba(251,146,60,{0.45 + 0.50*(v/n_rep):.2f})" for v in values],
            line=dict(color="#0d0c0a", width=0.5),
        ),
        text=[f"{v:,} ({p})" for v, p in zip(values, pcts)],
        textposition="inside", insidetextanchor="middle",
        textfont=dict(size=10, color="rgba(255,255,255,0.90)"),
        hovertemplate="%{y}: <b>%{x:,}</b><extra></extra>",
    ))
    h = max(280, len(ordered) * 44 + 80)
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text="Reprovados por Etapa", font=_TF),
        xaxis=dict(title="Leads", tickfont=_AF, showgrid=True, gridcolor=_GRID, zeroline=False),
        yaxis=dict(tickfont=dict(size=11, color="#cbd5e1"), automargin=True),
        margin=dict(t=50, b=20, l=20, r=40), height=h,
    )
    return fig


def _fig_histograma(valores: list):
    if not valores:
        return None
    fig = go.Figure(go.Histogram(
        x=valores, nbinsx=35,
        marker=dict(color="#FEC52E", line=dict(color="#0d0c0a", width=0.5)),
        hovertemplate="R$ %{x:,.0f}: %{y:,} contratos<extra></extra>",
    ))
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text="Distribuição — Valor Contratado", font=_TF),
        xaxis=dict(title="Valor (R$)", tickfont=_AF, showgrid=True, gridcolor=_GRID,
                   tickprefix="R$ ", tickformat=",.0f"),
        yaxis=dict(title="Contratos", tickfont=_AF, showgrid=True, gridcolor=_GRID),
        bargap=0.05,
        margin=dict(t=50, b=40, l=10, r=10), height=300,
    )
    return fig


def _fig_bloqueios(bloqueios: dict):
    if not any(bloqueios.values()):
        return None
    nomes = {"cpf": "CPF Bloqueado", "cnpj": "CNPJ Bloqueado",
             "cnae": "CNAE Bloqueado", "cbo": "CBO Bloqueado"}
    cores = {"cpf": "#ef4444", "cnpj": "#f97316", "cnae": "#eab308", "cbo": "#a855f7"}
    labels = [nomes.get(k, k) for k, v in bloqueios.items() if v > 0]
    values = [v for v in bloqueios.values() if v > 0]
    colors = [cores.get(k, "#666") for k, v in bloqueios.items() if v > 0]
    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker=dict(color=colors, line=dict(color="#0d0c0a", width=0.5)),
        text=[f"{v:,}" for v in values],
        textposition="outside",
        textfont=dict(size=12, color="#e2e8f0"),
        hovertemplate="%{x}: <b>%{y:,}</b><extra></extra>",
    ))
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text="Leads com Bloqueio por Tipo", font=_TF),
        xaxis=dict(tickfont=dict(size=12, color="#cbd5e1")),
        yaxis=dict(tickfont=_AF, showgrid=True, gridcolor=_GRID),
        margin=dict(t=50, b=10, l=10, r=10), height=280,
    )
    return fig

# ── Carrega datas disponiveis ─────────────────────────────────────────────────

datas = listar_datas()
if not datas:
    st.error("Sem dados disponíveis ou erro ao acessar o repositório.")
    st.stop()

data_min = datetime.strptime(datas[0],  "%Y%m%d").date()
data_max = datetime.strptime(datas[-1], "%Y%m%d").date()
d_ini_default = max(data_min, data_max - timedelta(days=6))

# ── Header + seletor de periodo ───────────────────────────────────────────────

col_title, col_picker = st.columns([1, 1])

with col_title:
    st.markdown("## 📊 Leads SWorks")
    st.markdown(
        f'<div class="periodo">Dados de {data_min.strftime("%d/%m/%Y")} '
        f'até {data_max.strftime("%d/%m/%Y")}</div>',
        unsafe_allow_html=True,
    )

with col_picker:
    intervalo = st.date_input(
        "Período de análise",
        value=(d_ini_default, data_max),
        min_value=data_min,
        max_value=data_max,
        format="DD/MM/YYYY",
    )

if isinstance(intervalo, (list, tuple)):
    if len(intervalo) == 2:
        d_ini, d_fim = intervalo[0], intervalo[1]
    else:
        d_ini = d_fim = intervalo[0]
else:
    d_ini = d_fim = data_max

datas_sel = [
    d for d in datas
    if d_ini <= datetime.strptime(d, "%Y%m%d").date() <= d_fim
]
n_dias = len(datas_sel)

if not datas_sel:
    st.warning("Nenhum dado no período selecionado.")
    st.stop()

# ── Carrega e agrega ──────────────────────────────────────────────────────────

with st.spinner(f"Carregando {n_dias} dia(s)..."):
    dias_raw = [carregar_dia(d) for d in datas_sel]
    dias_raw = [d for d in dias_raw if d]

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

# ── Secao 1 — Distribuicao por status + funil ─────────────────────────────────

st.markdown('<div class="sec">Distribuição por Status</div>', unsafe_allow_html=True)

col_d, col_f = st.columns(2)
with col_d:
    fig = _fig_donut(f.get("_d_status", {}))
    if fig:
        st.plotly_chart(fig, use_container_width=True, config=_CONF)

with col_f:
    fig = _fig_funil(f)
    if fig:
        st.plotly_chart(fig, use_container_width=True, config=_CONF)

# ── Secao 2 — Evolucao temporal ───────────────────────────────────────────────

st.markdown('<div class="sec">Evolução Temporal</div>', unsafe_allow_html=True)

fig = _fig_evolucao(agg, n_dias)
if fig:
    st.plotly_chart(fig, use_container_width=True, config=_CONF)

# ── Secao 3 — Reprovados (Etapas + Motivos) ───────────────────────────────────

st.markdown('<div class="sec">Reprovados</div>', unsafe_allow_html=True)

col_e, col_m = st.columns(2)

with col_e:
    fig = _fig_etapas(agg.get("etapas", {}), f.get("reprovados", 0))
    if fig:
        st.plotly_chart(fig, use_container_width=True, config=_CONF)
    else:
        st.info("Sem dados de etapas (JSONs desta data ainda não possuem o campo).")

with col_m:
    fig = _fig_barras_h(agg.get("top_motivos", {}), "Top Motivos de Reprovação", "#ef4444")
    if fig:
        st.plotly_chart(fig, use_container_width=True, config=_CONF)
    else:
        st.info("Sem dados de motivos.")

# ── Secao 4 — Aprovados (Histograma + Financeiro) ────────────────────────────

st.markdown('<div class="sec">Aprovados — Perfil Financeiro</div>', unsafe_allow_html=True)

col_h, col_fin = st.columns([1.2, 1])

with col_h:
    fig = _fig_histograma(agg.get("valores_contratacao", []))
    if fig:
        st.plotly_chart(fig, use_container_width=True, config=_CONF)

with col_fin:
    st.markdown("**Estatísticas dos aprovados**")
    _CAMPOS_FIN = [
        ("ValorContratacao", "Valor contratado", "R$",     True),
        ("Prazo",            "Prazo",             "meses",  False),
        ("Taxa",             "Taxa de juros",     "% a.m.", False),
        ("RendaLiquida",     "Renda líquida",     "R$",     True),
    ]
    for campo, label, unid, is_money in _CAMPOS_FIN:
        s = fin.get(campo)
        if not s or s.get("n", 0) == 0:
            continue

        def _fmt(v, _is_money=is_money, _unid=unid):
            if _is_money:
                return f"R$ {v:,.2f}"
            return f"{v:,.2f} {_unid}"

        with st.expander(f"**{label}** — n = {s['n']:,}", expanded=True):
            c1, c2, c3 = st.columns(3)
            c1.metric("Média",    _fmt(s["media"]))
            c2.metric("Mediana*", _fmt(s["mediana"]))
            c3.metric("Total",    f"R$ {s['total']:,.0f}" if is_money else _fmt(s["total"]))
            c4, c5 = st.columns(2)
            c4.metric("Mínimo", _fmt(s["min"]))
            c5.metric("Máximo", _fmt(s["max"]))

    if n_dias > 1:
        st.caption("\\* Mediana = média ponderada das medianas diárias")

# ── Secao 5 — Empregadores + CBOs ─────────────────────────────────────────────

st.markdown('<div class="sec">Top Empregadores e CBOs (Aprovados)</div>', unsafe_allow_html=True)

col_emp, col_cbo = st.columns(2)

with col_emp:
    fig = _fig_barras_h(agg.get("top_empregadores", {}), "Top Empregadores", "#22c55e")
    if fig:
        st.plotly_chart(fig, use_container_width=True, config=_CONF)

with col_cbo:
    fig = _fig_barras_h(agg.get("top_cbos", {}), "Top CBOs", "#3b82f6")
    if fig:
        st.plotly_chart(fig, use_container_width=True, config=_CONF)

# ── Secao 6 — Bloqueios ───────────────────────────────────────────────────────

st.markdown('<div class="sec">Bloqueios por Tipo</div>', unsafe_allow_html=True)

fig = _fig_bloqueios(agg.get("bloqueios", {}))
if fig:
    col_bl, _ = st.columns([1, 1])
    with col_bl:
        st.plotly_chart(fig, use_container_width=True, config=_CONF)
else:
    st.info("Sem dados de bloqueios (campo ausente nos JSONs desta data).")
