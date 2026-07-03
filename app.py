"""
Dashboard de leads SWorks — Streamlit Community Cloud.
Dados lidos do repositorio privado leads-sworks-data via GitHub API.
"""

import hashlib
import hmac
import json
import re
import statistics
import time
import bcrypt
import requests
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
from datetime import datetime, timedelta
from collections import defaultdict
from streamlit_cookies_controller import CookieController

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

.kpi-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin: 10px 0 16px; }
.kpi-card {
    background: #131210; border-radius: 10px;
    padding: 11px 14px; border: 1px solid #272420; text-align: center;
}
.kpi-label { color: #94a3b8; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; margin-bottom: 4px; }
.kpi-value { color: #FEC52E; font-size: 21px; font-weight: 700; line-height: 1.1; }
.kpi-sub   { color: #64748b; font-size: 10px; margin-top: 3px; }

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

/* Reset login-form styling so it doesn't bleed into the dashboard */
div[data-testid="stForm"]{background:transparent!important;border:none!important;
    border-radius:0!important;padding:0!important}
/* Collapse CookieController iframe — JS still runs with height:0 (no display:none) */
iframe{height:0!important;min-height:0!important;overflow:hidden!important}
</style>
""", unsafe_allow_html=True)

# ── Secrets ───────────────────────────────────────────────────────────────────

try:
    _TOKEN = st.secrets["github"]["token"]
    _REPO  = st.secrets["github"]["repo"]
except Exception:
    st.error("Secrets do GitHub não configurados. Adicione [github] token e repo em Settings > Secrets.")
    st.stop()

_HEADERS_RAW  = {"Authorization": f"Bearer {_TOKEN}", "Accept": "application/vnd.github.v3.raw", "Cache-Control": "no-cache"}
_HEADERS_JSON = {"Authorization": f"Bearer {_TOKEN}", "Cache-Control": "no-cache"}

# ── Auth ──────────────────────────────────────────────────────────────────────

_COOKIE_NAME          = "zileads_session"
_COOKIE_MAX_AGE       = 7_200   # 2h — expiração por inatividade
_COOKIE_REFRESH_AFTER = 900     # re-emite cookie a cada 15min de atividade
_login_attempts: dict = {}    # {email: {"count": int, "blocked_until": float|None}}

_SVG_Z = (
    '<svg viewBox="0 0 483 462" xmlns="http://www.w3.org/2000/svg" '
    'style="height:52px;width:auto;display:block;margin:0 auto 4px">'
    '<path d="M400.738 373.763C392.772 365.797 377.074 359.276 365.814 '
    '359.276H214.153C202.893 359.276 198.725 351.579 204.876 342.134L'
    '224.641 311.882C230.792 302.471 229.313 288.252 221.38 280.286L'
    '178.053 236.959C170.087 228.993 158.524 230.17 152.306 239.581L'
    '18.191 443.14C12.0063 452.551 16.1406 460.215 27.4009 460.215H'
    '466.753C478.014 460.215 480.703 453.694 472.736 445.728L400.738 373.729V373.763Z" fill="#FEC52E"/>'
    '<path d="M219.065 100.939C230.325 100.939 234.46 108.636 228.275 '
    '118.014L197.889 164.131C191.704 173.543 193.15 187.727 201.116 '
    '195.693L244.174 238.751C252.14 246.717 263.669 245.508 269.854 '
    '236.096L412.944 17.1424C419.095 7.73085 414.927 0 403.667 0H'
    '10.5652C-0.695032 0 -3.38405 6.52066 4.58217 14.4869L76.5807 '
    '86.4856C84.547 94.4518 100.244 100.972 111.504 100.972H219.065V100.939Z" fill="#FEC52E"/>'
    '</svg>'
)


def _session_secret() -> str:
    try:
        return st.secrets["auth"]["secret"]
    except Exception:
        raise RuntimeError("auth.secret não configurado em Streamlit Secrets.")


def _make_token(email: str) -> str:
    expires = int(time.time()) + _COOKIE_MAX_AGE
    msg = f"{email}:{expires}"
    sig = hmac.new(_session_secret().encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{msg}:{sig}"


def _verify_token(token: str) -> str | None:
    """Retorna email se token válido, None caso contrário."""
    try:
        email, expires_str, sig = token.rsplit(":", 2)
        if time.time() > int(expires_str):
            return None
        expected = hmac.new(
            _session_secret().encode(),
            f"{email}:{expires_str}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return email if hmac.compare_digest(sig, expected) else None
    except Exception:
        return None


def _find_user(email: str) -> dict | None:
    try:
        for u in st.secrets["auth"]["users"].values():
            if str(u.get("email", "")).lower() == email.strip().lower():
                return dict(u)
    except Exception:
        pass
    return None


def _check_password(password: str, hash_str: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hash_str.encode())
    except Exception:
        return False


def _login_page(cookies: CookieController) -> None:
    st.markdown("""<style>
    body,[data-testid="stAppViewContainer"]{background:#0a0908!important}
    [data-testid="stHeader"],footer,#MainMenu{display:none!important}
    [data-testid="stDeployButton"],[data-testid="stStatusWidget"]{display:none!important}
    div[data-testid="stForm"]{background:#141210!important;border:1px solid #272420!important;
        border-radius:12px!important;padding:28px 24px!important}
    </style>""", unsafe_allow_html=True)

    _, col, _ = st.columns([1, 1.1, 1])
    with col:
        _svg_inline = _SVG_Z.replace("margin:0 auto 4px", "margin:0")
        st.markdown(
            f'<div style="text-align:center;margin:56px 0 28px">'
            f'<div style="display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:4px">'
            f'{_svg_inline}'
            f'<div style="font-size:32px;font-weight:700;color:#e2e8f0;letter-spacing:-0.5px">ileads</div>'
            f'</div>'
            f'<div style="font-size:13px;color:#475569">Dashboard de Leads</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        with st.form("login_form", border=False):
            email_in = st.text_input("E-mail", placeholder="seu@zilicred.com.br")
            senha_in = st.text_input("Senha", type="password")
            entrar   = st.form_submit_button("Entrar", use_container_width=True, type="primary")

        if entrar:
            attempt = _login_attempts.get(email_in, {"count": 0, "blocked_until": None})
            bu = attempt.get("blocked_until")
            if bu and time.time() < bu:
                mins = max(1, int((bu - time.time()) / 60))
                st.error(f"Acesso bloqueado. Tente novamente em {mins} minuto(s).")
            else:
                user  = _find_user(email_in)
                pw_ok = user is not None and _check_password(senha_in, user.get("password_hash", ""))
                if pw_ok:
                    _login_attempts.pop(email_in, None)
                    cookies.set(_COOKIE_NAME, _make_token(email_in), max_age=_COOKIE_MAX_AGE)
                    st.session_state.update({
                        "logged_in":    True,
                        "user_email":   email_in,
                        "display_name": user.get("display_name", email_in),
                        "_cookie_set":  True,
                        "_cookie_checked": True,
                    })
                    st.rerun()
                else:
                    attempt["count"] = attempt.get("count", 0) + 1
                    if attempt["count"] >= 3:
                        attempt["blocked_until"] = time.time() + 3600
                    _login_attempts[email_in] = attempt
                    st.error("E-mail ou senha incorretos.")

    st.stop()


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
    "Cadastro Proposta",
    "Envia CCB Único",
    "Averbação",
]

_TEMPLATE = "plotly_dark"
_CONF     = {"displayModeBar": False, "responsive": True}
_GRID     = "rgba(255,255,255,0.06)"
_BG       = "rgba(0,0,0,0)"
_TF       = dict(size=15, color="#FEC52E")
_AF       = dict(size=13, color="#94a3b8")

_TV_N_SLIDES   = 17
_TV_INTERVAL_S = 20  # seconds per slide

_TV_CSS = """<style>
body,html{background:#0f0e0b!important}
body,html,[data-testid="stAppViewContainer"],[data-testid="stMain"],section.main{
    overflow:hidden!important;height:100vh!important;background:#0f0e0b!important}
header[data-testid="stHeader"]{display:none!important}
footer{display:none!important}
#MainMenu{display:none!important}
[data-testid="stDeployButton"],[data-testid="stStatusWidget"]{display:none!important}
section.main>.block-container{
    padding:0 1.5rem 2rem!important;max-width:100%!important;
    max-height:100vh!important;overflow:hidden!important;background:#0f0e0b!important;
    opacity:1!important}
[data-testid="column"],[data-testid="stVerticalBlock"]{background:#0f0e0b!important}
iframe{height:0!important;min-height:0!important;overflow:hidden!important}
section.main>.block-container>[data-testid="stVerticalBlock"]{margin-top:-2rem!important}
.kpi-value{font-size:43px!important}
.kpi-label{font-size:21px!important;letter-spacing:.06em}
.kpi-sub{font-size:18px!important}
.dtbl{font-size:25px!important;width:100%}
.dtbl th,.dtbl td{padding:12px 18px!important;font-size:25px!important}
.dtbl-title{display:none!important}
</style>"""

# ── GitHub API ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def listar_datas() -> list:
    url = f"https://api.github.com/repos/{_REPO}/contents/dados"
    r = requests.get(url, headers=_HEADERS_JSON, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"GitHub API retornou {r.status_code}")
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
    if r.status_code != 200:
        raise RuntimeError(f"GitHub API retornou {r.status_code}")
    return json.loads(r.text)

# ── Agregacao ─────────────────────────────────────────────────────────────────

def agregar(dias_raw: list) -> dict:
    d_status     = defaultdict(int)
    fin_n            = defaultdict(int)
    fin_total        = defaultdict(float)
    fin_min          = {}
    fin_max          = {}
    fin_med_sum      = defaultdict(float)
    fin_weighted_sum = defaultdict(float)
    fin_weight_sum   = defaultdict(float)
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
    emp_motivos   = defaultdict(lambda: defaultdict(int))
    novo_ctps     = defaultdict(int)
    emp_ap_stats_raw: dict = {}
    valores_cont     = []
    aguardando          = 0
    aguardando_valor    = 0.0
    aguardando_liberado = 0.0
    aguardando_iof      = 0.0
    assinado            = 0
    assinado_valor      = 0.0
    assinado_liberado   = 0.0
    assinado_iof        = 0.0
    projecao_tipos_agg  = defaultdict(lambda: {"count": 0, "valor": 0.0, "liberado": 0.0, "iof": 0.0})

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
                if "weighted_sum" in s:
                    fin_weighted_sum[campo] += s["weighted_sum"]
                    fin_weight_sum[campo]   += s["weight_sum"]

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
                motivos_det[_norm_label(k)] += v
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
                etapa_motivos[etapa][_norm_label(label)] += cnt

        for emp, mots in d.get("emp_motivos", {}).items():
            for label, cnt in mots.items():
                emp_motivos[emp][label] += cnt

        for k, v in d.get("novo_ctps_status", {}).items():
            novo_ctps[k] += v

        for emp, s in d.get("emp_ap_stats", {}).items():
            if emp not in emp_ap_stats_raw:
                emp_ap_stats_raw[emp] = {
                    "n_tempo": 0, "sum_tempo": 0.0,
                    "n_renda": 0, "sum_renda": 0.0,
                    "n_valor": 0, "sum_valor": 0.0,
                    "n_prazo": 0, "sum_prazo": 0.0,
                    "n_taxa":  0, "sum_taxa":  0.0,
                    "num_funcionarios": None, "faturamento": None,
                    "dividas_ativas":   None, "capital_social": None,
                }
            a = emp_ap_stats_raw[emp]
            for _c in ("tempo", "renda", "valor", "prazo", "taxa"):
                a[f"n_{_c}"]   += s.get(f"n_{_c}", 0)
                a[f"sum_{_c}"] += s.get(f"sum_{_c}", 0.0)
            for _pj in ("num_funcionarios", "faturamento", "dividas_ativas", "capital_social"):
                if a[_pj] is None and s.get(_pj) is not None:
                    a[_pj] = s[_pj]

        valores_cont.extend(d.get("valores_contratacao", []))
        aguardando          += d.get("aguardando", 0)
        aguardando_valor    += d.get("aguardando_valor", 0.0)
        aguardando_liberado += d.get("aguardando_liberado", 0.0)
        aguardando_iof      += d.get("aguardando_iof", 0.0)
        assinado            += d.get("assinado", 0)
        assinado_valor      += d.get("assinado_valor", 0.0)
        assinado_liberado   += d.get("assinado_liberado", 0.0)
        assinado_iof        += d.get("assinado_iof", 0.0)
        for _ts, _v in d.get("projecao_tipos", {}).items():
            projecao_tipos_agg[_ts]["count"]    += _v.get("count", 0)
            projecao_tipos_agg[_ts]["valor"]    += _v.get("valor", 0.0)
            projecao_tipos_agg[_ts]["liberado"] += _v.get("liberado", 0.0)
            projecao_tipos_agg[_ts]["iof"]      += _v.get("iof", 0.0)

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
        if fin_weight_sum.get(campo):
            media = fin_weighted_sum[campo] / fin_weight_sum[campo]
        else:
            media = fin_total[campo] / n
        financeiro[campo] = {
            "n":      n,
            "media":  media,
            "mediana": fin_med_sum[campo] / n,
            "total":  fin_total[campo],
            "min":    fin_min[campo],
            "max":    fin_max[campo],
        }

    def _top(dd, n):
        return dict(sorted(dd.items(), key=lambda x: -x[1])[:n])

    emp_ap_stats_final: dict = {}
    for _emp, _a in emp_ap_stats_raw.items():
        emp_ap_stats_final[_emp] = {
            "media_tempo": _a["sum_tempo"] / _a["n_tempo"] if _a["n_tempo"] else None,
            "media_renda": _a["sum_renda"] / _a["n_renda"] if _a["n_renda"] else None,
            "media_valor": _a["sum_valor"] / _a["n_valor"] if _a["n_valor"] else None,
            "media_prazo": _a["sum_prazo"] / _a["n_prazo"] if _a["n_prazo"] else None,
            "media_taxa":  _a["sum_taxa"]  / _a["n_taxa"]  if _a["n_taxa"]  else None,
            "num_funcionarios": _a["num_funcionarios"],
            "faturamento":      _a["faturamento"],
            "dividas_ativas":   _a["dividas_ativas"],
            "capital_social":   _a["capital_social"],
        }

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
        "emp_motivos":       {emp: dict(sorted(mots.items(), key=lambda x: -x[1])[:15]) for emp, mots in emp_motivos.items()},
        "emp_ap_stats":      emp_ap_stats_final,
        "valores_contratacao": valores_cont,
        "projecao_tipos": {
            ts: {
                "count":    d["count"],
                "valor":    round(d["valor"], 2),
                "liberado": round(d["liberado"], 2),
                "iof":      round(d["iof"], 2),
            }
            for ts, d in sorted(projecao_tipos_agg.items(), key=lambda x: -x[1]["valor"])
        },
        "aguardando":           aguardando,
        "aguardando_valor":     round(aguardando_valor, 2),
        "aguardando_liberado":  round(aguardando_liberado, 2),
        "aguardando_iof":       round(aguardando_iof, 2),
        "assinado":             assinado,
        "assinado_valor":       round(assinado_valor, 2),
        "assinado_liberado":    round(assinado_liberado, 2),
        "assinado_iof":         round(assinado_iof, 2),
        "pipeline_financeiro":  dias_raw[-1].get("pipeline_financeiro", {}) if dias_raw else {},
        "duplicatas_cpf":       dias_raw[-1].get("duplicatas_cpf", []) if dias_raw else [],
        "novo_ctps_status":     dict(novo_ctps),
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
        textinfo="percent",          # only % on slices (no label — cleaner)
        domain=dict(x=[0, 0.55]),   # pie in left 55%
        textfont=dict(size=11, color="#e2e8f0"),
        hovertemplate="%{label}: <b>%{value:,}</b> (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text="Distribuição por Status", font=_TF),
        legend=dict(
            font=dict(size=13, color="#94a3b8"),
            bgcolor="rgba(13,12,10,0.85)",
            bordercolor="rgba(255,255,255,0.10)", borderwidth=1,
            orientation="v",
            x=0.60, y=0.50,
            xanchor="left", yanchor="middle",
        ),
        margin=dict(t=50, b=10, l=10, r=200), height=360,
        annotations=[dict(
            text=f"<b>{_nbr(total)}</b><br>leads",
            x=0.275,                 # center of pie domain [0, 0.55]
            y=0.5,
            font=dict(size=14, color="#e2e8f0"),
            showarrow=False,
            xanchor="center",
            yanchor="middle",
        )],
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
        textfont=dict(size=14, color="#e2e8f0"),
        connector=dict(line=dict(color="rgba(255,255,255,0.2)", width=1)),
        hovertemplate="<b>%{y}</b><br>%{x:,} leads · %{percentInitial:.2%}<extra></extra>",
    ))
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text="Funil de Conversão", font=_TF),
        xaxis=dict(tickfont=_AF),
        yaxis=dict(tickfont=dict(size=13, color="#cbd5e1"), automargin=True),
        margin=dict(t=50, b=10, l=160, r=40), height=360,
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


def _sem_codigo(d: dict, max_chars: int = 50) -> dict:
    """Remove 'CODIGO — ' prefix das chaves, trunca para max_chars.
    Re-ordena por valor desc após mesclar rótulos duplicados."""
    out: dict = {}
    for k, v in d.items():
        label = k.split(" — ", 1)[1] if " — " in k else k
        if len(label) > max_chars:
            label = label[:max_chars - 1].rstrip() + "…"
        out[label] = out.get(label, 0) + v
    return dict(sorted(out.items(), key=lambda x: -x[1]))


# CNAE_RED e CBO_RED removidos do S-Works (eram redundantes com BLOCKLIST).
_MOTIVOS_DET_MERGE = {
    # códigos normalizados (fallback)
    "COMPANY_CNAE_BLOCKLIST":                                                              "CNAE da empresa está na lista de CNAEs bloqueados",
    "CNAE_RED":                                                                            "CNAE da empresa está na lista de CNAEs bloqueados",
    "CBO_BLOCKLIST":                                                                       "CBO do cliente está na lista de CBOs bloqueados",
    "CBO_RED":                                                                             "CBO do cliente está na lista de CBOs bloqueados",
    # textos detalhados vindos do campo MotivoReprovacaoDetalhado
    "CNAE da empresa está na lista de CNAEs bloqueados":                                   "CNAE da empresa está na lista de CNAEs bloqueados",
    "CNAE da empresa está na lista de CNAEs bloqueados | O semáforo do CNAE é vermelho":   "CNAE da empresa está na lista de CNAEs bloqueados",
    "O semáforo do CNAE é vermelho":                                                       "CNAE da empresa está na lista de CNAEs bloqueados",
    "CBO do cliente está na lista de CBOs bloqueados":                                     "CBO do cliente está na lista de CBOs bloqueados",
    "CBO do cliente está na lista de CBOs bloqueados | O semáforo do CBO é vermelho":      "CBO do cliente está na lista de CBOs bloqueados",
    "O semaforo do CBO é vermelho":                                                        "CBO do cliente está na lista de CBOs bloqueados",
    "Reprovação Perfil Margem":                                                            "Cadastro Proposta Reprovada",
}

_RE_BLOQUEADO_DASH = re.compile(r'^Bloqueado pelo Segurado\b')
_RE_CNPJ_NF_DASH   = re.compile(r'^CNPJ\s+[\d.\/\-]+\s+não encontrado', re.IGNORECASE)


def _nbr(v) -> str:
    return f"{v:,}".replace(",", ".")


def _norm_label(s: str) -> str:
    if _RE_BLOQUEADO_DASH.match(s):
        return "Bloqueado pelo Segurado"
    if _RE_CNPJ_NF_DASH.match(s):
        return "CNPJ não encontrado"
    return _MOTIVOS_DET_MERGE.get(s, s)


def _merge_motivos_det(d: dict) -> dict:
    out: dict = {}
    for k, v in d.items():
        label = _norm_label(k)
        out[label] = out.get(label, 0) + v
    return out


# ── Pizza UF dos leads ────────────────────────────────────────────────────────

def _fig_mapa_ufs(ufs: dict):
    if not ufs:
        return None
    pairs = sorted(ufs.items(), key=lambda x: -x[1])
    if not pairs:
        return None

    # Agrupa estados pequenos em "Outros" para manter o gráfico legível
    TOP_N = 12
    if len(pairs) > TOP_N:
        top   = pairs[:TOP_N]
        resto = sum(v for _, v in pairs[TOP_N:])
        labels = [uf for uf, _ in top] + ["Outros"]
        values = [v  for _, v  in top] + [resto]
    else:
        labels = [uf for uf, _ in pairs]
        values = [v  for _, v  in pairs]

    total = sum(values) or 1
    customdata = [f"<b>{lbl}</b>: {_nbr(val)} leads ({100*val/total:.1f}%)"
                  for lbl, val in zip(labels, values)]

    # Arco-íris: vermelho (hue=0) → violeta (hue=270); "Outros" fica cinza
    n_real = len(labels) - (1 if labels and labels[-1] == "Outros" else 0)
    _COLORS = [
        f"hsl({int(_i * 270 / max(n_real - 1, 1))}, 82%, 42%)"
        for _i in range(n_real)
    ]
    if labels and labels[-1] == "Outros":
        _COLORS.append("#64748b")

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        customdata=customdata,
        hovertemplate="%{customdata}<extra></extra>",
        texttemplate="%{label} %{percent:.0%}",
        textfont=dict(size=45, color="#f1f5f9"),
        insidetextorientation="horizontal",
        textposition="inside",
        hole=0.15,
        domain=dict(x=[0, 0.50], y=[0, 1]),
        marker=dict(colors=_COLORS, line=dict(color=_BG, width=2)),
        sort=False,
    ))
    fig.update_layout(
        template=_TEMPLATE,
        paper_bgcolor=_BG,
        margin=dict(t=10, b=10, l=10, r=10),
        height=700,
        showlegend=False,
    )

    # Legenda manual em 2 colunas à direita do gráfico
    n = len(labels)
    split = (n + 1) // 2          # col1 tem ceil(n/2) itens
    col1 = list(zip(labels[:split],  _COLORS[:split]))
    col2 = list(zip(labels[split:n], _COLORS[split:n]))
    n_rows = split

    y_top, y_bot = 0.88, 0.12
    y_step = (y_top - y_bot) / max(n_rows - 1, 1)
    bw, bh = 0.028, 0.050          # largura/altura da caixa em paper coords

    for (x_box, x_lbl), items in [
        ((0.54, 0.585), col1),
        ((0.77, 0.815), col2),
    ]:
        for i, (lbl, clr) in enumerate(items):
            y = y_top - i * y_step
            fig.add_shape(
                type="rect", xref="paper", yref="paper",
                x0=x_box, x1=x_box + bw,
                y0=y - bh / 2, y1=y + bh / 2,
                fillcolor=clr, line=dict(width=0),
            )
            fig.add_annotation(
                xref="paper", yref="paper",
                x=x_lbl, y=y,
                text=lbl,
                showarrow=False,
                font=dict(size=42, color="#cbd5e1"),
                xanchor="left", yanchor="middle",
            )

    return fig


def _fig_barras_h(data_dict: dict, titulo: str, color: str, n: int = 15, pct_base: int = 0,
                  show_abs: bool = False, show_pct: bool = True):
    items = list(data_dict.items())[:n]
    if not items:
        return None
    labels = [k for k, _ in items]
    values = [v for _, v in items]
    max_v  = max(values) if values else 1
    if pct_base > 0:
        shades = [f"rgba(96,165,250,{0.40 + 0.55*(v/max_v):.2f})" for v in values]
        if not show_pct:
            texts = [f"{_nbr(v)}" for v in values]
        elif show_abs:
            texts = [f"{_nbr(v)}  |  {100*v/pct_base:.1f}%" for v in values]
        else:
            texts  = [f"{100*v/pct_base:.1f}%" for v in values]
        tpos   = "inside"
    else:
        shades = color
        texts  = [f"{_nbr(v)}" for v in values]
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
    )
    return fig


def _fig_histograma(valores: list):
    if len(valores) < 3:
        return None
    mediana = statistics.median(valores)
    media   = statistics.mean(valores)
    fig = go.Figure(go.Histogram(
        x=valores, nbinsx=35,
        marker=dict(color="#3b82f6", opacity=0.8, line=dict(color="#0d0c0a", width=0.5)),
        hovertemplate="R$ %{x:,.0f}: %{y:,} contratos<extra></extra>",
    ))
    fig.add_vline(x=mediana, line=dict(color="#f87171", dash="dash", width=2.5))
    fig.add_vline(x=media,   line=dict(color="#fb923c", dash="dot",  width=2))
    fig.add_annotation(x=0.98, y=0.97, xref="paper", yref="paper",
        text=("Mediana: R$ " + f"{mediana:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")), font=dict(color="#f87171", size=12),
        showarrow=False, xanchor="right", yanchor="top",
        bgcolor="rgba(13,12,10,0.88)", borderpad=6,
        bordercolor="rgba(248,113,113,0.35)", borderwidth=1)
    fig.add_annotation(x=0.98, y=0.84, xref="paper", yref="paper",
        text=("Média: R$ " + f"{media:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")), font=dict(color="#fb923c", size=12),
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
        gl    = (f"dos {_nbr(n_antes)} reprov. antes do clique"
                 if is_antes else f"dos {_nbr(n_corte)} reprov. após clique")
        colors.append(f"{gc}{shade:.2f})")
        texts.append(f"{_nbr(v)} ({pct:.1f}%)")
        hovers.append(f"<b>{name}</b><br>{_nbr(v)} leads · {pct:.2f}% {gl}")
    n_dep = len(depois_sorted)
    shapes = [
        dict(type="line", x0=0, x1=1, xref="paper", y0=n_dep-0.5, y1=n_dep-0.5, yref="y",
             line=dict(color="rgba(255,255,255,0.10)", width=1, dash="dot")),
        dict(type="line", x0=0, x1=1, xref="paper", y0=n_dep+0.5, y1=n_dep+0.5, yref="y",
             line=dict(color="rgba(255,255,255,0.10)", width=1, dash="dot")),
    ]
    bar_h = max(360, len(all_items) * 34 + 90)
    fig = go.Figure(go.Bar(
        x=x_vals, y=y_labs, orientation="h",
        marker=dict(color=colors, line=dict(color="#0d0c0a", width=0.5)),
        text=texts, textposition="inside", insidetextanchor="end",
        textfont=dict(size=13, color="rgba(255,255,255,0.85)"),
        hovertemplate="%{customdata}<extra></extra>", customdata=hovers,
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="markers",
        marker=dict(color="rgba(251,146,60,0.85)", symbol="square", size=14),
        name=f"Antes do clique ({_nbr(n_antes)})",
    ))
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="markers",
        marker=dict(color="rgba(96,165,250,0.85)", symbol="square", size=14),
        name=f"Depois do clique ({_nbr(n_corte)})",
    ))
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text="Reprovados por Etapa — Antes vs. Depois do Clique", font=_TF),
        xaxis=dict(title="Ocorrências", tickfont=_AF, showgrid=True, gridcolor=_GRID, zeroline=False),
        yaxis=dict(tickfont=dict(size=13, color="#cbd5e1"), automargin=True, zeroline=False),
        uniformtext_minsize=11, uniformtext_mode="hide",
        shapes=shapes,
        legend=dict(
            orientation="h",
            x=0.5, y=-0.18,
            xanchor="center", yanchor="top",
            font=dict(size=13, color="#94a3b8"),
            bgcolor="rgba(13,12,10,0.85)",
            bordercolor="rgba(255,255,255,0.10)", borderwidth=1,
        ),
        margin=dict(t=50, b=90, l=20, r=40), height=bar_h,
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
        rej_colors.append(f"rgba(96,165,250,{shade:.2f})")
    rej_hover = [
        f"<b>{r['etapa']}</b><br>Chegaram: {_nbr(r['chegaram'])}<br>"
        f"Reprovados aqui: {_nbr(r['rejeitados'])} ({r['pct']:.1f}%)<br>"
        f"Avançaram: {_nbr(r['restante_apos'])}"
        for r in rows_r
    ]
    bar_h = max(360, len(rows) * 52 + 90)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[r["rejeitados"] for r in rows_r], y=y_labels, orientation="h",
        name="Reprovados",
        marker=dict(color=rej_colors, line=dict(color="#0d0c0a", width=0.5)),
        text=[f"{_nbr(r['rejeitados'])} ({r['pct']:.1f}%)" for r in rows_r],
        textposition="inside", insidetextanchor="middle",
        textfont=dict(size=13, color="rgba(255,255,255,0.90)"),
        hovertemplate="%{customdata}<extra></extra>", customdata=rej_hover,
    ))
    fig.add_trace(go.Bar(
        x=[r["restante_apos"] for r in rows_r], y=y_labels, orientation="h",
        name="Avançaram",
        marker=dict(color="rgba(255,255,255,0.07)", line=dict(color="#0d0c0a", width=0.5)),
        text=[f"{_nbr(r['restante_apos'])}" if r["restante_apos"] > 0 else "" for r in rows_r],
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
        text=[f"{_nbr(v)}<br>{p:.1f}%" for v, p in zip(values, pcts)],
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
                f'<td class="r">{_nbr(cnt)}</td>'
                f'<td class="r" style="color:#94a3b8">{pct}</td>'
                f'</tr>'
            )
        else:
            rows_html.append(
                f'<tr class="{rc}">'
                f'<td class="c" style="color:#64748b;width:28px">{i+1}</td>'
                f'<td class="wrap">{label}</td>'
                f'<td class="r">{_nbr(cnt)}</td>'
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


def _html_emp_rep_expandable(emp_rep: dict, emp_mot: dict, n_rep: int, n: int = 15) -> str:
    """Tabela de empregadores reprovados com <details>/<summary> para motivos (sem JS, sem iframe)."""
    if not emp_rep:
        return ""
    _items = list(emp_rep.items())[:n]
    rows = []
    for i, (emp, cnt) in enumerate(_items):
        pct  = f"{100*cnt/n_rep:.1f}%" if n_rep else "—"
        mots = emp_mot.get(emp, {})
        rc   = "g0" if i % 2 == 0 else "g1"
        if mots:
            total_emp = sum(mots.values())
            mrows = "".join(
                f'<tr>'
                f'<td style="font-size:0.78em;color:#94a3b8;padding:2px 8px 2px 0;word-break:break-word">{lbl}</td>'
                f'<td style="font-size:0.78em;color:#e2e8f0;font-weight:600;text-align:right;white-space:nowrap;padding:2px 0">{v/total_emp*100:.1f}%</td>'
                f'<td style="font-size:0.78em;color:#64748b;text-align:right;padding:2px 0 2px 10px">{v}</td>'
                f'</tr>'
                for lbl, v in sorted(mots.items(), key=lambda x: -x[1])
            )
            name_cell = (
                f'<details style="cursor:pointer">'
                f'<summary style="list-style:none;display:flex;align-items:center;gap:6px">'
                f'<span style="font-size:9px;color:#64748b">▶</span>{emp}'
                f'</summary>'
                f'<div style="margin:6px 0 4px 14px">'
                f'<table style="width:100%;border-collapse:collapse">'
                f'<thead><tr>'
                f'<th style="font-size:0.75em;color:#475569;font-weight:normal;text-align:left;padding-bottom:3px">Motivo</th>'
                f'<th style="font-size:0.75em;color:#475569;font-weight:normal;text-align:right;padding-bottom:3px">%</th>'
                f'<th style="font-size:0.75em;color:#475569;font-weight:normal;text-align:right;padding-bottom:3px;padding-left:10px">n</th>'
                f'</tr></thead>'
                f'<tbody>{mrows}</tbody>'
                f'</table></div>'
                f'</details>'
            )
        else:
            name_cell = emp
        rows.append(
            f'<tr class="{rc}">'
            f'<td class="c" style="color:#64748b;width:28px">{i+1}</td>'
            f'<td class="wrap">{name_cell}</td>'
            f'<td class="r">{_nbr(cnt)}</td>'
            f'<td class="r" style="color:#94a3b8">{pct}</td>'
            f'</tr>'
        )
    thead = '<thead><tr><th class="c">#</th><th>Razão Social</th><th class="r">Leads</th><th class="r">%</th></tr></thead>'
    return (
        '<div class="dtbl-wrap"><table class="dtbl">'
        + thead
        + '<tbody>' + "".join(rows) + '</tbody>'
        + '</table></div>'
    )


def _html_emp_ap_expandable(emp_ap: dict, emp_stats: dict, n_ap: int, n: int = 15) -> str:
    """Tabela de empregadores aprovados com <details>/<summary> para stats financeiras e PJ."""
    if not emp_ap:
        return ""

    def _brl(x):
        if x is None:
            return "—"
        s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {s}"

    def _num(x):
        return f"{x:,.0f}".replace(",", ".") if x is not None else "—"

    _items = list(emp_ap.items())[:n]
    rows = []
    for i, (emp, cnt) in enumerate(_items):
        pct  = f"{100*cnt/n_ap:.1f}%" if n_ap else "—"
        rc   = "g0" if i % 2 == 0 else "g1"
        st   = emp_stats.get(emp, {})

        _CELL_L = "font-size:0.78em;color:#94a3b8;padding:2px 8px 2px 0;white-space:nowrap"
        _CELL_R = "font-size:0.78em;color:#e2e8f0;font-weight:600;text-align:right;white-space:nowrap;padding:2px 0"
        _HDR    = "font-size:0.72em;color:#475569;font-weight:600;letter-spacing:.04em;text-transform:uppercase;padding:5px 0 2px"

        def _row(label, val):
            if val == "—":
                return ""
            return (
                f'<tr>'
                f'<td style="{_CELL_L}">{label}</td>'
                f'<td style="{_CELL_R}">{val}</td>'
                f'</tr>'
            )

        def _hdr_row(title):
            return f'<tr><td colspan="2" style="{_HDR}">{title}</td></tr>'

        fin_rows = (
            _hdr_row("Médias dos aprovados")
            + _row("Tempo de Emprego", f"{st['media_tempo']:.1f} meses" if st.get("media_tempo") else "—")
            + _row("Renda Líquida",    _brl(st.get("media_renda")))
            + _row("Valor Contratado", _brl(st.get("media_valor")))
            + _row("Prazo",            f"{st['media_prazo']:.0f} meses" if st.get("media_prazo") else "—")
            + _row("Taxa Mensal",      f"{st['media_taxa']:.2f}%" if st.get("media_taxa") else "—")
        )
        pj_rows = (
            _hdr_row("Dados da empresa")
            + _row("Nº Funcionários", _num(st.get("num_funcionarios")))
            + _row("Faturamento",     _brl(st.get("faturamento")))
            + _row("Dívidas Ativas",  _brl(st.get("dividas_ativas")))
            + _row("Capital Social",  _brl(st.get("capital_social")))
        )

        has_detail = st and any(
            st.get(k) is not None
            for k in ("media_tempo","media_renda","media_valor","media_prazo","media_taxa",
                       "num_funcionarios","faturamento","dividas_ativas","capital_social")
        )

        if has_detail:
            name_cell = (
                f'<details style="cursor:pointer">'
                f'<summary style="list-style:none;display:flex;align-items:center;gap:6px">'
                f'<span style="font-size:9px;color:#64748b">&#9654;</span>{emp}'
                f'</summary>'
                f'<div style="margin:6px 0 4px 14px">'
                f'<table style="width:100%;border-collapse:collapse">'
                f'<tbody>{fin_rows}{pj_rows}</tbody>'
                f'</table></div>'
                f'</details>'
            )
        else:
            name_cell = emp

        rows.append(
            f'<tr class="{rc}">'
            f'<td class="c" style="color:#64748b;width:28px">{i+1}</td>'
            f'<td class="wrap">{name_cell}</td>'
            f'<td class="r">{_nbr(cnt)}</td>'
            f'<td class="r" style="color:#94a3b8">{pct}</td>'
            f'</tr>'
        )

    thead = '<thead><tr><th class="c">#</th><th>Razão Social</th><th class="r">Leads</th><th class="r">%</th></tr></thead>'
    return (
        '<div class="dtbl-wrap"><table class="dtbl">'
        + thead
        + '<tbody>' + "".join(rows) + '</tbody>'
        + '</table></div>'
    )


def _html_diagrama(etapas: dict, n_rep: int) -> str:
    """HTML do Workflow 37 — linha única horizontal + detalhamento Motor de Crédito."""
    if not etapas or not n_rep:
        return ""

    _C = "#374151"  # cor dos conectores e setas

    _BOX_W = "min-width:52px;max-width:72px;line-height:1.35;white-space:normal;"
    _S_OK  = ("background:#1a3560;border:1px solid rgba(96,165,250,0.25);"
               f"color:#93c5fd;border-radius:8px;padding:6px 9px;"
               f"font-size:10.5px;font-weight:500;text-align:center;{_BOX_W}")
    _S_REJ = ("background:#431407;border:1.5px solid #f97316;"
               f"color:#fed7aa;border-radius:8px;padding:6px 9px;"
               f"font-size:10.5px;font-weight:500;text-align:center;{_BOX_W}")
    _ARR_R = f'<div style="padding:9px 3px 0;color:{_C};font-size:12px;flex-shrink:0;">&#9654;</div>'
    _ARR_L = f'<div style="padding:9px 3px 0;color:{_C};font-size:12px;flex-shrink:0;">&#9664;</div>'

    def _unit(name, keys, small=False):
        count = sum(etapas.get(e, 0) for e in keys)
        pct   = 100 * count / n_rep if n_rep and count else 0
        sw    = ("min-width:44px;max-width:62px;line-height:1.3;white-space:normal;"
                 if small else _BOX_W)
        fsz   = "9.5px" if small else "10.5px"
        ok_s  = (f"background:#1a3560;border:1px solid rgba(96,165,250,0.25);"
                  f"color:#93c5fd;border-radius:8px;padding:5px 8px;"
                  f"font-size:{fsz};font-weight:500;text-align:center;{sw}")
        rej_s = (f"background:#431407;border:1.5px solid #f97316;"
                  f"color:#fed7aa;border-radius:8px;padding:5px 8px;"
                  f"font-size:{fsz};font-weight:500;text-align:center;{sw}")
        s   = rej_s if count else ok_s
        sub = "".join(
            f'<div style="font-size:8px;color:#94a3b8;overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap;max-width:68px;">'
            f'&#8226; {e}: {_nbr(etapas[e])}</div>'
            for e in keys if etapas.get(e, 0)
        )
        below = (
            f'<div style="font-size:9px;color:#f97316;margin-top:4px;'
            f'font-weight:700;white-space:nowrap;text-align:center;">'
            f'&#11015; {_nbr(count)}&nbsp;({pct:.1f}%)</div>{sub}'
        ) if count else ""
        return (
            f'<div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0;">'
            f'<div style="{s}">{name}</div>{below}</div>'
        )

    def _circle(label, color, border):
        return (
            f'<div style="display:flex;flex-direction:column;align-items:center;'
            f'flex-shrink:0;padding-top:7px;">'
            f'<div style="width:22px;height:22px;border-radius:50%;'
            f'background:{color};border:2px solid {border};"></div>'
            f'<div style="font-size:9px;color:#64748b;margin-top:4px;">{label}</div>'
            f'</div>'
        )

    # Motor de Crédito: caixa compacta no snake + detalhamento abaixo
    _MC_ITEMS = [
        ("Valid. Internas",  ["Validações Internas"]),
        ("RF PF",            ["Receita Federal PF"]),
        ("Dataprev",         ["Consulta Dataprev"]),
        ("RF PJ",            ["Receita Federal PJ"]),
        ("PH3A PJ",          ["Análise PH3A (PJ)"]),
        ("SCR",              ["SCR"]),
        ("PH3A PF",          ["Análise PH3A (PF)"]),
    ]
    mc_total = sum(sum(etapas.get(e, 0) for e in keys) for _, keys in _MC_ITEMS)
    mc_pct   = 100 * mc_total / n_rep if n_rep and mc_total else 0
    mc_sw    = "min-width:60px;max-width:90px;line-height:1.35;white-space:normal;"
    mc_ok_s  = (f"background:#1a3560;border:1px solid rgba(99,102,241,0.40);"
                 f"color:#a5b4fc;border-radius:8px;padding:6px 10px;"
                 f"font-size:10.5px;font-weight:700;text-align:center;{mc_sw}")
    mc_rej_s = (f"background:#431407;border:1.5px solid rgba(99,102,241,0.60);"
                 f"color:#c4b5fd;border-radius:8px;padding:6px 10px;"
                 f"font-size:10.5px;font-weight:700;text-align:center;{mc_sw}")
    mc_s      = mc_rej_s if mc_total else mc_ok_s
    mc_below  = (
        f'<div style="font-size:9px;color:#f97316;margin-top:4px;'
        f'font-weight:700;white-space:nowrap;text-align:center;">'
        f'&#11015; {_nbr(mc_total)}&nbsp;({mc_pct:.1f}%)</div>'
    ) if mc_total else ""
    mc_compact = (
        f'<div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0;">'
        f'<div style="{mc_s}">Motor de<br>Cr&#233;dito</div>{mc_below}</div>'
    )

    # Linha única (L→R): todos os steps em sequência de fluxo
    flow_content = (
        _circle("In&#237;cio", "#22c55e", "#16a34a") + _ARR_R
        + _unit("Inicializa Dados",             ["Já Reprovado (reentrada)"]) + _ARR_R
        + mc_compact + _ARR_R
        + _unit("C&#225;lculo Proposta",        ["Cálculo de Proposta"]) + _ARR_R
        + _unit("Proposta Leil&#227;o",         []) + _ARR_R
        + _unit("Cadastro Proposta",            ["Cadastro Proposta"]) + _ARR_R
        + _unit("Formaliza&#231;&#227;o",       []) + _ARR_R
        + _unit("Obter Endosso",                []) + _ARR_R
        + _unit("Envio Inf. Dtprev",            []) + _ARR_R
        + _unit("Antifraude",                   []) + _ARR_R
        + _unit("Averba&#231;&#227;o Dtprev",   ["Averbação"]) + _ARR_R
        + _unit("Envia CCB &#218;nico",         ["Envia CCB Único"]) + _ARR_R
        + _unit("Obter CCB",                    []) + _ARR_R
        + _unit("Atualiz. Dados",               []) + _ARR_R
        + _unit("Pagamento Pix",                []) + _ARR_R
        + _unit("Tesouraria",                   []) + _ARR_R
        + _unit("Portal Cr&#233;dito",          []) + _ARR_R
        + _unit("Contratar Seguro",             []) + _ARR_R
        + _unit("Envia Comunica&#231;&#227;o",  []) + _ARR_R
        + _circle("Aprovado", "#22c55e", "#16a34a")
    )

    snake_html = (
        f'<div style="display:flex;align-items:flex-start;flex-wrap:nowrap;padding:6px 0;">'
        + flow_content
        + '</div>'
    )

    # Detalhamento do Motor de Crédito (2ª linha abaixo do fluxo)
    mc_detail = ""
    for i, (name, keys) in enumerate(_MC_ITEMS):
        if i > 0:
            mc_detail += _ARR_R
        mc_detail += _unit(name, keys, small=True)

    mc_section = (
        f'<div style="margin-top:14px;border:1px solid rgba(99,102,241,0.35);'
        f'border-radius:8px;padding:8px 12px;background:rgba(99,102,241,0.06);">'
        f'<div style="font-size:9px;color:#a5b4fc;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;">'
        f'Motor de Cr&#233;dito &#8212; Detalhamento</div>'
        f'<div style="display:flex;align-items:flex-start;flex-wrap:nowrap;">'
        + mc_detail
        + '</div></div>'
    )

    title_html = (
        '<div style="font-size:10px;color:#475569;text-transform:uppercase;'
        'letter-spacing:0.6px;margin-bottom:12px;font-weight:600;">'
        'Fluxo do Workflow 37 &#8212; Consignado Privado</div>'
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
        '<div style="width:24px;height:12px;border-radius:3px;'
        'border:1px solid rgba(99,102,241,0.40);'
        'background:rgba(99,102,241,0.06);flex-shrink:0;"></div>'
        'Motor de Cr&#233;dito</div>'
        '</div>'
    )

    wrapper = (
        '<div style="overflow-x:auto;padding:4px 0;">'
        '<div style="display:inline-block;min-width:max-content;">'
        + snake_html + mc_section
        + '</div></div>'
    )

    return title_html + wrapper + legend


def _html_tabela_etapa_motivo(etapa_motivos: dict, etapas: dict, n_rep: int) -> str:
    if not etapa_motivos or not etapas or n_rep == 0:
        return ""
    _order_idx = {e: i for i, e in enumerate(_ETAPA_WORKFLOW_ORDER)}
    etapas_sorted = sorted(etapas.keys(), key=lambda e: (_order_idx.get(e, 999), -etapas.get(e, 0)))

    thead = (
        "<thead><tr>"
        "<th>Etapa</th><th>Motivo de Reprovação</th>"
        '<th class="r">Leads</th><th class="r">%</th>'
        "</tr></thead>"
    )

    tbody_rows = []
    shade_idx  = -1

    for etapa in etapas_sorted:
        if etapa not in etapa_motivos and etapas.get(etapa, 0) == 0:
            continue

        motivos_etapa = sorted(etapa_motivos.get(etapa, {}).items(), key=lambda x: -x[1])
        if not motivos_etapa:
            motivos_etapa = [("—", etapas.get(etapa, 0))]

        shade_idx += 1
        rc = "g0" if shade_idx % 2 == 0 else "g1"
        for i, (motivo, cnt) in enumerate(motivos_etapa):
            pct = f"{100*cnt/n_rep:.1f}%" if n_rep else "—"
            tbody_rows.append(
                f'<tr class="{rc}">'
                f"<td>{etapa if i == 0 else ''}</td>"
                f'<td class="wrap">{motivo}</td>'
                f'<td class="r">{_nbr(cnt)}</td>'
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
    _C_ETG = "#60a5fa"
    _C_Z   = "#64748b"
    trs = []
    for r in rows:
        cor     = _C_ETG if r["rejeitados"] else _C_Z
        pct_str = f"{r['pct']:.1f}%" if r["rejeitados"] else "—"
        trs.append(
            f'<tr>'
            f'<td style="color:{cor};font-weight:600">{r["etapa"]}</td>'
            f'<td style="text-align:right">{_nbr(r["chegaram"])}</td>'
            f'<td style="text-align:right">{_nbr(r["rejeitados"])}</td>'
            f'<td style="text-align:right;color:{cor}">{pct_str}</td>'
            f'<td style="text-align:right;color:#64748b">{_nbr(r["restante_apos"])}</td>'
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
    _brl = lambda x: ("R$ " + f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    campos = [
        ("ValorContratacao",  "Valor Contratado",    _brl),
        ("RendaLiquida",      "Renda Líquida",       _brl),
        ("Prazo",             "Prazo (meses)",        lambda x: f"{x:.0f}"),
        ("Taxa",              "Taxa Mensal (%)",      lambda x: f"{x:.2f}"),
        ("TempoEmpregoMeses", "Tempo de Emprego (meses)", lambda x: f"{x:.2f}"),
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
            f'<td class="r">{_nbr(v["n"])}</td>'
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


def _html_tabela_pipeline(fin: dict) -> str:
    _brl = lambda x: ("R$ " + f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    campos = [
        ("ValorContratacao",  "Valor Contratado",         _brl),
        ("RendaLiquida",      "Renda Líquida",            _brl),
        ("Prazo",             "Prazo (meses)",             lambda x: f"{x:.0f}"),
        ("Taxa",              "Taxa Mensal (%)",           lambda x: f"{x:.2f}"),
        ("TempoEmpregoMeses", "Tempo de Emprego (meses)", lambda x: f"{x:.2f}"),
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
            f'<td class="r">{_nbr(v["n"])}</td>'
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
        '<div class="dtbl-title">Estatísticas Financeiras — Aguardando Desembolso</div>'
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
    """Barra de progresso dourada + dots (position:fixed). Setas ‹ › ficam na barra de controles do topo."""
    dots = "".join(
        f'<div style="width:8px;height:8px;border-radius:50%;background:'
        f'{"#FEC52E" if i == slide else "#2a2820"};flex-shrink:0"></div>'
        for i in range(_TV_N_SLIDES)
    )
    _ap = f"tvp{slide}"
    st.markdown(f"""
    <style>
      @keyframes {_ap}{{from{{width:0%}}to{{width:100%}}}}
      body,html{{background:#0f0e0b!important}}
    </style>
    <div style="position:fixed;bottom:0;left:0;right:0;height:3px;background:#1a1814;z-index:9999">
      <div style="height:100%;background:#FEC52E;
           animation:{_ap} {_TV_INTERVAL_S}s linear forwards"></div>
    </div>
    <div style="position:fixed;bottom:10px;left:50%;transform:translateX(-50%);
         display:flex;gap:6px;align-items:center;z-index:9999">
      {dots}
    </div>
    """, unsafe_allow_html=True)


def _tv_h(titulo: str, periodo: str = "") -> None:
    sub = f'<span style="color:#475569;font-size:42px;margin-left:12px">{periodo}</span>' if periodo else ""
    st.markdown(
        f'<div style="color:#FEC52E;font-size:42px;font-weight:700;'
        f'border-bottom:1px solid #272420;padding-bottom:8px;margin-bottom:14px">'
        f'{titulo}{sub}</div>',
        unsafe_allow_html=True,
    )


def _render_tv_slide(slide: int, agg: dict, funil: dict, fin: dict,
                     n_dias: int, dias_raw: list, datas_sel: list, periodo: str):
    # _TV_CSS is emitted once by the caller before invoking this function.
    n_rep = funil.get("reprovados", 0)
    n_ap  = funil.get("aprovados", 0)

    # TV font constants — 28px so every label reads comfortably from 3 metres
    _TV_TF   = dict(size=28, color="#FEC52E")
    _TV_AF   = dict(size=28, color="#94a3b8")
    _TV_TXT  = dict(size=28, color="rgba(255,255,255,0.92)")
    _TV_YTXT = dict(size=28, color="#cbd5e1")

    taxa     = f"{funil['taxa_aprovacao']:.1f}%" if funil.get("terminais") else "—"
    vol      = fin.get("ValorContratacao", {})
    vol_s    = ("R$ " + f"{vol['total']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if vol.get("total") else "—"
    _pt_tv        = agg.get("projecao_tipos", {})
    # BT live: independente do período — data de referência baseada no horário BRT atual
    _now_brt_tv  = datetime.utcnow() - timedelta(hours=3)
    _pix_ab_tv   = _now_brt_tv.weekday() < 5 and (7, 0) <= (_now_brt_tv.hour, _now_brt_tv.minute) <= (18, 30)
    _data_ref_tv = _now_brt_tv.date()
    if not _pix_ab_tv:
        _data_ref_tv += timedelta(days=1)
        while _data_ref_tv.weekday() >= 5:
            _data_ref_tv += timedelta(days=1)
    _ref_str_tv   = _data_ref_tv.strftime("%Y%m%d")
    _ref_label_tv = _data_ref_tv.strftime("%d/%m")
    _ultimo_tv    = carregar_dia(max(datas)) if datas else {}
    _bt_live_tv   = _ultimo_tv.get("bt_pix_days", {}).get(_ref_str_tv, {})
    _proj_count   = sum(d["count"]    for ts, d in _pt_tv.items() if ts != "BLOQUEIO_TEMPORARIO") + _bt_live_tv.get("count", 0)
    _proj_count_s = f"{_proj_count:,}".replace(",", ".")
    _proj_valor   = sum(d["valor"]    for ts, d in _pt_tv.items() if ts != "BLOQUEIO_TEMPORARIO") + _bt_live_tv.get("valor", 0.0)
    _proj_lib     = sum(d["liberado"] for ts, d in _pt_tv.items() if ts != "BLOQUEIO_TEMPORARIO") + _bt_live_tv.get("liberado", 0.0)
    _proj_iof_tv  = sum(d["iof"]      for ts, d in _pt_tv.items() if ts != "BLOQUEIO_TEMPORARIO") + _bt_live_tv.get("iof", 0.0)
    if _proj_valor:
        _proj_val_fmt_tv = ("R$ " + f"{_proj_valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        _proj_lib_fmt_tv = ("R$ " + f"{_proj_lib:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        _proj_iof_fmt_tv = ("R$ " + f"{_proj_iof_tv:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        _proj_sub = (
            f"<span style='color:#64748b;font-size:0.82em'>"
            f"Lib. {_proj_lib_fmt_tv} · IOF {_proj_iof_fmt_tv}"
            "</span>"
        )
    else:
        _proj_val_fmt_tv = "—"
        _proj_sub = ""
    _prazo_d   = fin.get("Prazo", {})
    _taxa_d    = fin.get("Taxa", {})
    _parcela_d = fin.get("ValorParcela", {})
    prazo_s   = f"{_prazo_d['media']:.0f} meses"  if _prazo_d.get("media") else "—"
    ticket_s  = ("R$ " + f"{vol['media']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if vol.get("media") else "—"
    parcela_s = ("R$ " + f"{_parcela_d['media']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if _parcela_d.get("media") else "—"
    taxa_s    = f"{_taxa_d['media']:.2f}".replace(".", ",") + "% a.m." if _taxa_d.get("media") else "—"
    _total_fmt = _nbr(funil["total"])
    _aprov_fmt = _nbr(funil["aprovados"])
    _term_fmt  = _nbr(funil["terminais"])
    _repro_fmt = _nbr(funil["reprovados"])
    _ag_fmt    = _nbr(_proj_count)
    _ncs_tv       = agg.get("novo_ctps_status", {})
    _ctps_antes_tv   = _ncs_tv.get("ctps_antes", 0)
    _ctps_apos_tv    = _ncs_tv.get("ctps_apos", 0)
    _ctps_outros_tv  = _ncs_tv.get("ctps_outros_status", 0)
    _ctps_bot_tv     = _ctps_apos_tv + _ctps_outros_tv
    _kpi_html = f"""
    <div class="kpi-row" style="grid-template-columns:repeat(4,1fr)">
      <div class="kpi-card"><div class="kpi-label">Total de leads</div>
        <div class="kpi-value">{_total_fmt}</div><div class="kpi-sub">{periodo}</div></div>
      <div class="kpi-card"><div class="kpi-label">Aprovados</div>
        <div class="kpi-value">{_aprov_fmt}</div><div class="kpi-sub">taxa: {taxa}</div></div>
      <div class="kpi-card"><div class="kpi-label">Reprovados</div>
        <div class="kpi-value">{_repro_fmt}</div>
        <div class="kpi-sub">{funil['taxa_reprovacao']:.1f}% dos finalizados</div></div>
      <div class="kpi-card"><div class="kpi-label">Volume aprovado</div>
        <div class="kpi-value">{vol_s}</div><div class="kpi-sub">valor contratado</div></div>
    </div>
    <div class="kpi-row" style="grid-template-columns:repeat(4,1fr)">
      <div class="kpi-card"><div class="kpi-label">Ticket médio do empréstimo</div>
        <div class="kpi-value">{ticket_s}</div><div class="kpi-sub">valor contratado</div></div>
      <div class="kpi-card"><div class="kpi-label">Ticket médio da parcela</div>
        <div class="kpi-value">{parcela_s}</div><div class="kpi-sub">média pond. pelo prazo</div></div>
      <div class="kpi-card"><div class="kpi-label">Taxa média</div>
        <div class="kpi-value">{taxa_s}</div><div class="kpi-sub">contratos aprovados</div></div>
      <div class="kpi-card"><div class="kpi-label">Prazo médio</div>
        <div class="kpi-value">{prazo_s}</div><div class="kpi-sub">contratos aprovados</div></div>
    </div>
    <div class="kpi-row" style="grid-template-columns:repeat(4,1fr)">
      <div class="kpi-card"><div class="kpi-label">Projeção de Leads a Desembolsar</div>
        <div class="kpi-value">{_ag_fmt}</div><div class="kpi-sub">Pix {_ref_label_tv}</div></div>
      <div class="kpi-card"><div class="kpi-label">Projeção de Desembolso</div>
        <div class="kpi-value" style="color:#FEC52E">{_proj_val_fmt_tv}</div><div class="kpi-sub">Pix {_ref_label_tv} · {_proj_sub}</div></div>
      <div class="kpi-card"><div class="kpi-label">CTPS — Aguardando clique</div>
        <div class="kpi-value">{_nbr(_ctps_antes_tv)}</div><div class="kpi-sub">Novos sem DataHoraInicio</div></div>
      <div class="kpi-card"><div class="kpi-label">CTPS — Bot WhatsApp iniciado</div>
        <div class="kpi-value">{_nbr(_ctps_bot_tv)}</div><div class="kpi-sub">{_nbr(_ctps_outros_tv)} em outros status</div></div>
    </div>
    """

    if slide == 0:
        _tv_h("KPIs", periodo)
        st.markdown(_kpi_html, unsafe_allow_html=True)

    elif slide == 1:
        _tv_h("Distribuição por Status", periodo)
        fig = _fig_donut(funil.get("_d_status", {}))
        if fig:
            fig.update_traces(textfont=dict(size=27))
            fig.update_annotations(font_size=30)
            fig.update_layout(
                height=560,
                legend=dict(font=dict(size=30, color="#94a3b8")),
            )
            st.plotly_chart(fig, use_container_width=True, config=_CONF)

    elif slide == 2:
        _tv_h("Funil de Conversão", periodo)
        fig = _fig_funil_rico(funil)
        if fig:
            fig.update_traces(
                textfont=dict(size=32, color="#e2e8f0"),
                texttemplate="%{value:,}  %{percentInitial:.1%}",
            )
            fig.update_layout(
                height=560,
                title=dict(text=""),
                xaxis=dict(tickfont=_TV_AF),
                yaxis=dict(tickfont=_TV_YTXT, automargin=True),
                margin=dict(t=10, b=20, l=250, r=40),
            )
            st.plotly_chart(fig, use_container_width=True, config=_CONF)

    elif slide == 3:
        _tv_h("Estatísticas Financeiras dos Aprovados", periodo)
        html = _html_tabela_financeira(fin)
        if html:
            st.markdown(html, unsafe_allow_html=True)
        else:
            st.info("Sem dados financeiros.")

    elif slide == 4:
        _tv_h("Distribuição do Valor Contratado — Aprovados", periodo)
        fig = _fig_histograma(agg.get("valores_contratacao", []))
        if fig:
            fig.update_annotations(font_size=25)
            fig.update_layout(
                height=680,
                title=dict(text="", font=_TV_TF),
                xaxis=dict(title=dict(text="Valor (R$)", font=_TV_AF),
                           tickformat=",.0f", tickfont=_TV_AF),
                yaxis=dict(title=dict(text="Contratos", font=_TV_AF), tickfont=_TV_AF),
                margin=dict(t=10, b=40, l=10, r=10),
            )
            st.plotly_chart(fig, use_container_width=True, config=_CONF)
        else:
            st.info("Sem dados de distribuição.")

    elif slide == 5:
        _tv_h("Etapas de Reprovação — Visão geral", periodo)
        etapas_d = agg.get("etapas", {})
        if etapas_d and n_rep > 0:
            _order_idx_tv = {e: i for i, e in enumerate(_ETAPA_WORKFLOW_ORDER)}
            _ordered_tv = sorted(
                [(e, etapas_d.get(e, 0)) for e in etapas_d if etapas_d.get(e, 0) > 0],
                key=lambda x: _order_idx_tv.get(x[0], 999),
            )
            _max_v_tv = max(v for _, v in _ordered_tv) if _ordered_tv else 1
            _y_tv  = [e for e, _ in reversed(_ordered_tv)]
            _x_tv  = [v for _, v in reversed(_ordered_tv)]
            _ps_tv = [f"{100*v/n_rep:.1f}%" for v in reversed([v for _, v in _ordered_tv])]
            _sh_tv = [f"rgba(96,165,250,{0.40 + 0.55*(v/_max_v_tv):.2f})" for v in _x_tv]
            fig_d = go.Figure(go.Bar(
                x=_x_tv, y=_y_tv, orientation="h",
                marker=dict(color=_sh_tv, line=dict(color="#0d0c0a", width=0.5)),
                text=[f"{_nbr(v)} ({p})" for v, p in zip(_x_tv, _ps_tv)],
                textposition="auto",
                insidetextanchor="end",
                cliponaxis=False,
                textfont=dict(size=13, color="#cbd5e1"),
                hovertemplate="%{y}: <b>%{x:,}</b><extra></extra>",
            ))
            fig_d.update_layout(
                template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
                title=dict(text=""),
                xaxis=dict(title="Ocorrências", tickfont=_TV_AF, showgrid=True, gridcolor=_GRID, zeroline=False),
                yaxis=dict(tickfont=_TV_YTXT, automargin=True, zeroline=False),
                margin=dict(t=10, b=30, l=20, r=160), height=580,
            )
            st.plotly_chart(fig_d, use_container_width=True, config=_CONF)
        else:
            st.info("Sem dados de etapas.")

    elif slide == 6:
        _tv_h("Etapas de Reprovação — Visão de Funil", periodo)
        etapas_d = agg.get("etapas", {})
        if etapas_d and n_rep > 0:
            result_f = _fig_funil_etapa(etapas_d, n_rep)
            if result_f:
                fig_f, _ = result_f
                fig_f.update_traces(
                    textfont=dict(size=40, color="rgba(255,255,255,0.92)"),
                    selector=dict(type="bar"),
                )
                fig_f.update_layout(
                    height=580,
                    title=dict(text=""),
                    xaxis=dict(tickfont=_TV_AF),
                    yaxis=dict(tickfont=_TV_YTXT, automargin=True),
                    legend=dict(
                        orientation="v", x=0.82, y=0.04,
                        xanchor="left", yanchor="bottom",
                        bgcolor="rgba(15,14,11,0.85)",
                        bordercolor="rgba(255,255,255,0.08)",
                        borderwidth=1,
                        font=dict(size=28),
                    ),
                    margin=dict(t=10, b=20, l=20, r=40),
                )
                st.plotly_chart(fig_f, use_container_width=True, config=_CONF)
        else:
            st.info("Sem dados de etapas.")

    elif slide == 7:
        _tv_h("Motivos de Reprovação — Alto Nível", periodo)
        mot = agg.get("top_motivos", {})
        fig = _fig_barras_h(mot, "Motivo de Reprovação — Alto Nível", "#ef4444", pct_base=n_rep)
        if fig:
            fig.update_traces(textfont=_TV_TXT)
            fig.update_layout(
                uniformtext_minsize=25, uniformtext_mode="show",
                height=620,
                title=dict(text="", font=_TV_TF),
                xaxis=dict(tickfont=_TV_AF),
                yaxis=dict(tickfont=_TV_YTXT, automargin=True),
                margin=dict(t=10, b=20, l=20, r=120),
            )
            st.plotly_chart(fig, use_container_width=True, config=_CONF)
        else:
            st.info("Sem dados de motivos.")

    elif slide == 8:
        _tv_h("Motivos de Reprovação — Detalhado", periodo)
        mot_det = _merge_motivos_det(agg.get("top_motivos_det", {}))
        if mot_det:
            n_det = sum(mot_det.values())
            fig = _fig_barras_h(mot_det, "Motivo Detalhado", "#f97316", pct_base=n_det)
            if fig:
                fig.update_traces(textfont=_TV_TXT)
                fig.update_layout(
                    height=620,
                    title=dict(text="", font=_TV_TF),
                    xaxis=dict(tickfont=_TV_AF),
                    yaxis=dict(tickfont=_TV_YTXT, automargin=True),
                    margin=dict(t=10, b=20, l=20, r=120),
                )
                st.plotly_chart(fig, use_container_width=True, config=_CONF)
        else:
            st.info("Sem dados de motivos detalhados.")

    elif slide == 9:
        _tv_h("Leads com Bloqueio por Tipo", periodo)
        fig = _fig_bloqueios(agg.get("bloqueios", {}), n_rep=n_rep)
        if fig:
            fig.update_traces(textfont=dict(size=28, color="#e2e8f0"))
            fig.update_layout(
                height=520,
                title=dict(text=""),
                xaxis=dict(tickfont=dict(size=28, color="#cbd5e1")),
                yaxis=dict(tickfont=_TV_AF),
                margin=dict(t=10, b=40, l=80, r=80),
            )
            st.plotly_chart(fig, use_container_width=True, config=_CONF)
        else:
            st.info("Sem dados de bloqueios.")

    elif slide == 10:
        _tv_h("Top Empregadores dos Reprovados", periodo)
        emp_rep = agg.get("top_emp_rep", {})
        if emp_rep:
            fig = _fig_barras_h(emp_rep, "Top Empregadores (Reprovados)", "#ef4444", pct_base=n_rep, show_pct=False)
            if fig:
                fig.update_traces(textfont=_TV_TXT, textangle=0)
                fig.update_layout(
                    height=620,
                    title=dict(text="", font=_TV_TF),
                    xaxis=dict(tickfont=_TV_AF),
                    yaxis=dict(tickfont=_TV_YTXT, automargin=True),
                    margin=dict(t=10, b=20, l=20, r=120),
                )
                st.plotly_chart(fig, use_container_width=True, config=_CONF)
        else:
            st.info("Sem dados de empregadores dos reprovados.")

    elif slide == 11:
        _tv_h("UF dos Reprovados", periodo)
        ufs = agg.get("top_ufs", {})
        if ufs:
            fig = _fig_mapa_ufs(ufs)
            if fig:
                fig.update_layout(height=750)
                st.plotly_chart(fig, use_container_width=True, config=_CONF)
            else:
                n_ufs = sum(ufs.values())
                fig2 = _fig_barras_h(ufs, "UF dos Reprovados", "#3b82f6", n=27, pct_base=n_ufs)
                if fig2:
                    fig2.update_traces(textfont=_TV_TXT)
                    fig2.update_layout(
                        height=620,
                        title=dict(text="", font=_TV_TF),
                        xaxis=dict(tickfont=_TV_AF),
                        yaxis=dict(tickfont=_TV_YTXT, automargin=True),
                        margin=dict(t=10, b=20, l=20, r=120),
                    )
                    st.plotly_chart(fig2, use_container_width=True, config=_CONF)
        else:
            st.info("Sem dados de UF.")

    elif slide == 12:
        _tv_h("CNAEs Bloqueados dos Reprovados", periodo)
        cnaes = agg.get("top_cnaes", {})
        if cnaes:
            n_cnae = sum(cnaes.values())
            fig = _fig_barras_h(_sem_codigo(cnaes), "Top CNAEs Bloqueados", "#eab308",
                                pct_base=n_cnae, show_abs=True)
            if fig:
                fig.update_traces(textfont=_TV_TXT)
                fig.update_layout(
                    height=620,
                    title=dict(text="", font=_TV_TF),
                    xaxis=dict(tickfont=_TV_AF),
                    yaxis=dict(tickfont=_TV_YTXT, automargin=True),
                    margin=dict(t=10, b=20, l=20, r=55),
                )
                st.plotly_chart(fig, use_container_width=True, config=_CONF)
        else:
            st.info("Sem dados de CNAE bloqueado.")

    elif slide == 13:
        _tv_h("CBOs Bloqueados dos Reprovados", periodo)
        cbos_rep = agg.get("top_cbos_rep", {})
        if cbos_rep:
            n_cbo_r = sum(cbos_rep.values())
            fig = _fig_barras_h(_sem_codigo(cbos_rep), "Top CBOs Bloqueados", "#a855f7",
                                pct_base=n_cbo_r, show_abs=True)
            if fig:
                fig.update_traces(textfont=_TV_TXT)
                fig.update_layout(
                    height=620,
                    title=dict(text="", font=_TV_TF),
                    xaxis=dict(tickfont=_TV_AF),
                    yaxis=dict(tickfont=_TV_YTXT, automargin=True),
                    margin=dict(t=10, b=20, l=20, r=55),
                )
                st.plotly_chart(fig, use_container_width=True, config=_CONF)
        else:
            st.info("Sem dados de CBO dos reprovados.")

    elif slide == 14:
        _tv_h("Top Empregadores dos Aprovados", periodo)
        emp_ap = agg.get("top_empregadores", {})
        if emp_ap:
            fig = _fig_barras_h(emp_ap, "Top Empregadores (Aprovados)", "#22c55e", pct_base=n_ap)
            if fig:
                fig.update_traces(textfont=_TV_TXT)
                fig.update_layout(
                    height=620,
                    title=dict(text="", font=_TV_TF),
                    xaxis=dict(tickfont=_TV_AF),
                    yaxis=dict(tickfont=_TV_YTXT, automargin=True),
                    margin=dict(t=10, b=20, l=20, r=120),
                )
                st.plotly_chart(fig, use_container_width=True, config=_CONF)
        else:
            st.info("Sem dados de empregadores dos aprovados.")

    elif slide == 15:
        _tv_h("Evolução Temporal", periodo)
        fig = _fig_evolucao(agg, n_dias, dias_raw=dias_raw, datas_sel=datas_sel)
        if fig:
            fig.update_layout(
                height=620,
                title=dict(text=""),
                margin=dict(t=120, b=20, l=10, r=20),
                xaxis=dict(tickfont=_TV_AF, title=dict(font=_TV_AF)),
                yaxis=dict(tickfont=_TV_AF, title=dict(font=_TV_AF)),
                legend=dict(
                    orientation="h",
                    x=0.5, y=1.07,
                    xanchor="center", yanchor="bottom",
                    bgcolor="rgba(15,14,11,0.88)",
                    bordercolor="rgba(255,255,255,0.10)",
                    borderwidth=1,
                    font=dict(size=34, color="#94a3b8"),
                ),
            )
            st.plotly_chart(fig, use_container_width=True, config=_CONF)

    elif slide == 16:
        _tv_h("Top CBOs dos Aprovados", periodo)
        cbos_ap = agg.get("top_cbos", {})
        if cbos_ap:
            fig = _fig_barras_h(_sem_codigo(cbos_ap), "Top CBOs (Aprovados)", "#3b82f6", pct_base=n_ap)
            if fig:
                fig.update_traces(textfont=_TV_TXT)
                fig.update_layout(
                    height=620,
                    title=dict(text="", font=_TV_TF),
                    xaxis=dict(tickfont=_TV_AF),
                    yaxis=dict(tickfont=_TV_YTXT, automargin=True),
                    margin=dict(t=10, b=20, l=20, r=55),
                )
                st.plotly_chart(fig, use_container_width=True, config=_CONF)
        else:
            st.info("Sem dados de CBO dos aprovados.")

    _tv_nav(slide)


# ── TV auto-login via token na URL ───────────────────────────────────────────
# URL: https://<app>/?tv=<tv_token configurado em secrets.toml>
# Entra direto no modo TV sem login, sem cookie, sem interação.
_tv_url_token = st.query_params.get("tv", "")
_tv_secret    = st.secrets.get("auth", {}).get("tv_token", "")
if _tv_url_token and _tv_secret and _tv_url_token == _tv_secret:
    if not st.session_state.get("logged_in"):
        st.session_state.update({
            "logged_in":       True,
            "user_email":      "tv",
            "display_name":    "TV",
            "_cookie_set":     True,
            "_cookie_checked": True,
            "_is_tv":          True,   # sessão TV: sem cookie, sem expiração por inatividade
        })
    if "tv_slide" not in st.session_state:
        st.session_state["tv_slide"] = 0

# ── Autenticação ─────────────────────────────────────────────────────────────

_cookies = CookieController()

if not st.session_state.get("logged_in"):
    # Logout explícito: ignora o cookie nesta renderização (JS de remoção ainda não executou)
    _just_logged_out = st.session_state.pop("_force_logout", False)
    token = _cookies.get(_COOKIE_NAME)
    if token is None and not st.session_state.get("_cookie_checked"):
        # Primeira renderização: cookie controller ainda não leu o cookie — aguarda
        st.session_state["_cookie_checked"] = True
        st.markdown("""<style>
        body,[data-testid="stAppViewContainer"]{background:#0a0908!important}
        [data-testid="stHeader"],footer,#MainMenu{display:none!important}
        </style>""", unsafe_allow_html=True)
        st.stop()
    if token and not _just_logged_out:
        email_from_cookie = _verify_token(token)
        if email_from_cookie:
            user_from_cookie = _find_user(email_from_cookie)
            if user_from_cookie:
                st.session_state.update({
                    "logged_in":    True,
                    "user_email":   email_from_cookie,
                    "display_name": user_from_cookie.get("display_name", email_from_cookie),
                    "_cookie_set":  True,
                    "_cookie_checked": True,
                })
                st.rerun()
        _cookies.remove(_COOKIE_NAME)
    st.session_state["_cookie_checked"] = True
    _login_page(_cookies)

if not st.session_state.get("_is_tv"):
    _now = time.time()
    _last_ref = st.session_state.get("_last_cookie_refresh", 0)
    if _now - _last_ref > _COOKIE_REFRESH_AFTER:
        try:
            _cookies.set(_COOKIE_NAME, _make_token(st.session_state["user_email"]),
                         max_age=_COOKIE_MAX_AGE)
            st.session_state["_last_cookie_refresh"] = _now
        except RuntimeError as e:
            st.error(str(e))
            st.stop()
    if not st.session_state.get("_cookie_set"):
        st.session_state["_cookie_set"] = True

try:
    # ── Carrega datas disponiveis ─────────────────────────────────────────────────
    
    datas = listar_datas()
    if not datas:
        st.error("Sem dados disponíveis ou erro ao acessar o repositório.")
        st.stop()
    
    data_min = datetime.strptime(datas[0],  "%Y%m%d").date()
    data_max = datetime.strptime(datas[-1], "%Y%m%d").date()
    d_ini_default = data_max

    # _slot: container exclusivo do dashboard normal.
    # Em modo TV, _slot.empty() remove todo conteúdo anterior deste container
    # antes de renderizar os slides — elimina o ghosting do dashboard normal.
    _slot = st.empty()

    # ── Modo TV: atalho completo ──────────────────────────────────────────────────
    if st.query_params.get("tv", "0") == "1":
        # Slide via session_state (não URL) → rerun via WebSocket, sem page reload, sem perder fullscreen
        if "tv_slide" not in st.session_state:
            st.session_state["tv_slide"] = int(st.query_params.get("slide", "0")) % _TV_N_SLIDES
        _tv_slide  = st.session_state["tv_slide"]
        _tv_prev   = (_tv_slide - 1) % _TV_N_SLIDES
        _tv_next   = (_tv_slide + 1) % _TV_N_SLIDES
    
        # CSS TV antecipado (evita flash antes de _render_tv_slide)
        _slot.empty()  # remove dashboard normal do DOM antes de renderizar o slide
        st.markdown(_TV_CSS, unsafe_allow_html=True)
    
        # Tela cheia automática (melhor esforço — pode ser bloqueado sem gesto do usuário)
        components.html("""
        <script>
        try {
            var el = parent.document.documentElement;
            var fn = el.requestFullscreen || el.webkitRequestFullscreen || el.mozRequestFullScreen;
            if (fn) fn.call(el);
        } catch(e) {}
        </script>
        """, height=0)
    
        # Seletor de período + navegação de slides na mesma barra
        _default_d_ini = data_max
    
        # session_state é a única fonte da data — mais confiável que query_params entre reruns.
        if "_tv_date" not in st.session_state:
            # Inicializa: tenta query_params, senão usa o padrão
            _tv_ini_raw = st.query_params.get("tv_ini", "")
            try:
                _tv_date_init = (datetime.strptime(_tv_ini_raw, "%Y%m%d").date()
                                 if _tv_ini_raw else _default_d_ini)
            except ValueError:
                _tv_date_init = _default_d_ini
            st.session_state["_tv_date"] = max(data_min, min(_tv_date_init, data_max))
        if "_tv_picker_ver" not in st.session_state:
            st.session_state["_tv_picker_ver"] = 0
    
        _d_ini_tv = max(data_min, min(st.session_state["_tv_date"], data_max))
    
        _cp_prev, _cp_lbl, _cp_date, _cp_7d, _cp_3d, _cp_1d, _cp_info, _cp_next, _cp_exit = \
            st.columns([1, 1, 2, 1.8, 1.8, 1.8, 1.5, 1, 2])
        with _cp_prev:
            if st.button("‹", key="tv_prev", use_container_width=True):
                st.session_state["tv_slide"] = _tv_prev
                st.rerun()
        with _cp_lbl:
            st.markdown("<p style='margin:6px 0 0;color:#94a3b8;font-size:13px'>📅 Desde:</p>",
                        unsafe_allow_html=True)
        with _cp_date:
            # Versão no key garante widget novo a cada clique de atalho (sem cache stale)
            _new_ini = st.date_input(
                "", value=_d_ini_tv,
                min_value=data_min, max_value=data_max,
                key=f"tv_ini_picker_{st.session_state['_tv_picker_ver']}",
                label_visibility="collapsed",
            )
        with _cp_7d:
            if st.button("Últimos 7 dias", key="tv_7d", use_container_width=True):
                st.session_state["_tv_date"] = max(data_min, data_max - timedelta(days=6))
                st.session_state["_tv_picker_ver"] += 1
                st.session_state["tv_slide"] = 0
                st.rerun()
        with _cp_3d:
            if st.button("Últimos 3 dias", key="tv_3d", use_container_width=True):
                st.session_state["_tv_date"] = max(data_min, data_max - timedelta(days=2))
                st.session_state["_tv_picker_ver"] += 1
                st.session_state["tv_slide"] = 0
                st.rerun()
        with _cp_1d:
            if st.button("Desde Ontem", key="tv_1d", use_container_width=True):
                st.session_state["_tv_date"] = max(data_min, data_max - timedelta(days=1))
                st.session_state["_tv_picker_ver"] += 1
                st.session_state["tv_slide"] = 0
                st.rerun()
        with _cp_info:
            st.markdown(
                f"<p style='text-align:center;margin:8px 0;color:#64748b;"
                f"font-size:12px;font-family:monospace'>{_tv_slide+1} / {_TV_N_SLIDES}</p>",
                unsafe_allow_html=True,
            )
        with _cp_next:
            if st.button("›", key="tv_next", use_container_width=True):
                st.session_state["tv_slide"] = _tv_next
                st.rerun()
        with _cp_exit:
            if st.button("Sair do modo TV", key="tv_exit", use_container_width=True):
                st.session_state.pop("tv_slide", None)
                st.query_params.clear()
                st.rerun()
    
        if _new_ini != _d_ini_tv:
            st.session_state["_tv_date"] = _new_ini
            st.session_state["tv_slide"] = 0
            st.rerun()
        _d_ini_tv = _new_ini
    
        _datas_sel_tv = [d for d in datas
                         if _d_ini_tv <= datetime.strptime(d, "%Y%m%d").date() <= data_max]
        _dias_raw_tv = [d for d in [carregar_dia(d) for d in _datas_sel_tv] if d]
        if not _dias_raw_tv:
            st.warning("Sem dados para o período selecionado.")
            st.stop()
        _agg_tv = agregar(_dias_raw_tv)
        # Tipos não-BT dos 3 dias extras antes do período TV
        _d_extra_ini_tv = _d_ini_tv - timedelta(days=3)
        _datas_extra_tv = [d for d in datas
                           if _d_extra_ini_tv <= datetime.strptime(d, "%Y%m%d").date() < _d_ini_tv]
        for _d_extra_str in _datas_extra_tv:
            _dia_extra_tv = carregar_dia(_d_extra_str)
            if not _dia_extra_tv:
                continue
            for _ts_e, _v_e in _dia_extra_tv.get("projecao_tipos", {}).items():
                if _ts_e == "BLOQUEIO_TEMPORARIO":
                    continue
                _ex = _agg_tv["projecao_tipos"].get(_ts_e, {"count": 0, "valor": 0.0, "liberado": 0.0, "iof": 0.0})
                _agg_tv["projecao_tipos"][_ts_e] = {
                    "count":    _ex["count"]    + _v_e.get("count", 0),
                    "valor":    _ex["valor"]    + _v_e.get("valor", 0.0),
                    "liberado": _ex["liberado"] + _v_e.get("liberado", 0.0),
                    "iof":      _ex["iof"]      + _v_e.get("iof", 0.0),
                }
        _periodo_tv = (
            _d_ini_tv.strftime("%d/%m/%Y") if _d_ini_tv == data_max
            else f"{_d_ini_tv.strftime('%d/%m/%Y')} — {data_max.strftime('%d/%m/%Y')}"
        )
        _render_tv_slide(
            _tv_slide, _agg_tv, _agg_tv["funil"], _agg_tv["financeiro"],
            len(_datas_sel_tv), _dias_raw_tv, _datas_sel_tv, _periodo_tv,
        )
        _tv_now = time.time()
        if st.session_state.get("tv_slide_at_start") != _tv_slide:
            # Primeira renderização deste slide: rerun imediato para enviar frame
            # completo ao browser e remover elementos antigos do DOM.
            st.session_state["tv_slide_start"] = _tv_now
            st.session_state["tv_slide_at_start"] = _tv_slide
            st.rerun()
        else:
            # Segunda renderização: DOM já está limpo. Aguarda o tempo restante.
            _tv_remaining = max(0.0, _TV_INTERVAL_S - (_tv_now - st.session_state["tv_slide_start"]))
            time.sleep(_tv_remaining)
            st.session_state["tv_slide"] = (_tv_slide + 1) % _TV_N_SLIDES
            st.session_state.pop("tv_slide_start", None)
            st.session_state.pop("tv_slide_at_start", None)
            st.rerun()
    
    # ── Saída de modo TV: sai do fullscreen via JS ────────────────────────────────
    else:
        components.html("""
        <script>
        try {
            var doc = parent.document;
            var ef = doc.exitFullscreen || doc.webkitExitFullscreen || doc.mozCancelFullScreen;
            if (ef && (doc.fullscreenElement || doc.webkitFullscreenElement)) ef.call(doc);
        } catch(e) {}
        </script>
        """, height=0)
        with _slot.container():

            # ── Header + seletor ──────────────────────────────────────────────────────────
            
            col_title, col_picker = st.columns([1, 1])
            
            with col_title:
                _c_tit, _c_tv, _c_out = st.columns([3, 1, 1])
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
                        'color:#e2e8f0;letter-spacing:-0.5px">ileads</span>'
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
                        st.session_state["tv_slide"] = 0
                        st.query_params["tv"] = "1"
                        st.rerun()
                with _c_out:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    if st.button("Sair", use_container_width=True):
                        _cookies.remove(_COOKIE_NAME)
                        for _k in ["logged_in", "user_email", "display_name", "_cookie_set", "_cookie_checked"]:
                            st.session_state.pop(_k, None)
                        st.session_state["_cookie_checked"] = True  # evita tela preta pós-logout
                        st.session_state["_force_logout"] = True    # impede restore do cookie no mesmo rerun
                        st.rerun()
            
            with col_picker:
                _cp_dat, _cp_ref = st.columns([4, 1])
                with _cp_dat:
                    intervalo = st.date_input(
                        "Período de análise",
                        value=(d_ini_default, data_max),
                        min_value=data_min, max_value=data_max,
                        format="DD/MM/YYYY",
                    )
                with _cp_ref:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    if st.button("↺", use_container_width=True, help="Forçar atualização dos dados"):
                        carregar_dia.clear()
                        listar_datas.clear()
                        st.rerun()
            
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
            # Extra: 3 dias antes de d_ini para capturar tipos não-BT de leads antigos suspensos
            _d_extra_ini = d_ini - timedelta(days=3)
            datas_extra = [d for d in datas
                           if _d_extra_ini <= datetime.strptime(d, "%Y%m%d").date() < d_ini]

            with st.spinner(f"Carregando {n_dias} dia(s)..."):
                dias_raw = [d for d in [carregar_dia(d) for d in datas_sel] if d]

            if not dias_raw:
                st.warning("Sem dados para o período selecionado.")
                st.stop()

            agg = agregar(dias_raw)
            # Tipos não-BT dos 3 dias extras: leads suspensos há mais dias que o início do período
            for _d_extra_str in datas_extra:
                _dia_extra = carregar_dia(_d_extra_str)
                if not _dia_extra:
                    continue
                for _ts_e, _v_e in _dia_extra.get("projecao_tipos", {}).items():
                    if _ts_e == "BLOQUEIO_TEMPORARIO":
                        continue  # BT só conta se Pix day cai no período selecionado
                    _ex = agg["projecao_tipos"].get(_ts_e, {"count": 0, "valor": 0.0, "liberado": 0.0, "iof": 0.0})
                    agg["projecao_tipos"][_ts_e] = {
                        "count":    _ex["count"]    + _v_e.get("count", 0),
                        "valor":    _ex["valor"]    + _v_e.get("valor", 0.0),
                        "liberado": _ex["liberado"] + _v_e.get("liberado", 0.0),
                        "iof":      _ex["iof"]      + _v_e.get("iof", 0.0),
                    }
            f   = agg["funil"]
            fin = agg["financeiro"]
            
            periodo_label = (
                d_ini.strftime("%d/%m/%Y") if d_ini == d_fim
                else f"{d_ini.strftime('%d/%m/%Y')} — {d_fim.strftime('%d/%m/%Y')}"
            )
            
            # ── KPIs ──────────────────────────────────────────────────────────────────────
            
            taxa     = f"{f['taxa_aprovacao']:.1f}%" if f.get("terminais") else "—"
            vol      = fin.get("ValorContratacao", {})
            vol_s    = ("R$ " + f"{vol['total']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if vol.get("total") else "—"
            _pt_nm       = agg.get("projecao_tipos", {})
            # BT live: independente do período — data de referência baseada no horário BRT atual
            _now_brt_nm  = datetime.utcnow() - timedelta(hours=3)
            _pix_ab_nm   = _now_brt_nm.weekday() < 5 and (7, 0) <= (_now_brt_nm.hour, _now_brt_nm.minute) <= (18, 30)
            _data_ref_nm = _now_brt_nm.date()
            if not _pix_ab_nm:
                _data_ref_nm += timedelta(days=1)
                while _data_ref_nm.weekday() >= 5:
                    _data_ref_nm += timedelta(days=1)
            _ref_str_nm    = _data_ref_nm.strftime("%Y%m%d")
            _ref_label_nm  = _data_ref_nm.strftime("%d/%m/%Y")
            _ref_short_nm  = _data_ref_nm.strftime("%d/%m")
            _ultimo_nm     = carregar_dia(max(datas)) if datas else {}
            _bt_live_nm    = _ultimo_nm.get("bt_pix_days", {}).get(_ref_str_nm, {})
            _proj_cnt   = sum(d["count"]    for ts, d in _pt_nm.items() if ts != "BLOQUEIO_TEMPORARIO") + _bt_live_nm.get("count", 0)
            _proj_cnt_s = f"{_proj_cnt:,}".replace(",", ".")
            _proj_val   = sum(d["valor"]    for ts, d in _pt_nm.items() if ts != "BLOQUEIO_TEMPORARIO") + _bt_live_nm.get("valor", 0.0)
            _proj_lib   = sum(d["liberado"] for ts, d in _pt_nm.items() if ts != "BLOQUEIO_TEMPORARIO") + _bt_live_nm.get("liberado", 0.0)
            _proj_iof   = sum(d["iof"]      for ts, d in _pt_nm.items() if ts != "BLOQUEIO_TEMPORARIO") + _bt_live_nm.get("iof", 0.0)
            if _proj_val:
                _proj_val_fmt = ("R$ " + f"{_proj_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                _proj_lib_fmt = ("R$ " + f"{_proj_lib:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                _proj_iof_fmt = ("R$ " + f"{_proj_iof:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                _proj_kpi_sub = (
                    f"<span style='color:#64748b;font-size:0.82em'>"
                    f"Lib. {_proj_lib_fmt} · IOF {_proj_iof_fmt}"
                    "</span>"
                )
            else:
                _proj_val_fmt = "—"
                _proj_kpi_sub = ""
            
            _prazo_d   = fin.get("Prazo", {})
            _taxa_d    = fin.get("Taxa", {})
            _parcela_d = fin.get("ValorParcela", {})
            prazo_s   = f"{_prazo_d['media']:.0f} meses"  if _prazo_d.get("media") else "—"
            ticket_s  = ("R$ " + f"{vol['media']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if vol.get("media") else "—"
            parcela_s = ("R$ " + f"{_parcela_d['media']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if _parcela_d.get("media") else "—"
            taxa_s    = f"{_taxa_d['media']:.2f}".replace(".", ",") + "% a.m." if _taxa_d.get("media") else "—"
            
            _f_total_fmt = _nbr(f["total"])
            _f_aprov_fmt = _nbr(f["aprovados"])
            _f_term_fmt  = _nbr(f["terminais"])
            _f_repro_fmt = _nbr(f["reprovados"])
            _f_ag_fmt    = _nbr(_proj_cnt)
            st.markdown(f"""
            <div class="kpi-row">
              <div class="kpi-card">
                <div class="kpi-label">Total de leads</div>
                <div class="kpi-value">{_f_total_fmt}</div>
                <div class="kpi-sub">{periodo_label} · {n_dias} dia(s)</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Aprovados</div>
                <div class="kpi-value">{_f_aprov_fmt}</div>
                <div class="kpi-sub">taxa: {taxa}</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Reprovados</div>
                <div class="kpi-value">{_f_repro_fmt}</div>
                <div class="kpi-sub">{f['taxa_reprovacao']:.1f}% dos finalizados</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Projeção de Leads a Desembolsar</div>
                <div class="kpi-value">{_f_ag_fmt}</div>
                <div class="kpi-sub">Pix {_ref_short_nm}</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Projeção de Desembolso</div>
                <div class="kpi-value" style="color:#FEC52E">{_proj_val_fmt}</div>
                <div class="kpi-sub">Pix {_ref_short_nm} · {_proj_kpi_sub}</div>
              </div>
            </div>
            <div class="kpi-row">
              <div class="kpi-card">
                <div class="kpi-label">Ticket médio do empréstimo</div>
                <div class="kpi-value">{ticket_s}</div>
                <div class="kpi-sub">valor contratado</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Ticket médio da parcela</div>
                <div class="kpi-value">{parcela_s}</div>
                <div class="kpi-sub">média pond. pelo prazo</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Taxa média</div>
                <div class="kpi-value">{taxa_s}</div>
                <div class="kpi-sub">contratos aprovados</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Prazo médio</div>
                <div class="kpi-value">{prazo_s}</div>
                <div class="kpi-sub">contratos aprovados</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Volume aprovado</div>
                <div class="kpi-value">{vol_s}</div>
                <div class="kpi-sub">valor contratado total</div>
              </div>
            </div>
            """, unsafe_allow_html=True)
            
            # ── 1. Projeção de Desembolso ────────────────────────────────────────────────
            
            st.markdown('<div class="sec">1. Projeção de Desembolso</div>', unsafe_allow_html=True)

            # Breakdown por dia para as setinhas de expansão na tabela.
            # carregar_dia é cached — não faz requests adicionais.
            _pt_por_dia: dict = {}
            for _ds2 in list(datas_sel) + list(datas_extra):
                _dj2 = carregar_dia(_ds2)
                if not _dj2:
                    continue
                for _ts2, _v2 in _dj2.get("projecao_tipos", {}).items():
                    if _ts2 == "BLOQUEIO_TEMPORARIO":
                        continue
                    if _v2.get("count", 0) > 0:
                        if _ts2 not in _pt_por_dia:
                            _pt_por_dia[_ts2] = {}
                        _pt_por_dia[_ts2][_ds2] = {
                            "count":    _v2.get("count", 0),
                            "valor":    _v2.get("valor", 0.0),
                            "liberado": _v2.get("liberado", 0.0),
                            "iof":      _v2.get("iof", 0.0),
                        }
            # BT: breakdown já está keyed por dia Pix no JSON mais recente
            _pt_por_dia["BLOQUEIO_TEMPORARIO"] = _ultimo_nm.get("bt_pix_days", {})

            _TIPO_LABEL_MAP = {
                "PAGAMENTO":                 "Aguardando Pagamento Pix (Suspenso)",
                "ASSINADO":                  "Falha Pós-Assinatura (Pendente Falha)",
                "ASSINATURA":                "Aguardando CCB Único (Suspenso)",
                "ENTREVISTA":                "Aguardando Entrevista Antifraude da Nuvidio (Suspenso)",
                "FORMALIZACAO":              "Aguardando Aceite para Formalização (Suspenso)",
                "PRE_APROVADO":              "Aguardando Aceite de Proposta Enviada (Suspenso)",
                "SIMULACAO":                 "Aguardando nova Simulação de Proposta (Suspenso)",
                "PENDENTE_DADOS_PAGAMENTO":  "Aguardando Resolução de Pendência em Dados de Pagamento (Suspenso)",
                "BLOQUEIO_TEMPORARIO":       f"Aguardando 24h — Pix {_ref_label_nm}",
                "AVERBACAO_PENDENTE_MANUAL": "Pendente de Averbação Manual (Pendente Manual)",
            }
            
            # Tabela: tipos nao-BT do periodo + BT live (mesma logica das KPIs)
            _pt_sec_base = {ts: d for ts, d in agg.get("projecao_tipos", {}).items() if ts != "BLOQUEIO_TEMPORARIO"}
            if _bt_live_nm.get("count", 0) > 0:
                _pt_sec_base["BLOQUEIO_TEMPORARIO"] = _bt_live_nm
            _pt_sec = _pt_sec_base
            if _pt_sec:
                def _r(v): return ("R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if v else "—"
                def _n(v): return f"{v:,}".replace(",", ".")
            
                _sorted = sorted(_pt_sec.items(), key=lambda x: -x[1]["valor"])
                _t_cnt  = sum(d["count"]    for d in _pt_sec.values())
                _t_val  = sum(d["valor"]    for d in _pt_sec.values())
                _t_lib  = sum(d["liberado"] for d in _pt_sec.values())
                _t_iof  = sum(d["iof"]      for d in _pt_sec.values())
            
                _rows = ""
                for ts, d in _sorted:
                    _label   = _TIPO_LABEL_MAP.get(ts, ts)
                    _dias_ts = _pt_por_dia.get(ts, {})
                    if _dias_ts:
                        _is_bt      = ts == "BLOQUEIO_TEMPORARIO"
                        _det_inner  = "".join(
                            f"<div class='pj-det-row'>"
                            f"<span class='pj-det-dt'>{'Pix ' if _is_bt else ''}"
                            f"{datetime.strptime(_ds3, '%Y%m%d').strftime('%d/%m/%Y')}</span>"
                            f"<span class='pj-det-n'>{_n(_dv3['count'])} lead{'s' if _dv3['count'] != 1 else ''}</span>"
                            f"<span class='pj-det-v'>{_r(_dv3['valor'])}</span>"
                            f"</div>"
                            for _ds3, _dv3 in sorted(_dias_ts.items())
                        )
                        _cell_lbl = f"<details class='pj-det'><summary>{_label}</summary>{_det_inner}</details>"
                    else:
                        _cell_lbl = _label
                    _rows += (
                        f"<tr>"
                        f"<td class='pj-lbl'>{_cell_lbl}</td>"
                        f"<td class='pj-n'>{_n(d['count'])}</td>"
                        f"<td class='pj-n'>{_r(d['valor'])}</td>"
                        f"<td class='pj-n'>{_r(d['liberado'])}</td>"
                        f"<td class='pj-n'>{_r(d['iof'])}</td>"
                        f"</tr>"
                    )
            
                st.markdown(f"""
            <style>
            .pj-wrap{{overflow-x:auto;margin:6px 0 18px}}
            .pj-tbl{{width:100%;border-collapse:collapse;font-size:.91em}}
            .pj-tbl th{{background:#1c1a17;color:#94a3b8;font-weight:600;padding:9px 16px;
                        text-align:left;border-bottom:2px solid #272420;white-space:nowrap}}
            .pj-tbl th.pj-n{{text-align:right}}
            .pj-tbl td{{padding:7px 16px;border-bottom:1px solid #1c1a17;color:#e2e8f0}}
            .pj-lbl{{color:#cbd5e1;white-space:nowrap}}
            .pj-n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
            .pj-tbl tr:hover td{{background:#1a1815}}
            .pj-tot td{{background:#1c1a17!important;color:#FEC52E!important;
                        font-weight:700;border-top:2px solid #272420}}
            .pj-tot .pj-lbl{{color:#FEC52E}}
            .pj-det{{cursor:pointer}}
            .pj-det summary{{list-style:none;display:flex;align-items:center;gap:6px;
                             cursor:pointer;color:#cbd5e1;white-space:nowrap}}
            .pj-det summary::-webkit-details-marker{{display:none}}
            .pj-det summary::before{{content:'▶';font-size:.6em;color:#64748b;
                                     transition:transform .15s;flex-shrink:0}}
            .pj-det[open] summary::before{{transform:rotate(90deg)}}
            .pj-det-row{{display:flex;gap:16px;padding:3px 0 3px 18px;font-size:.82em;
                         color:#94a3b8;border-top:1px solid #272420}}
            .pj-det-dt{{min-width:110px;color:#64748b}}
            .pj-det-n{{min-width:80px}}
            .pj-det-v{{font-variant-numeric:tabular-nums}}
            </style>
            <div class="pj-wrap">
            <table class="pj-tbl">
              <thead><tr>
                <th>Etapa</th>
                <th class="pj-n">Leads</th>
                <th class="pj-n">Valor Total</th>
                <th class="pj-n">Liberado</th>
                <th class="pj-n">IOF</th>
              </tr></thead>
              <tbody>
                {_rows}
                <tr class="pj-tot">
                  <td class="pj-lbl">Total</td>
                  <td class="pj-n">{_n(_t_cnt)}</td>
                  <td class="pj-n">{_r(_t_val)}</td>
                  <td class="pj-n">{_r(_t_lib)}</td>
                  <td class="pj-n">{_r(_t_iof)}</td>
                </tr>
              </tbody>
            </table>
            </div>
            """, unsafe_allow_html=True)
            else:
                st.markdown(
                    "<p style='color:#475569;font-size:.88em'>Sem dados de projeção para o período.</p>",
                    unsafe_allow_html=True,
                )
            
            # ── 2. Leads Aguardando Desembolso ───────────────────────────────────────────

            st.markdown('<div class="sec">2. Leads Aguardando Desembolso</div>', unsafe_allow_html=True)

            _pf = agg.get("pipeline_financeiro", {})
            _dup = agg.get("duplicatas_cpf", [])

            html_pf = _html_tabela_pipeline(_pf)
            if html_pf:
                st.markdown(html_pf, unsafe_allow_html=True)
                if n_dias > 1:
                    st.caption("*Dados do dia mais recente selecionado")

            if _dup:
                _brl2 = lambda x: "R$ " + f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                _dup_rows = []
                for _i, _item in enumerate(_dup):
                    _rc = "g0" if _i % 2 == 0 else "g1"
                    _conts = "<br>".join(
                        f'{c["codigo"] or c["identificador"][:8]} — {c["etapa"]} — {_brl2(c["valor"])}'
                        for c in _item["contratos"]
                    )
                    _dup_rows.append(
                        f'<tr class="{_rc}">'
                        f'<td>{_item["cpf"]}</td>'
                        f'<td>{_item["nome"]}</td>'
                        f'<td class="r">{len(_item["contratos"])}</td>'
                        f'<td class="r">{_brl2(_item["total"])}</td>'
                        f'<td style="font-size:.82em;line-height:1.5">{_conts}</td>'
                        f'</tr>'
                    )
                _dup_html = (
                    '<div class="dtbl-title" style="color:#f59e0b">&#9888; CPFs com múltiplos contratos &mdash; total &gt; R$&nbsp;15k</div>'
                    '<div class="dtbl-wrap"><table class="dtbl">'
                    '<thead><tr>'
                    '<th>CPF</th><th>Nome</th><th class="r">Contratos</th>'
                    '<th class="r">Total</th><th>Detalhes</th>'
                    '</tr></thead>'
                    '<tbody>' + "".join(_dup_rows) + '</tbody>'
                    '</table></div>'
                )
                st.markdown(_dup_html, unsafe_allow_html=True)
            elif _pf:
                st.markdown(
                    "<p style='color:#475569;font-size:.88em'>Nenhum CPF com múltiplos contratos acima de R$&nbsp;15k.</p>",
                    unsafe_allow_html=True,
                )

            # ── 3. Distribuição por Status ────────────────────────────────────────────────

            st.markdown('<div class="sec">3. Distribuição por Status</div>', unsafe_allow_html=True)
            
            col_d, col_f = st.columns(2)
            with col_d:
                fig = _fig_donut(f.get("_d_status", {}))
                if fig:
                    st.plotly_chart(fig, use_container_width=True, config=_CONF)
            with col_f:
                fig = _fig_funil_rico(f)
                if fig:
                    st.plotly_chart(fig, use_container_width=True, config=_CONF)
            
            # ── 4. Status Novo — CTPS ─────────────────────────────────────────────────────

            st.markdown('<div class="sec">4. Status Novo — CTPS</div>', unsafe_allow_html=True)
            _ncs = agg.get("novo_ctps_status", {})
            if _ncs:
                _ctps_total     = _ncs.get("ctps_total", 0)
                _ctps_antes     = _ncs.get("ctps_antes", 0)
                _ctps_apos      = _ncs.get("ctps_apos", 0)
                _ctps_outros_st = _ncs.get("ctps_outros_status", 0)
                _ctps_bot_total = _ctps_apos + _ctps_outros_st
                _outros_all     = _ncs.get("outros_total_all", 0)
                _grand_total    = _ctps_antes + _ctps_bot_total + _outros_all
                _pct_antes      = f"{100 * _ctps_antes     / _grand_total:.1f}%" if _grand_total else "—"
                _pct_bot        = f"{100 * _ctps_bot_total / _grand_total:.1f}%" if _grand_total else "—"
                _pct_outros     = f"{100 * _outros_all     / _grand_total:.1f}%" if _grand_total else "—"
                st.markdown(f"""
<div class="kpi-row" style="grid-template-columns: repeat(3, 1fr); max-width: 860px;">
  <div class="kpi-card">
    <div class="kpi-label">CTPS — Aguardando clique</div>
    <div class="kpi-value">{_nbr(_ctps_antes)}</div>
    <div class="kpi-sub">{_pct_antes} do total · {_nbr(_ctps_total)} CTPS Novos</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">CTPS — Bot WhatsApp iniciado</div>
    <div class="kpi-value">{_nbr(_ctps_bot_total)}</div>
    <div class="kpi-sub">{_pct_bot} do total · {_nbr(_ctps_outros_st)} em outros status</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Outros na esteira</div>
    <div class="kpi-value">{_nbr(_outros_all)}</div>
    <div class="kpi-sub">{_pct_outros} do total · não-CTPS (todos os status)</div>
  </div>
</div>
""", unsafe_allow_html=True)

            # ── 5. Evolução Temporal ──────────────────────────────────────────────────────

            st.markdown('<div class="sec">5. Evolução Temporal</div>', unsafe_allow_html=True)
            
            fig = _fig_evolucao(agg, n_dias, dias_raw=dias_raw, datas_sel=datas_sel)
            if fig:
                st.plotly_chart(fig, use_container_width=True, config=_CONF)
            
            # ── 6. Perfil Financeiro — Aprovados ─────────────────────────────────────────

            st.markdown('<div class="sec">6. Perfil Financeiro — Aprovados</div>', unsafe_allow_html=True)
            
            html_fin = _html_tabela_financeira(fin)
            if html_fin:
                st.markdown(html_fin, unsafe_allow_html=True)
                if n_dias > 1:
                    st.caption("*Mediana = média ponderada das medianas diárias")
            
            fig = _fig_histograma(agg.get("valores_contratacao", []))
            if fig:
                st.plotly_chart(fig, use_container_width=True, config=_CONF)
            
            # ── 7. Etapa de Reprovação ────────────────────────────────────────────────────

            st.markdown('<div class="sec">7. Etapa de Reprovação</div>', unsafe_allow_html=True)
            
            n_rep    = f.get("reprovados", 0)
            etapas_d = agg.get("etapas", {})
            etapa_motivos_d = agg.get("etapa_motivos", {})
            
            # Diagrama do Workflow
            diagrama_html = _html_diagrama(etapas_d, n_rep)
            if diagrama_html:
                st.markdown(diagrama_html, unsafe_allow_html=True)
                st.markdown("")
            
            # 2 abas: Visão geral | Visão de Funil
            if etapas_d and n_rep > 0:
                tab_g, tab_f = st.tabs(["Visão geral", "Visão de Funil"])

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
                        text=[f"{_nbr(v)} ({p})" for v, p in zip(x, ps)],
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
            
            # ── 8. Motivos de Reprovação ──────────────────────────────────────────────────

            st.markdown('<div class="sec">8. Motivos de Reprovação</div>', unsafe_allow_html=True)
            
            col_m1, col_m2 = st.columns(2)
            
            with col_m1:
                fig = _fig_barras_h(agg.get("top_motivos", {}),
                                    "Motivo de Reprovação — Alto Nível", "#ef4444", pct_base=n_rep)
                if fig:
                    st.plotly_chart(fig, use_container_width=True, config=_CONF)
                else:
                    st.info("Sem dados de motivos.")
            
            with col_m2:
                mot_det = _merge_motivos_det(agg.get("top_motivos_det", {}))
                if mot_det:
                    n_det = sum(mot_det.values())
                    fig = _fig_barras_h(mot_det, "Motivo de Reprovação — Detalhado", "#f97316",
                                        pct_base=n_det)
                    if fig:
                        st.plotly_chart(fig, use_container_width=True, config=_CONF)
                else:
                    st.info("Motivos detalhados ainda não disponíveis (requer nova exportação dos JSONs).")
            
            # ── 9. Bloqueios ──────────────────────────────────────────────────────────────

            st.markdown('<div class="sec">9. Bloqueios por Tipo</div>', unsafe_allow_html=True)
            
            fig = _fig_bloqueios(agg.get("bloqueios", {}), n_rep=n_rep)
            if fig:
                col_bl, _ = st.columns([1, 1])
                with col_bl:
                    st.plotly_chart(fig, use_container_width=True, config=_CONF)
            else:
                st.info("Sem dados de bloqueios.")
            
            # ── 10. Segmentação — Reprovados ─────────────────────────────────────────────

            st.markdown('<div class="sec">10. Segmentação — Reprovados</div>', unsafe_allow_html=True)
            
            col_s1, col_s2 = st.columns(2)
            
            with col_s1:
                emp_rep = agg.get("top_emp_rep", {})
                emp_mot = agg.get("emp_motivos", {})
                if emp_rep:
                    fig = _fig_barras_h(emp_rep, "Top Empregadores dos Reprovados", "#ef4444", pct_base=n_rep, show_pct=False)
                    if fig:
                        st.plotly_chart(fig, use_container_width=True, config=_CONF)
                    _tbl_html = _html_emp_rep_expandable(emp_rep, emp_mot, n_rep)
                    if _tbl_html:
                        st.markdown(_tbl_html, unsafe_allow_html=True)
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
            
            # ── 11. Aprovados — Empregadores e CBOs ──────────────────────────────────────

            st.markdown('<div class="sec">11. Aprovados — Empregadores e CBOs</div>', unsafe_allow_html=True)
            
            n_ap = f.get("aprovados", 0)
            
            col_e, col_c = st.columns(2)
            
            with col_e:
                emp_ap = agg.get("top_empregadores", {})
                emp_ap_stats = agg.get("emp_ap_stats", {})
                fig = _fig_barras_h(emp_ap, "Top Empregadores (Aprovados)", "#22c55e", pct_base=n_ap)
                if fig:
                    st.plotly_chart(fig, use_container_width=True, config=_CONF)
                tbl = _html_emp_ap_expandable(emp_ap, emp_ap_stats, n_ap)
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
        
except Exception:
    st.warning(
        "⚠️ **Plataforma em manutenção** — houve um erro inesperado. "
        "Aguarde alguns minutos e recarregue a página."
    )
    st.stop()
