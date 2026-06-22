"""
Dashboard de leads SWorks — Streamlit Community Cloud.
Dados lidos do repositorio privado leads-sworks-data via GitHub API.
"""

import json
import requests
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta
from collections import defaultdict

# ── Pagina ───────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Leads SWorks",
    page_icon="📊",
    layout="wide",
)

# ── Secrets ───────────────────────────────────────────────────────────────────

try:
    _TOKEN = st.secrets["github"]["token"]
    _REPO  = st.secrets["github"]["repo"]
except Exception:
    st.error("Secrets do GitHub nao configurados. Adicione [github] token e repo em Settings > Secrets.")
    st.stop()

_HEADERS_RAW  = {"Authorization": f"Bearer {_TOKEN}", "Accept": "application/vnd.github.v3.raw"}
_HEADERS_JSON = {"Authorization": f"Bearer {_TOKEN}"}

_STATUS_NOMES = {
    0: "Novo",
    2: "Em Processamento",
    3: "Aprovado",
    4: "Reprovado",
    5: "Suspenso",
    7: "Pendente Falha",
}

_STATUS_CORES = {
    3: "#2ecc71",
    4: "#e74c3c",
    5: "#f39c12",
    2: "#3498db",
    0: "#95a5a6",
    7: "#9b59b6",
}

# ── GitHub API ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def listar_datas() -> list:
    """Retorna lista de datas YYYYMMDD disponiveis no repo privado."""
    url = f"https://api.github.com/repos/{_REPO}/contents/dados"
    r = requests.get(url, headers=_HEADERS_JSON)
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
    """Busca e parseia o JSON de um dia do repo privado."""
    url = f"https://api.github.com/repos/{_REPO}/contents/dados/{dia_str}.json"
    r = requests.get(url, headers=_HEADERS_RAW)
    if r.status_code == 200:
        return json.loads(r.text)
    return {}

# ── Agregacao ─────────────────────────────────────────────────────────────────

def agregar(dias_data: list) -> dict:
    funil      = defaultdict(int)
    fin_lista  = defaultdict(list)
    evolucao   = defaultdict(lambda: defaultdict(int))
    motivos    = defaultdict(int)
    empregadores = defaultdict(int)
    cbos       = defaultdict(int)

    for d in dias_data:
        f = d.get("funil", {})
        for k in ("total", "aprovados", "reprovados", "cancelados", "em_curso"):
            funil[k] += f.get(k, 0)

        for campo, s in d.get("financeiro", {}).items():
            if s.get("n", 0) > 0:
                fin_lista[campo].append(s)

        for hora, cont in d.get("evolucao_horaria", {}).items():
            for status_str, cnt in cont.items():
                evolucao[hora][int(status_str)] += cnt

        for k, v in d.get("top_motivos", {}).items():
            if k:
                motivos[k] += v
        for k, v in d.get("top_empregadores", {}).items():
            if k:
                empregadores[k] += v
        for k, v in d.get("top_cbos", {}).items():
            if k:
                cbos[k] += v

    terminais = funil["aprovados"] + funil["reprovados"] + funil["cancelados"]
    funil["taxa_aprovacao"]  = funil["aprovados"]  / terminais * 100 if terminais else 0.0
    funil["taxa_reprovacao"] = funil["reprovados"] / terminais * 100 if terminais else 0.0

    financeiro = {}
    for campo, lista in fin_lista.items():
        n_total    = sum(s["n"]     for s in lista)
        soma_total = sum(s["total"] for s in lista)
        financeiro[campo] = {
            "n":     n_total,
            "media": soma_total / n_total if n_total else 0,
            "min":   min(s["min"] for s in lista),
            "max":   max(s["max"] for s in lista),
        }

    return {
        "funil":            dict(funil),
        "financeiro":       financeiro,
        "evolucao":         {h: dict(c) for h, c in sorted(evolucao.items())},
        "top_motivos":      dict(sorted(motivos.items(),      key=lambda x: -x[1])[:20]),
        "top_empregadores": dict(sorted(empregadores.items(), key=lambda x: -x[1])[:15]),
        "top_cbos":         dict(sorted(cbos.items(),         key=lambda x: -x[1])[:15]),
    }

# ── Sidebar / filtros ─────────────────────────────────────────────────────────

datas = listar_datas()
if not datas:
    st.error("Sem dados disponiveis ou erro ao acessar o repositorio.")
    st.stop()

data_min = datetime.strptime(datas[0],  "%Y%m%d").date()
data_max = datetime.strptime(datas[-1], "%Y%m%d").date()

with st.sidebar:
    st.header("Filtros")
    intervalo = st.date_input(
        "Periodo",
        value=(max(data_min, data_max - timedelta(days=6)), data_max),
        min_value=data_min,
        max_value=data_max,
        format="DD/MM/YYYY",
    )

if isinstance(intervalo, (list, tuple)) and len(intervalo) == 2:
    d_ini, d_fim = intervalo
elif isinstance(intervalo, (list, tuple)) and len(intervalo) == 1:
    d_ini = d_fim = intervalo[0]
else:
    d_ini = d_fim = data_max

datas_sel = [
    d for d in datas
    if d_ini <= datetime.strptime(d, "%Y%m%d").date() <= d_fim
]

if not datas_sel:
    st.warning("Nenhum dado no periodo selecionado.")
    st.stop()

# ── Carrega dados ─────────────────────────────────────────────────────────────

with st.spinner(f"Carregando {len(datas_sel)} dia(s)..."):
    dias_raw = [carregar_dia(d) for d in datas_sel]
    dias_raw = [d for d in dias_raw if d]

if not dias_raw:
    st.warning("Sem dados para o periodo selecionado.")
    st.stop()

agg = agregar(dias_raw)
f   = agg["funil"]
fin = agg["financeiro"]

periodo_label = (
    d_ini.strftime("%d/%m/%Y") if d_ini == d_fim
    else f"{d_ini.strftime('%d/%m/%Y')} a {d_fim.strftime('%d/%m/%Y')}"
)

# ── Cabecalho ─────────────────────────────────────────────────────────────────

st.title("📊 Dashboard Leads SWorks")
st.caption(f"Periodo: {periodo_label}  ·  {len(datas_sel)} dia(s)  ·  {f['total']:,} leads")

st.divider()

# ── Funil ─────────────────────────────────────────────────────────────────────

st.subheader("Funil")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total",        f"{f['total']:,}")
c2.metric("Aprovados",    f"{f['aprovados']:,}",  f"{f['taxa_aprovacao']:.1f}%")
c3.metric("Reprovados",   f"{f['reprovados']:,}", f"{f['taxa_reprovacao']:.1f}%")
c4.metric("Cancelados",   f"{f['cancelados']:,}")
c5.metric("Em andamento", f"{f['em_curso']:,}")

st.divider()

# ── Financeiro ────────────────────────────────────────────────────────────────

st.subheader("Financeiro — aprovados")
fc1, fc2, fc3, fc4 = st.columns(4)

def _metrica_fin(col, campo, label, prefix="", suffix="", dec=2):
    s = fin.get(campo, {})
    if s.get("n", 0) == 0:
        col.metric(label, "—")
        return
    col.metric(label, f"{prefix}{s['media']:,.{dec}f}{suffix}", f"n = {s['n']}")

_metrica_fin(fc1, "ValorContratacao", "Valor medio",  prefix="R$ ")
_metrica_fin(fc2, "Prazo",            "Prazo medio",  suffix=" meses", dec=0)
_metrica_fin(fc3, "Taxa",             "Taxa media",   suffix="% a.m.")
_metrica_fin(fc4, "RendaLiquida",     "Renda media",  prefix="R$ ")

st.divider()

# ── Evolucao horaria ──────────────────────────────────────────────────────────

st.subheader("Evolucao horaria")
ev    = agg["evolucao"]
horas = sorted(ev.keys())

fig_ev = go.Figure()
for s in [3, 4, 5, 2, 0, 7]:
    y = [ev.get(h, {}).get(s, 0) for h in horas]
    if sum(y) == 0:
        continue
    fig_ev.add_trace(go.Bar(
        name=_STATUS_NOMES.get(s, str(s)),
        x=horas,
        y=y,
        marker_color=_STATUS_CORES.get(s, "#aaa"),
    ))
fig_ev.update_layout(
    barmode="stack",
    height=320,
    margin=dict(t=10, b=10, l=10, r=10),
    legend=dict(orientation="h", y=-0.3),
    xaxis_title="Hora",
    yaxis_title="Leads",
)
st.plotly_chart(fig_ev, use_container_width=True)

st.divider()

# ── Top motivos e empregadores ────────────────────────────────────────────────

col_m, col_e = st.columns(2)

with col_m:
    st.subheader("Top motivos de reprovacao")
    mot = agg["top_motivos"]
    if mot:
        items = list(mot.items())[:15]
        fig_m = go.Figure(go.Bar(
            x=[v for _, v in items],
            y=[k for k, _ in items],
            orientation="h",
            marker_color="#e74c3c",
        ))
        fig_m.update_layout(
            height=440,
            margin=dict(t=10, b=10, l=10, r=10),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig_m, use_container_width=True)
    else:
        st.info("Sem dados de reprovacao.")

with col_e:
    st.subheader("Top empregadores (aprovados)")
    emps = agg["top_empregadores"]
    if emps:
        items = list(emps.items())[:15]
        fig_e = go.Figure(go.Bar(
            x=[v for _, v in items],
            y=[k for k, _ in items],
            orientation="h",
            marker_color="#2ecc71",
        ))
        fig_e.update_layout(
            height=440,
            margin=dict(t=10, b=10, l=10, r=10),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig_e, use_container_width=True)
    else:
        st.info("Sem dados de empregadores.")
