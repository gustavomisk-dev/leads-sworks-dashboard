"""
Dashboard de leads SWorks — Streamlit Community Cloud.
Dados lidos do repositorio privado leads-sworks-data via GitHub API.
"""

import base64
import hashlib
import hmac
import json
import re
import statistics
import time
import bcrypt
import requests
import streamlit as st
import streamlit.components.v1 as components  # usado só p/ o download HTML (JS client-side)
import plotly.graph_objects as go
from datetime import datetime, timedelta
from collections import defaultdict
from io import BytesIO
from openpyxl import Workbook
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
.pj-i { display:inline-flex; align-items:center; justify-content:center; width:13px; height:13px; margin-left:5px; border-radius:50%; background:#334155; color:#cbd5e1; font:italic 700 8px Georgia,serif; vertical-align:super; line-height:1; cursor:help; flex-shrink:0; text-transform:none; letter-spacing:normal; }
.pj-i:hover { background:#FEC52E; color:#1c1a17; }
.ftip { position:relative; display:inline-flex; }
.ftip .ftip-box { visibility:hidden; opacity:0; transition:opacity .12s ease; position:absolute; top:150%; left:50%; transform:translateX(-50%); z-index:1000; width:320px; max-width:80vw; background:#1e293b; color:#e2e8f0; border:1px solid #334155; border-radius:8px; padding:10px 12px; font-size:12.5px; line-height:1.55; font-weight:400; white-space:normal; text-align:left; text-transform:none; letter-spacing:normal; box-shadow:0 8px 26px rgba(0,0,0,.4); pointer-events:none; }
.ftip:hover .ftip-box { visibility:visible; opacity:1; }
.ftip-box b { color:#FEC52E; }
.kpi-value { color: #FEC52E; font-size: 21px; font-weight: 700; line-height: 1.1; }
.kpi-sub   { color: #64748b; font-size: 10px; margin-top: 3px; }
.kpi-grp   { color: #FEC52E; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; margin: 16px 0 4px; border-bottom: 1px solid #272420; padding-bottom: 3px; }
.kpi-grp span { color: #64748b; font-weight: 400; text-transform: none; letter-spacing: 0; font-size: 11px; margin-left: 6px; }

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
/* Grey out weekend days in Streamlit date picker calendar */
[data-baseweb="calendar"] button[aria-label*="Saturday"],
[data-baseweb="calendar"] button[aria-label*="Sunday"],
[data-baseweb="calendar"] [role="gridcell"]:first-child button,
[data-baseweb="calendar"] [role="gridcell"]:last-child button{
    opacity:.25!important;pointer-events:none!important;cursor:not-allowed!important}
/* esconde o "Press Enter to apply" abaixo dos text_input (login + 🔒 do heatmap) */
[data-testid="InputInstructions"]{display:none!important}
/* esconde a toolbar do Streamlit no canto superior direito (Share/GitHub/menu ⋮) */
[data-testid="stToolbar"]{display:none!important}
[data-testid="stToolbarActions"]{display:none!important}
[data-testid="stDecoration"]{display:none!important}
[data-testid="stStatusWidget"]{display:none!important}
#MainMenu{display:none!important}
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
_COOKIE_MAX_AGE       = 21_600  # 6h — expiração por inatividade
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
        _svg_inline = _SVG_Z.replace("margin:0 auto 4px", "margin:0 0 5px")
        st.markdown(
            f'<div style="text-align:center;margin:56px 0 28px">'
            f'<div style="display:flex;align-items:flex-end;justify-content:center;gap:10px;margin-bottom:4px">'
            f'{_svg_inline}'
            f'<div style="font-size:32px;font-weight:700;line-height:1;color:#e2e8f0;letter-spacing:-0.5px">ileads</div>'
            f'</div>'
            f'<div style="font-size:13px;color:#475569">Dashboard de Leads</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        with st.form("login_form", border=False):
            email_in = st.text_input("E-mail", placeholder="seu@zilicred.com.br")
            senha_in = st.text_input("Senha", type="password")
            entrar   = st.form_submit_button("Entrar", width='stretch', type="primary")

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
                        "_login_via":   "senha",
                    })
                    st.rerun()
                else:
                    attempt["count"] = attempt.get("count", 0) + 1
                    if attempt["count"] >= 3:
                        attempt["blocked_until"] = time.time() + 3600
                    _login_attempts[email_in] = attempt
                    st.error("E-mail ou senha incorretos.")

    st.stop()


# ── Admin & histórico de acessos ────────────────────────────────────────────────
# Papel de administrador + registro/consulta de acessos. Os acessos são gravados no
# repositório PRIVADO (leads-sworks-data, o mesmo dos JSONs diários), em acessos/YYYYMMDD.json,
# usando o token de st.secrets["github"] — nunca ficam no repositório público.

_ACESSOS_DIR = "acessos"   # pasta no repo privado


def _is_admin_user(email: str) -> bool:
    """True somente se o bloco do usuário em st.secrets["auth"]["users"] tiver `admin = true`.
    O papel de admin vive APENAS no secrets do Streamlit — nunca no repositório público,
    então o código não revela quem é (ou não) administrador."""
    if not email:
        return False
    u = _find_user(email)
    return bool(u and u.get("admin"))


_ORG_POR_DOMINIO = {
    "zilicred.com.br":  "Zili",
    "xpi.com.br":       "XP",
    "xpprivate.com":    "XP",
    "poligono.com":     "Polígono",
    "angaasset.com.br": "Angá",
}


def _user_org(email: str) -> str:
    """Categoria/empresa do usuário. Prioriza o campo `org` no secrets; senão infere pelo
    domínio do e-mail (domínio é informação pública, não sensível — pode ficar no código)."""
    if not email:
        return "—"
    u = _find_user(email) or {}
    if u.get("org"):
        return str(u["org"])
    dom = email.split("@")[-1].strip().lower()
    return _ORG_POR_DOMINIO.get(dom, "Outros")


def _gh_get_file(path: str):
    """(texto, sha) do arquivo no repo privado; (None, None) se não existir ou em erro."""
    url = f"https://api.github.com/repos/{_REPO}/contents/{path}"
    try:
        r = requests.get(url, headers=_HEADERS_JSON, timeout=15)
    except requests.RequestException:
        return None, None
    if r.status_code != 200:
        return None, None
    j = r.json()
    try:
        return base64.b64decode(j.get("content", "")).decode("utf-8"), j.get("sha")
    except Exception:
        return None, j.get("sha")


def _gh_put_file(path: str, content: str, message: str, sha=None) -> bool:
    """Cria/atualiza um arquivo no repo privado. sha obrigatório para atualizar."""
    url = f"https://api.github.com/repos/{_REPO}/contents/{path}"
    payload = {"message": message,
               "content": base64.b64encode(content.encode("utf-8")).decode("ascii")}
    if sha:
        payload["sha"] = sha
    try:
        r = requests.put(url, headers=_HEADERS_JSON, json=payload, timeout=20)
    except requests.RequestException:
        return None
    return r.status_code


# ── Aviso de manutenção (flag global no repo privado; admin liga/desliga) ────────
_MANUT_PATH = "manutencao.json"


@st.cache_data(ttl=60, show_spinner=False)
def _ler_manutencao() -> dict:
    """Lê o aviso de manutenção do repo privado. Cache 60s p/ propagar a todos os
    usuários sem custo por render; o admin que altera limpa o cache na hora."""
    content, _sha = _gh_get_file(_MANUT_PATH)
    if not content:
        return {"ativo": False, "mensagem": "", "desde": "", "por": ""}
    try:
        d = json.loads(content)
        return {"ativo": bool(d.get("ativo")), "mensagem": str(d.get("mensagem", "")),
                "desde": str(d.get("desde", "")), "por": str(d.get("por", ""))}
    except Exception:
        return {"ativo": False, "mensagem": "", "desde": "", "por": ""}


def _set_manutencao(ativo: bool, mensagem: str, por: str) -> bool:
    """Grava o aviso de manutenção (ação de admin). Retorna True em sucesso."""
    agora = datetime.utcnow() - timedelta(hours=3)   # BRT (Brasil sem horário de verão)
    d = {"ativo": bool(ativo), "mensagem": mensagem.strip(),
         "desde": agora.strftime("%Y-%m-%dT%H:%M:%S"), "por": por}
    _content, sha = _gh_get_file(_MANUT_PATH)
    code = _gh_put_file(_MANUT_PATH, json.dumps(d, ensure_ascii=False, indent=1),
                        f"manutencao: {'ativar' if ativo else 'desativar'} por {por}", sha=sha)
    return code in (200, 201)


def _registrar_acesso(email: str, nome: str, via: str = "cookie") -> None:
    """Anexa 1 evento de acesso ao arquivo do dia (acessos/YYYYMMDD.json) no repo privado.
    Robusto: retry em 409 (escrita concorrente) e NUNCA levanta exceção (não pode derrubar o login)."""
    try:
        agora = datetime.utcnow() - timedelta(hours=3)   # BRT (Brasil sem horário de verão)
        evento = {"ts": agora.strftime("%Y-%m-%dT%H:%M:%S"), "email": email, "nome": nome, "via": via}
        path = f"{_ACESSOS_DIR}/{agora.strftime('%Y%m%d')}.json"
        for _ in range(3):
            content, sha = _gh_get_file(path)
            try:
                eventos = json.loads(content) if content else []
                if not isinstance(eventos, list):
                    eventos = []
            except Exception:
                eventos = []
            eventos.append(evento)
            corpo = json.dumps(eventos, ensure_ascii=False, indent=1)
            code = _gh_put_file(path, corpo, f"acesso: {email} {evento['ts']}", sha)
            if code in (200, 201):
                return
            if code != 409:      # 403/rede/etc — repetir não resolve
                return
    except Exception:
        pass


def _listar_acessos_arquivos() -> list:
    """Nomes dos arquivos em acessos/ (YYYYMMDD.json), mais recentes primeiro."""
    url = f"https://api.github.com/repos/{_REPO}/contents/{_ACESSOS_DIR}"
    try:
        r = requests.get(url, headers=_HEADERS_JSON, timeout=15)
    except requests.RequestException:
        return []
    if r.status_code != 200:
        return []
    nomes = [it.get("name", "") for it in r.json()
             if isinstance(it, dict) and str(it.get("name", "")).endswith(".json")]
    return sorted(nomes, reverse=True)


@st.cache_data(ttl=120, show_spinner=False)
def _ler_acessos(max_dias: int = 90) -> list:
    """Eventos de acesso dos últimos `max_dias` arquivos-dia do repo privado, mais recentes 1º.
    Cache curto (2 min) para não refazer a leitura a cada rerun da página admin."""
    eventos = []
    for nome in _listar_acessos_arquivos()[:max_dias]:
        content, _ = _gh_get_file(f"{_ACESSOS_DIR}/{nome}")
        if not content:
            continue
        try:
            arr = json.loads(content)
            if isinstance(arr, list):
                eventos.extend(x for x in arr if isinstance(x, dict))
        except Exception:
            pass
    eventos.sort(key=lambda e: e.get("ts", ""), reverse=True)
    return eventos


def _pagina_acessos() -> None:
    """Página admin: histórico de acessos (só chamada quando o usuário é admin)."""
    st.markdown("<style>[data-testid='stHeader']{display:none!important}</style>", unsafe_allow_html=True)
    _cb, _ct = st.columns([0.5, 9], vertical_alignment="center")
    with _cb:
        if st.button("◂", key="acessos_voltar", help="Voltar ao dashboard", width='stretch'):
            try:
                del st.query_params["page"]
            except Exception:
                st.query_params.clear()
            st.rerun()
    with _ct:
        st.markdown(
            "<div style='font-size:22px;font-weight:700;color:#e2e8f0'>&#128274; Hist&#243;rico de Acessos</div>"
            "<div style='color:#64748b;font-size:12px'>Vis&#237;vel apenas para administradores &#183; "
            "registro no reposit&#243;rio privado</div>", unsafe_allow_html=True)

    if st.button("↻ Atualizar", key="acessos_refresh"):
        _ler_acessos.clear()

    with st.spinner("Carregando histórico do repositório privado…"):
        eventos = _ler_acessos()

    if not eventos:
        st.info("Nenhum acesso registrado ainda. Os registros começam a partir de agora, a cada login "
                "(pode levar um instante para o primeiro aparecer).")
        return

    def _fmt(ts: str) -> str:
        try:
            return datetime.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S").strftime("%d/%m/%Y %H:%M")
        except Exception:
            return str(ts)

    _emails = {e.get("email") for e in eventos}
    _orgs   = {_user_org(e.get("email", "")) for e in eventos}
    _c1, _c2, _c3, _c4 = st.columns(4)
    _c1.metric("Acessos registrados", _nbr(len(eventos)))
    _c2.metric("Usuários distintos", _nbr(len(_emails)))
    _c3.metric("Empresas", _nbr(len(_orgs)))
    _c4.metric("Último acesso", _fmt(eventos[0].get("ts", "")))

    # Resumo por empresa (categoria)
    _org_ag: dict = {}
    for e in eventos:
        o = _user_org(e.get("email", ""))
        a = _org_ag.setdefault(o, {"emails": set(), "n": 0})
        a["emails"].add(e.get("email", ""))
        a["n"] += 1
    _org_rows = sorted(
        [{"Empresa": o, "Usuários": len(a["emails"]), "Acessos": a["n"]} for o, a in _org_ag.items()],
        key=lambda r: -r["Acessos"])
    st.markdown("##### Por empresa")
    st.dataframe(_org_rows, width='stretch', hide_index=True)

    resumo: dict = {}
    for e in eventos:
        k = e.get("email", "?")
        r = resumo.setdefault(k, {"Usuário": e.get("nome", ""), "Empresa": _user_org(k),
                                  "E-mail": k, "Acessos": 0, "Último acesso": ""})
        r["Acessos"] += 1
        if e.get("ts", "") > r["Último acesso"]:
            r["Último acesso"] = e.get("ts", "")
        if e.get("nome"):
            r["Usuário"] = e.get("nome")
    resumo_rows = sorted(resumo.values(), key=lambda r: r["Último acesso"], reverse=True)
    for r in resumo_rows:
        r["Último acesso"] = _fmt(r["Último acesso"])

    st.markdown("##### Por usuário")
    st.dataframe(resumo_rows, width='stretch', hide_index=True)

    st.markdown("##### Acessos recentes")
    _det = [{"Data/hora": _fmt(e.get("ts", "")), "Usuário": e.get("nome", ""),
             "Empresa": _user_org(e.get("email", "")), "E-mail": e.get("email", ""),
             "Via": e.get("via", "")} for e in eventos[:500]]
    st.dataframe(_det, width='stretch', hide_index=True)
    st.caption(f"Mostrando os {len(_det)} acessos mais recentes · fonte: repositório privado (acessos/).")


# ── Constantes ────────────────────────────────────────────────────────────────

_STATUS_NOMES = {
    0: "Novo", 1: "Pendente", 2: "Em andamento", 3: "Aprovado",
    4: "Reprovado", 5: "Suspenso", 6: "Pendente Manual",
    7: "Pendente Falha", 8: "Cancelado",
    -1: "Em andamento (geral)",  # bucket sintético para donut quando filtro de origem ativo (agrega todos os não-terminais)
}
_STATUS_CORES = {
    3: "#22c55e", 4: "#ef4444", 5: "#f59e0b", 2: "#3b82f6",
    0: "#94a3b8", 7: "#a855f7", 8: "#64748b", 1: "#6366f1", 6: "#ec4899",
    -1: "#94a3b8",
}

# Tooltips (balãozinho no "i") por etapa da tabela de Projeção de Desembolso.
# Keyed pelo código do tipo (ts, o mesmo de _TIPO_LABEL_MAP).
_ETAPA_TOOLTIPS = {
    "BLOQUEIO_TEMPORARIO":       "São leads originados no leilão cujos perfis não são aderentes à proposta inicial enviada e que, por essa razão, devem aguardar 24h para receberem uma nova proposta, adequada aos seus perfis e não mais via leilão.",
    "PAGAMENTO":                 "São leads cujos perfis foram aprovados, já possuem CCB assinada e cujos tomadores estão apenas aguardando o recebimento do empréstimo via PIX.",
    "ASSINATURA":                "São leads cujos perfis foram aprovados pelo motor de crédito, cujas propostas enviadas foram aceitas e já cadastradas com sucesso, passaram pela formalização e atualização de dados, mas cujos tomadores ainda não assinaram a CCB gerada e enviada a eles.",
    "ASSINADO":                  "São leads cujos perfis foram aprovados pelo motor de crédito, cujas propostas enviadas foram aceitas e já cadastradas com sucesso, passaram pela formalização e atualização de dados, cujos tomadores já assinaram a CCB gerada e enviada a eles, mas houve alguma falha pós-assinatura, a ser investigada.",
    "ENTREVISTA":                "São leads cujos perfis foram aprovados pelo motor de crédito, cujas propostas enviadas foram aceitas e já cadastradas com sucesso, passaram pela formalização e atualização de dados, cujos tomadores já assinaram a CCB gerada e enviada a eles, mas não realizaram ainda a entrevista anti-fraude da Nuvidio.",
    "FORMALIZACAO":              "São leads cujos perfis foram aprovados pelo motor de crédito, cujas propostas enviadas foram aceitas e já cadastradas com sucesso, mas cujos tomadores ainda não deram o aceite na etapa de formalização para captura de dados de endereço e de pagamento.",
    "PRE_APROVADO":              "São leads cujos perfis foram aprovados pelo motor de crédito, mas cujas propostas iniciais, enviadas ao tomador, ainda não foram aceitas.",
    "SIMULACAO":                 "São leads cujos perfis foram aprovados pelo motor de crédito, mas cujas propostas iniciais não foram aceitas pelo tomador. Nesse contexto, foram simuladas e enviadas novas propostas que aguardam aceite dos tomadores.",
    "PENDENTE_DADOS_PAGAMENTO":  "São leads cujos perfis foram aprovados pelo motor de crédito, cujas propostas enviadas foram aceitas e já cadastradas com sucesso, passaram pela formalização e atualização de dados, cujos tomadores já assinaram a CCB gerada e enviada a eles, mas houve alguma pendência, relacionada aos dados de pagamento, na tentativa de realizar o desembolso, a ser investigada.",
    "AVERBACAO_PENDENTE_MANUAL": "São leads cujos perfis foram aprovados pelo motor de crédito, cujas propostas enviadas foram aceitas e já cadastradas com sucesso, passaram pela formalização e atualização de dados, cujos tomadores já assinaram a CCB gerada e enviada a eles, mas houve alguma falha na etapa de Averbação, a ser investigada.",
}

_ETAPAS_ANTES = frozenset({"Já Reprovado (reentrada)", "Validações Internas", "Validações Iniciais"})

# Conceitos de etapa de reprovação e o nome em cada workflow: (nome_v38, nome_v39).
# None = a etapa não existe naquele workflow. Os nomes do v39 seguem as caixas do
# próprio workflow v39 (RF PJ/PF, PH3A PJ/PF, Validações Iniciais…); o v38 mantém os
# rótulos legados. Cada workflow respeita o próprio nome; quando o período tem os dois
# e o conceito aparece nos dois, a coluna ETAPA mostra "nome_v38 | nome_v39".
_ETAPA_CONCEITOS = [
    ("Já Reprovado (reentrada)", None),
    ("Validações Internas",      "Validações Iniciais"),
    ("Consulta Dataprev",        "Consulta Dataprev"),
    ("Receita Federal PJ",       "RF PJ"),
    ("Receita Federal PF",       "RF PF"),
    ("SCR",                      "SCR"),
    (None,                       "BigDataCorp (PJ)"),
    (None,                       "BigDataCorp (PF)"),
    ("Análise PH3A (PJ)",        "PH3A PJ"),
    ("Análise PH3A (PF)",        "PH3A PF"),
    ("Cálculo de Proposta",      "Cálculo de Proposta"),
    ("Cadastro Proposta",        "Cadastro Proposta"),
    ("Envia CCB Único",          "Envia CCB Único"),
    ("Averbação",                "Averbação"),
    ("A identificar",            "A identificar"),
]
# Ordem default (todos os nomes, na ordem dos conceitos) p/ quem não combina (ex.: TV).
_ETAPA_WORKFLOW_ORDER = [n for c in _ETAPA_CONCEITOS for n in c if n]


def _combinar_etapas_conceito(etapas: dict, etapa_motivos: dict):
    """Agrupa as etapas por CONCEITO. O rótulo de cada conceito é a junção por ' | '
    dos nomes (v38 e v39) que TÊM leads no período — assim período de um só workflow
    mostra só o nome dele, e período misto mostra 'nome_v38 | nome_v39'. As contagens
    e os motivos dos dois nomes são somados no mesmo conceito.
    Retorna (etapas_comb, etapa_motivos_comb, ordem_comb)."""
    etapas_c: dict = {}
    motivos_c: dict = {}
    ordem_c: list = []
    mapeados: set = set()
    for n38, n39 in _ETAPA_CONCEITOS:
        nomes = []
        for nm in (n38, n39):
            if nm:
                mapeados.add(nm)
                if nm not in nomes and etapas.get(nm, 0) > 0:
                    nomes.append(nm)
        if not nomes:
            continue
        label = " | ".join(nomes)
        etapas_c[label] = sum(etapas.get(nm, 0) for nm in nomes)
        mm: dict = {}
        for nm in nomes:
            for mot, c in (etapa_motivos.get(nm) or {}).items():
                mm[mot] = mm.get(mot, 0) + c
        if mm:
            motivos_c[label] = mm
        ordem_c.append(label)
    # Etapas fora do mapa de conceitos (defensivo) → mantém o nome cru, ao fim.
    for nm, c in etapas.items():
        if nm not in mapeados and c > 0:
            etapas_c[nm] = etapas_c.get(nm, 0) + c
            if etapa_motivos.get(nm):
                motivos_c[nm] = dict(etapa_motivos[nm])
            if nm not in ordem_c:
                ordem_c.append(nm)
    return etapas_c, motivos_c, ordem_c

_TEMPLATE = "plotly_dark"
_CONF     = {"displayModeBar": False, "responsive": True}
_GRID     = "rgba(255,255,255,0.06)"
_BG       = "rgba(0,0,0,0)"
_TF       = dict(size=15, color="#FEC52E")
_AF       = dict(size=13, color="#94a3b8")

_TV_N_SLIDES   = 24
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


# Dias recentes (últimos _DIAS_MUTAVEIS) ainda mudam — o coletor atualiza hoje + retro
# e publica ~8 dias — então usam TTL curto. Dias mais antigos são congelados (nunca mais
# mudam) → cache permanente: baixam 1x e reusam pela vida do app (compartilhado entre
# sessões). Isso elimina o "Running carregar_dia" nas interações repetidas.
_DIAS_MUTAVEIS = 8
# Versão do modelo de dados dos JSONs diários. BUMP quando re-exportar dias históricos
# (novos campos em desembolsos_detalhe etc.) — muda a chave do cache e força re-fetch,
# sem depender do processo reiniciar. Histórico ganha TTL de 12h como rede de segurança
# (auto-heal), mantendo a performance dentro da sessão.
_DATA_VER = "2026-08-04-status-fix"


def _fetch_dia(dia_str: str) -> dict:
    url = f"https://api.github.com/repos/{_REPO}/contents/dados/{dia_str}.json"
    r = requests.get(url, headers=_HEADERS_RAW, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"GitHub API retornou {r.status_code}")
    return json.loads(r.text)


@st.cache_data(ttl=1800, max_entries=30)   # recentes: 30 min (coletor publica a cada ~30 min)
def _carregar_dia_recente(dia_str: str, _ver: str = "") -> dict:
    return _fetch_dia(dia_str)


@st.cache_data(ttl=43200, max_entries=400)  # históricos: TTL 12h (auto-heal) + _ver p/ bust
def _carregar_dia_hist(dia_str: str, _ver: str = "") -> dict:
    return _fetch_dia(dia_str)


def carregar_dia(dia_str: str) -> dict:
    # BRT (Brasil sem horário de verão desde 2019). Comparação lexicográfica de "YYYYMMDD"
    # = cronológica. Dia dentro da janela mutável → cache curto; senão → 12h + versão.
    _limite = (datetime.utcnow() - timedelta(hours=3) - timedelta(days=_DIAS_MUTAVEIS)).strftime("%Y%m%d")
    return (_carregar_dia_recente(dia_str, _DATA_VER) if dia_str >= _limite
            else _carregar_dia_hist(dia_str, _DATA_VER))


@st.cache_data(ttl=1800, show_spinner=False)
def _carregar_referencia() -> dict:
    """Referência de anomalia do heatmap (heatmap_ref/referencia.json no repo privado).
    Estrutura: ref[etapa][faixa_idx][classe util|fds][hora] = {n, med, mad, p10, p90, ...}.
    Retorna {} se ausente/erro (o heatmap então não sinaliza nada)."""
    url = f"https://api.github.com/repos/{_REPO}/contents/heatmap_ref/referencia.json"
    try:
        r = requests.get(url, headers=_HEADERS_RAW, timeout=15)
        if r.status_code != 200:
            return {}
        return json.loads(r.text)
    except Exception:
        return {}

# ── Agregacao ─────────────────────────────────────────────────────────────────

def _merge_segmentos(segs: list) -> dict:
    """Combina segmentos por-origem (mesma forma dos campos globais do JSON) em um
    único dict com a MESMA forma que `agregar` lê por dia. Usado para reconstruir um
    dia filtrado somando apenas as origens selecionadas."""
    _flat = ["taxa_dist", "prazo_dist", "etapas", "bloqueios", "top_motivos", "top_motivos_det",
             "top_empregadores", "top_cbos", "top_empregadores_rep", "top_cnaes",
             "top_cbos_rep", "top_ufs"]
    out: dict = {f: {} for f in _flat}
    out["etapa_motivos"] = {}
    out["emp_motivos"] = {}
    out["emp_motivos_leads"] = {}
    out["emp_ap_stats"] = {}
    out["evolucao_diaria"] = {}
    out["evolucao_horaria"] = {}
    out["valores_contratacao"] = []
    out["bloqueados_total"] = 0
    _fin: dict = {}
    for seg in segs:
        for f in _flat:
            for k, v in seg.get(f, {}).items():
                out[f][k] = out[f].get(k, 0) + v
        out["valores_contratacao"].extend(seg.get("valores_contratacao", []))
        out["bloqueados_total"] += seg.get("bloqueados_total", 0)
        for etapa, mots in seg.get("etapa_motivos", {}).items():
            dst = out["etapa_motivos"].setdefault(etapa, {})
            for lbl, cnt in mots.items():
                dst[lbl] = dst.get(lbl, 0) + cnt
        for _ev in ("evolucao_diaria", "evolucao_horaria"):
            for _k, _sm in seg.get(_ev, {}).items():
                _dst = out[_ev].setdefault(_k, {})
                for _sk, _cnt in _sm.items():
                    _dst[_sk] = _dst.get(_sk, 0) + _cnt
        for emp, mots in seg.get("emp_motivos", {}).items():
            dst = out["emp_motivos"].setdefault(emp, {})
            for lbl, cnt in mots.items():
                dst[lbl] = dst.get(lbl, 0) + cnt
        for emp, mots in seg.get("emp_motivos_leads", {}).items():
            dst = out["emp_motivos_leads"].setdefault(emp, {})
            for lbl, cods in mots.items():
                dst.setdefault(lbl, []).extend(cods)
        for campo, s in seg.get("financeiro", {}).items():
            n = s.get("n", 0)
            if n <= 0:
                continue
            fd = _fin.setdefault(campo, {"n": 0, "total": 0.0, "_med_sum": 0.0,
                                         "min": float("inf"), "max": float("-inf")})
            fd["n"]       += n
            fd["total"]   += s.get("total", 0.0)
            fd["_med_sum"] += s.get("mediana", 0.0) * n
            fd["min"] = min(fd["min"], s.get("min", float("inf")))
            fd["max"] = max(fd["max"], s.get("max", float("-inf")))
            if "weighted_sum" in s:
                fd["weighted_sum"] = fd.get("weighted_sum", 0.0) + s["weighted_sum"]
                fd["weight_sum"]   = fd.get("weight_sum", 0.0) + s["weight_sum"]
        for emp, s in seg.get("emp_ap_stats", {}).items():
            ed = out["emp_ap_stats"].setdefault(emp, {
                "n": 0, "n_tempo": 0, "sum_tempo": 0.0, "n_renda": 0, "sum_renda": 0.0,
                "n_valor": 0, "sum_valor": 0.0, "n_prazo": 0, "sum_prazo": 0.0,
                "n_taxa": 0, "sum_taxa": 0.0, "sum_taxa_prazo": 0.0, "weight_prazo_taxa": 0.0,
                "num_funcionarios": None,
                "faturamento": None, "dividas_ativas": None, "capital_social": None})
            ed["n"] += s.get("n", 0)
            for c in ("tempo", "renda", "valor", "prazo", "taxa"):
                ed[f"n_{c}"]   += s.get(f"n_{c}", 0)
                ed[f"sum_{c}"] += s.get(f"sum_{c}", 0.0)
            ed["sum_taxa_prazo"]    += s.get("sum_taxa_prazo", 0.0)
            ed["weight_prazo_taxa"] += s.get("weight_prazo_taxa", 0.0)
            for pj in ("num_funcionarios", "faturamento", "dividas_ativas", "capital_social"):
                if ed[pj] is None and s.get(pj) is not None:
                    ed[pj] = s[pj]
    # finaliza financeiro na forma que `agregar` lê por dia (n/total/mediana/min/max[/weighted])
    fin_out: dict = {}
    for campo, fd in _fin.items():
        n = fd["n"]
        item = {"n": n, "total": fd["total"],
                "mediana": (fd["_med_sum"] / n) if n else 0.0,
                "min": fd["min"], "max": fd["max"]}
        if "weight_sum" in fd:
            item["weighted_sum"] = fd["weighted_sum"]
            item["weight_sum"]   = fd["weight_sum"]
        fin_out[campo] = item
    out["financeiro"] = fin_out
    return out


def _info_i(_inner: str) -> str:
    """Ícone '?' (pj-i) + balão estilizado (.ftip). `_inner` deve ser HTML já pronto
    (use <br> p/ quebras e <b> p/ negrito). Padrão dos tooltips de informação do Zileads."""
    return (f'<span class="ftip"><span class="pj-i">?</span>'
            f'<span class="ftip-box">{_inner}</span></span>')


def _apply_origem(d: dict, origens) -> dict:
    """Cópia rasa do dia com os campos segmentáveis substituídos pela soma das origens
    selecionadas (de d['por_origem']). Campos fora do segmento (funil, evolucao,
    projecao, desembolsos, funil_por_origem, etc.) permanecem globais. Não muta `d`
    (que vem do cache de carregar_dia)."""
    po = d.get("por_origem")
    if not po:
        # Dia sem 'por_origem' (JSON pré-mudança — só num skew transitório entre os
        # repos): mantém os valores GLOBAIS do dia em vez de zerar as seções 8–13.
        # (Se 'por_origem' existe mas a origem selecionada não teve leads no dia, o
        # merge retorna vazio e o dia contribui 0 — que é o correto.)
        return d
    merged = _merge_segmentos([po[o] for o in origens if o in po])
    d2 = dict(d)
    d2.update(merged)
    return d2


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
    emp_motivos_leads = defaultdict(lambda: defaultdict(list))
    novo_ctps     = defaultdict(int)
    funil_orig_acc: dict = {}
    origens_all: set = set()
    emp_ap_stats_raw: dict = {}
    taxa_dist: dict = {}
    prazo_dist: dict = {}
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
    bloqueados_total_ag = 0
    workflows_set: set = set()
    natureza_leads: dict = defaultdict(int)
    for d in dias_raw:
        # Versões de workflow presentes no período (dias sem o campo = histórico v38).
        workflows_set.update(d.get("workflows") or ["v38"])
        for _nk, _nv in (d.get("natureza_leads") or {}).items():
            natureza_leads[_nk] += _nv
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
        for emp, mots in d.get("emp_motivos_leads", {}).items():
            for label, cods in mots.items():
                emp_motivos_leads[emp][label].extend(cods)

        for k, v in d.get("novo_ctps_status", {}).items():
            novo_ctps[k] += v

        for _orig, _ov in d.get("funil_por_origem", {}).items():
            if _orig not in funil_orig_acc:
                funil_orig_acc[_orig] = {"total": 0, "novos": 0, "aprovados": 0, "reprovados": 0, "cancelados": 0, "em_curso": 0}
            for _k in ("total", "novos", "aprovados", "reprovados", "cancelados", "em_curso"):
                funil_orig_acc[_orig][_k] += _ov.get(_k, 0)
        origens_all.update(d.get("origens", []))

        for emp, s in d.get("emp_ap_stats", {}).items():
            if emp not in emp_ap_stats_raw:
                emp_ap_stats_raw[emp] = {
                    "n_tempo": 0, "sum_tempo": 0.0,
                    "n_renda": 0, "sum_renda": 0.0,
                    "n_valor": 0, "sum_valor": 0.0,
                    "n_prazo": 0, "sum_prazo": 0.0,
                    "n_taxa":  0, "sum_taxa":  0.0,
                    "sum_taxa_prazo": 0.0, "weight_prazo_taxa": 0.0,
                    "num_funcionarios": None, "faturamento": None,
                    "dividas_ativas":   None, "capital_social": None,
                }
            a = emp_ap_stats_raw[emp]
            for _c in ("tempo", "renda", "valor", "prazo", "taxa"):
                a[f"n_{_c}"]   += s.get(f"n_{_c}", 0)
                a[f"sum_{_c}"] += s.get(f"sum_{_c}", 0.0)
            a["sum_taxa_prazo"]    += s.get("sum_taxa_prazo", 0.0)
            a["weight_prazo_taxa"] += s.get("weight_prazo_taxa", 0.0)
            for _pj in ("num_funcionarios", "faturamento", "dividas_ativas", "capital_social"):
                if a[_pj] is None and s.get(_pj) is not None:
                    a[_pj] = s[_pj]

        if d.get("taxa_dist"):
            for _tk, _cnt in d["taxa_dist"].items():
                taxa_dist[_tk] = taxa_dist.get(_tk, 0) + _cnt
        else:
            for _s in d.get("emp_ap_stats", {}).values():
                _nt = _s.get("n_taxa", 0)
                _st = _s.get("sum_taxa", 0.0)
                if _nt and _st:
                    _tk = f"{_st / _nt:.2f}"
                    taxa_dist[_tk] = taxa_dist.get(_tk, 0) + _nt

        for _pk, _pcnt in (d.get("prazo_dist") or {}).items():
            prazo_dist[_pk] = prazo_dist.get(_pk, 0) + _pcnt

        valores_cont.extend(d.get("valores_contratacao", []))
        aguardando          += d.get("aguardando", 0)
        aguardando_valor    += d.get("aguardando_valor", 0.0)
        aguardando_liberado += d.get("aguardando_liberado", 0.0)
        aguardando_iof      += d.get("aguardando_iof", 0.0)
        assinado            += d.get("assinado", 0)
        assinado_valor      += d.get("assinado_valor", 0.0)
        assinado_liberado   += d.get("assinado_liberado", 0.0)
        assinado_iof        += d.get("assinado_iof", 0.0)
        bloqueados_total_ag += d.get("bloqueados_total", 0)
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
        "novos":           d_status.get(0, 0),
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
            "media_taxa":  (_a["sum_taxa_prazo"] / _a["weight_prazo_taxa"]) if _a.get("weight_prazo_taxa")
                           else (_a["sum_taxa"] / _a["n_taxa"] if _a["n_taxa"] else None),
            "n_taxa":      _a["n_taxa"],
            "num_funcionarios": _a["num_funcionarios"],
            "faturamento":      _a["faturamento"],
            "dividas_ativas":   _a["dividas_ativas"],
            "capital_social":   _a["capital_social"],
        }

    return {
        "funil":             funil,
        "workflows":         sorted(workflows_set) or ["v38"],
        "natureza_leads":    dict(natureza_leads),
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
        "bloqueados_total":  bloqueados_total_ag,
        "etapas":            dict(etapas),
        "etapa_motivos":     {e: dict(m) for e, m in etapa_motivos.items()},
        "emp_motivos":       {emp: dict(sorted(mots.items(), key=lambda x: -x[1])[:15]) for emp, mots in emp_motivos.items()},
        "emp_motivos_leads": {emp: dict(m) for emp, m in emp_motivos_leads.items()},
        "emp_ap_stats":      emp_ap_stats_final,
        "taxa_dist":         taxa_dist,
        "prazo_dist":        prazo_dist,
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
        "funil_por_origem":     dict(funil_orig_acc),
        "origens":              sorted(origens_all),
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
        legend=dict(
            font=dict(size=13, color="#94a3b8"),
            bgcolor="rgba(13,12,10,0.85)",
            bordercolor="rgba(255,255,255,0.10)", borderwidth=1,
            orientation="v",
            x=0.60, y=0.50,
            xanchor="left", yanchor="middle",
        ),
        margin=dict(t=10, b=10, l=10, r=200), height=360,
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


def _fig_evolucao(agg: dict, n_dias: int, dias_raw: list = None, datas_sel: list = None,
                  statuses_sel: list = None):
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
    _sel_status = set([3, 4, 5, 2, 0, 7, 8, 1, 6] if statuses_sel is None else statuses_sel)
    _mostra_total = "TOTAL" in _sel_status
    for s in [3, 4, 5, 2, 0, 7, 8, 1, 6]:
        if s not in _sel_status:
            continue
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
    if _mostra_total:
        y_tot = [sum(ev.get(x, {}).values()) for x in eixo]
        if sum(y_tot) > 0:
            fig.add_trace(go.Scatter(
                x=eixo, y=y_tot,
                name="Total",
                mode=trace_mode,
                line=dict(color="#e2e8f0", width=2.5, dash="dot"),
                marker=dict(size=4),
                hovertemplate="Total: %{y:,}<extra></extra>",
            ))
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text=titulo, font=_TF),
        xaxis=dict(title=xlab, tickfont=_AF, showgrid=True, gridcolor=_GRID, **xaxis_extra),
        yaxis=dict(title="Leads", tickfont=_AF, showgrid=True, gridcolor=_GRID),
        legend=dict(font=dict(size=10, color="#94a3b8"), bgcolor=_BG,
                    orientation="h", y=-0.38, x=0.5, xanchor="center"),
        margin=dict(t=50, b=110, l=10, r=10), height=400,
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
                  show_abs: bool = False, show_pct: bool = True, text_auto: bool = False):
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
        tpos   = "auto" if text_auto else "outside"   # % sempre horizontal, fora da barra
    else:
        shades = color
        texts  = [f"{_nbr(v)}" for v in values]
        tpos   = "outside"
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker=dict(color=shades, line=dict(color="#0d0c0a", width=0.5)),
        text=texts, textposition=tpos,
        insidetextanchor="end" if (pct_base and text_auto) else None,
        cliponaxis=False,   # não corta o rótulo que cai fora da barra (à direita)
        textfont=dict(size=13, color="rgba(255,255,255,0.85)" if (pct_base and text_auto) else "#94a3b8"),
        hovertemplate="%{y}: <b>%{x:,}</b><extra></extra>",
    ))
    h = max(280, len(items) * 34 + 80)
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text=titulo, font=_TF),
        xaxis=dict(tickfont=_AF, showgrid=True, gridcolor=_GRID, zeroline=False),
        yaxis=dict(tickfont=dict(size=13, color="#cbd5e1"), autorange="reversed", automargin=True),
        margin=dict(t=50, b=20, l=20, r=110 if text_auto else (90 if pct_base else 60)), height=h,
    )
    return fig


def _fig_dist_prazo(prazo_dict: dict, titulo: str):
    """Barras VERTICAIS da distribuição de nº de parcelas ({prazo: contagem}),
    ordenadas por prazo crescente (12, 24, 36, 48, …). y = contratos; rótulo = % do total.
    Vertical (e não horizontal como a de taxa) porque há muitos prazos distintos: a ordem
    numérica no eixo X evidencia os picos em 12/24/36/48 sem cortar nenhum valor."""
    if not prazo_dict:
        return None
    _itens = sorted(((int(float(k)), v) for k, v in prazo_dict.items()), key=lambda x: x[0])
    _tot = sum(v for _, v in _itens)
    if not _tot:
        return None
    _xs  = [str(k) for k, _ in _itens]
    _ys  = [v for _, v in _itens]
    _pct = [100.0 * v / _tot for v in _ys]
    _txt = [f"{p:.0f}%" if p >= 3 else "" for p in _pct]   # rotula só barras ≥3% (evita poluir)
    _mx  = max(_ys)
    _shades = [f"rgba(96,165,250,{0.40 + 0.55*(v/_mx):.2f})" for v in _ys]
    fig = go.Figure(go.Bar(
        x=_xs, y=_ys, customdata=_pct,
        marker=dict(color=_shades, line=dict(color="#0d0c0a", width=0.5)),
        text=_txt, textposition="outside", textfont=dict(size=12, color="#cbd5e1"),
        cliponaxis=False,
        hovertemplate="%{x} parcelas: <b>%{y:,}</b> contrato(s) · %{customdata:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text=titulo, font=_TF),
        xaxis=dict(title="Número de parcelas", type="category", tickfont=_AF,
                   showgrid=False, zeroline=False),
        yaxis=dict(title="Contratos", tickfont=_AF, showgrid=True, gridcolor=_GRID, zeroline=False),
        margin=dict(t=50, b=45, l=10, r=10), height=360,
    )
    return fig


def _fig_barras_v(pairs, titulo: str, x_title: str = "", y_title: str = "Contratos"):
    """Barras VERTICAIS a partir de pares ORDENADOS (label, valor). y = valor; rótulo = %
    do total nas barras ≥3%. Genérico (faixas etárias, etc.); preserva a ordem dada."""
    _pares = [(str(_l), _v) for _l, _v in pairs if _v]
    if not _pares:
        return None
    _tot = sum(_v for _, _v in _pares)
    if not _tot:
        return None
    _xs  = [_l for _l, _ in _pares]
    _ys  = [_v for _, _v in _pares]
    _pct = [100.0 * _v / _tot for _v in _ys]
    _txt = [f"{_p:.0f}%" if _p >= 3 else "" for _p in _pct]
    _mx  = max(_ys)
    _shades = [f"rgba(96,165,250,{0.40 + 0.55*(_v/_mx):.2f})" for _v in _ys]
    fig = go.Figure(go.Bar(
        x=_xs, y=_ys, customdata=_pct,
        marker=dict(color=_shades, line=dict(color="#0d0c0a", width=0.5)),
        text=_txt, textposition="outside", textfont=dict(size=12, color="#cbd5e1"),
        cliponaxis=False,
        hovertemplate="%{x}: <b>%{y:,}</b> · %{customdata:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        title=dict(text=titulo, font=_TF),
        xaxis=dict(title=x_title, type="category", tickfont=_AF, showgrid=False, zeroline=False),
        yaxis=dict(title=y_title, tickfont=_AF, showgrid=True, gridcolor=_GRID, zeroline=False),
        margin=dict(t=50, b=45, l=10, r=10), height=340,
    )
    return fig


def _fig_barras_reais(data_dict: dict, titulo: str, hex_color: str, n: int = 12):
    """Barras horizontais com rótulos em R$. data_dict = {label: valor_float} (ordem desc)."""
    items = [(k, v) for k, v in data_dict.items() if v][:n]
    if not items:
        return None
    labels = [k for k, _ in items]
    values = [round(v, 2) for _, v in items]
    max_v  = max(values) if values else 1
    _h = hex_color.lstrip("#")
    _r, _g, _b = (int(_h[i:i + 2], 16) for i in (0, 2, 4))
    shades = [f"rgba({_r},{_g},{_b},{0.40 + 0.55 * (v / max_v):.2f})" for v in values]
    texts  = ["R$ " + f"{v:,.0f}".replace(",", ".") for v in values]
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker=dict(color=shades, line=dict(color="#0d0c0a", width=0.5)),
        text=texts, textposition="outside",
        textfont=dict(size=13, color="#94a3b8"),
        hovertemplate="%{y}: <b>R$ %{x:,.2f}</b><extra></extra>",
    ))
    h = max(280, len(items) * 34 + 80)
    fig.update_layout(
        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
        separators=",.",  # BR: vírgula decimal, ponto de milhar (alinha eixo/hover aos rótulos)
        title=dict(text=titulo, font=_TF),
        xaxis=dict(tickfont=_AF, showgrid=True, gridcolor=_GRID, zeroline=False,
                   tickprefix="R$ ", tickformat=",.0f"),
        yaxis=dict(tickfont=dict(size=13, color="#cbd5e1"), autorange="reversed", automargin=True),
        margin=dict(t=50, b=20, l=20, r=100), height=h,
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


def _fig_funil_etapa(etapas: dict, n_rep: int, order: list = None):
    if not etapas or n_rep == 0:
        return None
    _order_idx = {e: i for i, e in enumerate(order or _ETAPA_WORKFLOW_ORDER)}
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


def _fig_bloqueios(bloqueios: dict, n_bloq: int = 0):
    if not any(bloqueios.values()):
        return None
    nomes = {"cpf": "CPF Bloqueado", "cnpj": "CNPJ Bloqueado",
             "cnae": "CNAE Bloqueado", "cbo": "CBO Bloqueado"}
    cores = {"cpf": "#f87171", "cnpj": "#fb923c", "cnae": "#a78bfa", "cbo": "#60a5fa"}
    labels = [nomes.get(k, k) for k, v in bloqueios.items() if v > 0]
    values = [v for v in bloqueios.values() if v > 0]
    # % sobre os leads DISTINTOS com >=1 bloqueio (n_bloq). Fallback p/ JSONs antigos sem
    # o campo: soma dos valores (% somam 100%). Com n_bloq, os % somam >100% quando há
    # leads com mais de um tipo de bloqueio.
    _denom = n_bloq if n_bloq else sum(values)
    pcts   = [100*v/_denom if _denom else 0 for v in values]
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
        title=dict(text="Leads com Bloqueio por Tipo<br><sup>% sobre leads com ≥1 bloqueio</sup>", font=_TF),
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


def _html_tabela_desemb(items: list, titulo_col: str, n_total: int,
                        code_col_title: str = "", n: int = 15) -> str:
    """Ranking de desembolsados: #, [código,] nome, Contratos, %, Contratado (R$), Liberado (R$).
    items: lista de dicts {label, n, valor, liberado} já ordenada."""
    if not items:
        return ""
    _SEP = " — "
    _items = items[:n]
    has_sep = bool(code_col_title) and any(_SEP in str(it.get("label", "")) for it in _items[:5])

    def _brl(v):
        return ("R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if v else "—"

    rows_html = []
    for i, it in enumerate(_items):
        rc  = "g0" if i % 2 == 0 else "g1"
        lbl = str(it.get("label", "") or "")
        pct = f"{100 * it['n'] / n_total:.1f}%" if n_total else "—"
        if has_sep and _SEP in lbl:
            code, desc = lbl.split(_SEP, 1)
            name_cells = (f'<td style="color:#94a3b8;white-space:nowrap">{code}</td>'
                          f'<td class="wrap">{desc}</td>')
        elif has_sep:
            name_cells = f'<td style="color:#64748b">—</td><td class="wrap">{lbl or "—"}</td>'
        else:
            name_cells = f'<td class="wrap">{lbl or "—"}</td>'
        rows_html.append(
            f'<tr class="{rc}">'
            f'<td class="c" style="color:#64748b;width:28px">{i + 1}</td>'
            f'{name_cells}'
            f'<td class="r">{_nbr(it["n"])}</td>'
            f'<td class="r" style="color:#94a3b8">{pct}</td>'
            f'<td class="r" style="color:#FEC52E">{_brl(it.get("valor", 0.0))}</td>'
            f'<td class="r" style="color:#FEC52E">{_brl(it.get("liberado", 0.0))}</td>'
            f'</tr>'
        )
    if has_sep:
        thead = (f'<thead><tr><th class="c">#</th><th>{code_col_title}</th><th>{titulo_col}</th>'
                 '<th class="r">Contratos</th><th class="r">%</th>'
                 '<th class="r">Contratado</th><th class="r">Liberado</th></tr></thead>')
    else:
        thead = (f'<thead><tr><th class="c">#</th><th>{titulo_col}</th>'
                 '<th class="r">Contratos</th><th class="r">%</th>'
                 '<th class="r">Contratado</th><th class="r">Liberado</th></tr></thead>')
    return ('<div class="dtbl-wrap"><table class="dtbl">' + thead
            + '<tbody>' + "".join(rows_html) + '</tbody></table></div>')


def _html_emp_rep_expandable(emp_rep: dict, emp_mot: dict, emp_mot_leads: dict, n_rep: int, n: int = 15) -> str:
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
            _leads_by_mot = emp_mot_leads.get(emp, {})
            _CAP_LK = 200
            _mrows_list = []
            for lbl, v in sorted(mots.items(), key=lambda x: -x[1]):
                _cods = _leads_by_mot.get(lbl, [])
                if _cods:
                    _links = "".join(
                        f'<a href="https://sworks.zilicorp.net/Processo?codigo={_c}" target="_blank" '
                        f'style="color:#60a5fa;text-decoration:none;margin-right:8px;white-space:nowrap">{_c}</a>'
                        for _c in _cods[:_CAP_LK]
                    )
                    _extra = f'<span style="color:#64748b"> +{len(_cods)-_CAP_LK} mais</span>' if len(_cods) > _CAP_LK else ""
                    _mot_cell = (
                        f'<details style="cursor:pointer">'
                        f'<summary style="list-style:none;display:flex;align-items:center;gap:5px">'
                        f'<span style="font-size:8px;color:#475569">▶</span><span>{lbl}</span></summary>'
                        f'<div style="margin:3px 0 4px 12px;line-height:1.9;font-size:0.9em">'
                        f'<span style="color:#64748b;margin-right:8px">Links S-works:</span>{_links}{_extra}</div>'
                        f'</details>'
                    )
                else:
                    _mot_cell = lbl
                _mrows_list.append(
                    f'<tr>'
                    f'<td style="font-size:0.78em;color:#94a3b8;padding:2px 8px 2px 0;word-break:break-word;vertical-align:top">{_mot_cell}</td>'
                    f'<td style="font-size:0.78em;color:#e2e8f0;font-weight:600;text-align:right;white-space:nowrap;padding:2px 0;vertical-align:top">{v/total_emp*100:.1f}%</td>'
                    f'<td style="font-size:0.78em;color:#64748b;text-align:right;padding:2px 0 2px 10px;vertical-align:top">{v}</td>'
                    f'</tr>'
                )
            mrows = "".join(_mrows_list)
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
            + _row("Número de Parcelas", f"{st['media_prazo']:.0f}" if st.get("media_prazo") else "—")
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
        ("Dataprev",         ["Consulta Dataprev"]),
        ("RF PJ",            ["Receita Federal PJ"]),
        ("RF PF",            ["Receita Federal PF"]),
        ("SCR",              ["SCR"]),
        ("BDC PJ",           ["BigDataCorp (PJ)"]),
        ("BDC PF",           ["BigDataCorp (PF)"]),
        ("PH3A PJ",          ["Análise PH3A (PJ)"]),
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


def _html_wf166_flow(nivel: str = "root") -> str:
    """HTML (st.markdown) do fluxo de UM nível do Workflow 166 — drill-down por clique.

    A caixa 'Motor de Crédito' é um link (?wf166=motor) — clicar entra nela; dentro,
    uma setinha ◂ pequena (?wf166=root) volta. Só o nível atual aparece. Renderiza via
    st.markdown (links de query-param; o components.html/iframe vinha vazio neste deploy)."""
    fases = [
        "Inicializa Dados", "Motor de Crédito", "Cálculo Proposta", "Cadastro Proposta",
        "Formalização", "Atualização Dados Cliente", "Obter CCB", "Envia CCB Único",
        "Averbação Dataprev", "Nuvidio Antifraude", "Envio de Informações Dataprev",
        "Pagamento Pix", "Atualizar Tesouraria", "Atualizar Portal de Crédito",
        "Contratar o Seguro", "Aprovação Processo",
    ]
    motor = [
        "Validações Iniciais", "Token", "Dataprev Vínculos", "Dataprev Dados do Trabalhador",
        "RF PJ", "RF PF", "SCR", "BDC PJ Dados Básicos", "BDC PJ Dados Unificados",
        "PH3A PJ", "BDC PF Dados Unificados", "BDC PF Risco Financeiro",
        "BDC PF Dados Básicos", "PH3A PF",
    ]
    _box_base = ("min-height:56px;border-radius:9px;padding:10px 11px;flex-shrink:0;display:flex;"
                 "flex-direction:column;justify-content:center;gap:4px;")
    _arr = '<span style="align-self:center;color:#4b5563;font-size:15px;padding:0 5px;flex-shrink:0;">&#9656;</span>'
    _arm = '<span style="align-self:center;color:#6366f1;font-size:12px;padding:0 3px;flex-shrink:0;">&#9656;</span>'

    def _box(nome):
        return ('<div style="width:150px;min-width:150px;background:#15130e;border:1px solid #332e25;'
                + _box_base + '"><div style="color:#e2e8f0;font-size:12px;font-weight:600;line-height:1.25;">'
                + nome + '</div></div>')

    if nivel == "motor":
        crumb = ('<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">'
                 '<a href="?wf166=root" target="_self" title="Voltar" style="text-decoration:none;'
                 'color:#a5b4fc;font-size:14px;line-height:1;padding:4px 10px;border:1px solid #332e25;'
                 'border-radius:7px;background:#15130e;">&#9664;</a>'
                 '<span style="color:#94a3b8;font-size:13px;">&#128194; Workflow 166 &nbsp;&#8250;&nbsp; '
                 '<b style="color:#c7d2fe;">Motor de Cr&#233;dito</b></span></div>')
        parts = [
            '<div style="width:140px;min-width:140px;background:#141019;border:1px solid rgba(99,102,241,0.35);'
            + _box_base + '"><div style="color:#c4b5fd;font-size:12px;font-weight:600;line-height:1.25;">'
            + n + '</div></div>'
            for n in motor
        ]
        dec = ('<div style="width:150px;min-width:150px;background:#1a1420;border:1px solid rgba(167,139,250,0.55);'
               + _box_base + '"><div style="color:#e2e8f0;font-size:12px;font-weight:600;">Decis&#227;o Motor</div>'
               '<div style="font-size:9.5px;font-weight:600;"><span style="color:#22c55e;">&#10003; Aprova</span>'
               '&nbsp;&nbsp;<span style="color:#f87171;">&#10007; Reprova</span></div></div>')
        flow = _arm.join(parts) + _arm + dec
    else:
        crumb = ('<div style="margin-bottom:10px;color:#94a3b8;font-size:13px;">'
                 '&#128194; Workflow 166 &#183; <span style="color:#64748b;">n&#237;vel externo (16 fases) &#183; '
                 'clique no Motor de Cr&#233;dito para entrar</span></div>')
        parts = []
        for n in fases:
            if n == "Motor de Crédito":
                parts.append(
                    '<a href="?wf166=motor" target="_self" style="text-decoration:none;width:154px;min-width:154px;'
                    'background:rgba(99,102,241,0.12);border:1.5px solid #6366f1;box-shadow:0 0 0 3px rgba(99,102,241,0.07);'
                    + _box_base + '"><div style="color:#c7d2fe;font-size:12px;font-weight:700;line-height:1.25;">'
                    'Motor de Cr&#233;dito</div>'
                    '<div style="color:#8b93c9;font-size:8.5px;">&#128269; 14 sub-etapas &#183; clique para abrir</div></a>')
            else:
                parts.append(_box(n))
        flow = _arr.join(parts)

    return (crumb +
            '<div style="overflow:auto;border:1px solid #2a2620;border-radius:10px;background:#100e0a;'
            'padding:14px 16px;"><div style="display:flex;align-items:stretch;width:max-content;">'
            + flow + '</div></div>')


def _html_tabela_etapa_motivo(etapa_motivos: dict, etapas: dict, n_rep: int, order: list = None) -> str:
    if not etapa_motivos or not etapas or n_rep == 0:
        return ""
    _order_idx = {e: i for i, e in enumerate(order or _ETAPA_WORKFLOW_ORDER)}
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
        ("Prazo",             "Número de Parcelas",   lambda x: f"{x:.0f}"),
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
        ("Prazo",             "Número de Parcelas",        lambda x: f"{x:.0f}"),
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


def _build_desemb_det(datas: list, d_ini, d_fim, ori_ativas=None) -> list:
    """Contratos desembolsados (PaymentDate `pd` no período [d_ini, d_fim]).

    Lê os JSONs dos dias [d_ini-7, d_fim] (lookback de 7 dias — igual ao modo normal,
    pois cada JSON diário é chaveado pela data de CRIAÇÃO do lead e o desembolso pode
    ocorrer depois). Aplica o filtro de Origem quando `ori_ativas` for informado.
    Cada item é o dict `desembolsos_detalhe` (campos: pd, data_criacao, emp, cbo, cnae,
    uf, origem, valor, liberado, iof, prazo, taxa, parcela)."""
    _ori_set = set(ori_ativas) if ori_ativas else None
    _ini = d_ini - timedelta(days=7)
    out: list = []
    for _dd in datas:
        try:
            _dd_date = datetime.strptime(_dd, "%Y%m%d").date()
        except (ValueError, TypeError):
            continue
        if not (_ini <= _dd_date <= d_fim):
            continue
        _dj = carregar_dia(_dd)
        if not _dj:
            continue
        for _det in _dj.get("desembolsos_detalhe", []):
            _pdk = _det.get("pd")
            if not _pdk:
                continue
            try:
                _pdk_date = datetime.strptime(str(_pdk), "%Y%m%d").date()
            except (ValueError, TypeError):
                continue
            if not (d_ini <= _pdk_date <= d_fim):
                continue
            if _ori_set is not None and (_det.get("origem") or "Outros") not in _ori_set:
                continue
            out.append(_det)
    return out


def _compute_projecao_live(datas: list):
    """(ref_label, pess, otim) para a projeção a desembolsar — mesma lógica do modo normal.

    pess = 4 etapas finais da esteira com liberado>0 (sem BT); otim = todas as etapas
    com liberado>0 + BLOQUEIO_TEMPORARIO. Cada dict traz count/valor/iof, onde
    valor = valor contratado (com IOF). Independe do período: usa os últimos 5 dias."""
    _PROJ_PESS_SET = {"AVERBACAO_PENDENTE_MANUAL", "ENTREVISTA", "PAGAMENTO", "PENDENTE_DADOS_PAGAMENTO"}
    _ETAPA_ORD = ["PRE_APROVADO", "SIMULACAO", "FORMALIZACAO", "ASSINATURA", "ASSINADO",
                  "AVERBACAO_PENDENTE_MANUAL", "ENTREVISTA", "PAGAMENTO", "PENDENTE_DADOS_PAGAMENTO"]
    _now = datetime.utcnow() - timedelta(hours=3)
    _ref = _now.date()
    if _now.weekday() >= 5 or (_now.hour, _now.minute) > (18, 30):
        _ref += timedelta(days=1)
        while _ref.weekday() >= 5:
            _ref += timedelta(days=1)
    _bt = (carregar_dia(max(datas)) if datas else {}).get("bt_pix_days", {}).get(_ref.strftime("%Y%m%d"), {})
    _nonbt: dict = {}
    _today = _now.date()
    for _d in range(5):
        _s = (_today - timedelta(days=_d)).strftime("%Y%m%d")
        if _s not in datas:
            continue
        _j = carregar_dia(_s)
        if not _j:
            continue
        for _ts, _v in _j.get("projecao_tipos", {}).items():
            if _ts == "BLOQUEIO_TEMPORARIO" or _v.get("count", 0) <= 0:
                continue
            _a = _nonbt.setdefault(_ts, {"count": 0, "valor": 0.0, "liberado": 0.0, "iof": 0.0})
            _a["count"]    += _v.get("count", 0)
            _a["valor"]    += _v.get("valor", 0.0)
            _a["liberado"] += _v.get("liberado", 0.0)
            _a["iof"]      += _v.get("iof", 0.0)

    def _libpos(ts):
        return ((_nonbt.get(ts) or {}).get("liberado") or 0) > 0

    def _acc(etapas, incl_bt):
        _r = {"count": 0, "valor": 0.0, "iof": 0.0}
        for ts in etapas:
            _s = _nonbt.get(ts) or {}
            _r["count"] += _s.get("count", 0)
            _r["valor"] += _s.get("valor", 0.0)
            _r["iof"]   += _s.get("iof", 0.0)
        if incl_bt and (_bt.get("liberado") or 0) > 0:
            _r["count"] += _bt.get("count", 0)
            _r["valor"] += _bt.get("valor", 0.0)
            _r["iof"]   += _bt.get("iof", 0.0)
        return _r

    _pess_et = [ts for ts in _ETAPA_ORD if ts in _PROJ_PESS_SET and _libpos(ts)]
    _otim_et = [ts for ts in _nonbt if _libpos(ts)]
    return _ref.strftime("%d/%m"), _acc(_pess_et, False), _acc(_otim_et, True)


def _render_tv_slide(slide: int, agg: dict, funil: dict, fin: dict,
                     n_dias: int, dias_raw: list, datas_sel: list, periodo: str,
                     d_ini=None, d_fim=None):
    # _TV_CSS é emitido uma vez pelo chamador antes de invocar esta função.
    n_rep = funil.get("reprovados", 0)
    n_ap  = funil.get("aprovados", 0)

    # Fontes TV — grandes o suficiente para leitura a 3 metros
    _TV_TF   = dict(size=28, color="#FEC52E")
    _TV_AF   = dict(size=28, color="#94a3b8")
    _TV_TXT  = dict(size=28, color="rgba(255,255,255,0.92)")
    _TV_YTXT = dict(size=28, color="#cbd5e1")

    def _brl(x):
        return ("R$ " + f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if x else "—"

    def _pct(a, b):
        return f"{100*a/b:.1f}%" if b else "—"

    def _tv_bar(fig, h=620, r=120):
        """Aplica o layout TV a um gráfico de barras horizontais e o plota. False se vazio."""
        if not fig:
            return False
        fig.update_traces(textfont=_TV_TXT)
        fig.update_layout(
            height=h, title=dict(text=""),
            xaxis=dict(tickfont=_TV_AF),
            yaxis=dict(tickfont=_TV_YTXT, automargin=True),
            margin=dict(t=10, b=20, l=20, r=r),
        )
        st.plotly_chart(fig, width='stretch', config=_CONF)
        return True

    def _tv_line_valor(x, yval, ycnt, ylib, xtitle):
        fig = go.Figure(go.Scatter(
            x=x, y=yval, mode="lines+markers",
            line=dict(color="#10b981", width=3), marker=dict(size=9, color="#10b981"),
            fill="tozeroy", fillcolor="rgba(16,185,129,0.10)",
            customdata=list(zip(ycnt, ylib)),
            hovertemplate=("<b>%{x}</b><br>Contratado: <b>R$ %{y:,.2f}</b><br>"
                           "Contratos: <b>%{customdata[0]}</b><br>"
                           "Liberado: <b>R$ %{customdata[1]:,.2f}</b><extra></extra>"),
        ))
        fig.update_layout(
            template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG, height=640,
            separators=",.", title=dict(text=""),
            xaxis=dict(title=dict(text=xtitle, font=_TV_AF), tickfont=_TV_AF, showgrid=True, gridcolor=_GRID),
            yaxis=dict(title=dict(text="Valor (R$)", font=_TV_AF), tickfont=_TV_AF, showgrid=True,
                       gridcolor=_GRID, tickformat=",.0f", tickprefix="R$ "),
            margin=dict(t=20, b=50, l=10, r=20), hovermode="x unified",
        )
        st.plotly_chart(fig, width='stretch', config=_CONF)

    # ═══════════════ A · VISÃO GERAL ═══════════════
    if slide == 0:
        _tv_h("Visão Geral — Funil de Leads", periodo)
        _taxa_ap = f"{funil['taxa_aprovacao']:.1f}%" if funil.get("terminais") else "—"
        st.markdown(f"""
        <div class="kpi-row" style="grid-template-columns:repeat(4,1fr)">
          <div class="kpi-card"><div class="kpi-label">Total de leads</div>
            <div class="kpi-value">{_nbr(funil.get('total', 0))}</div><div class="kpi-sub">{periodo}</div></div>
          <div class="kpi-card"><div class="kpi-label">Novos</div>
            <div class="kpi-value">{_nbr(funil.get('novos', 0))}</div><div class="kpi-sub">{_pct(funil.get('novos', 0), funil.get('total', 0))} do total</div></div>
          <div class="kpi-card"><div class="kpi-label">Reprovados</div>
            <div class="kpi-value" style="color:#FEC52E">{_nbr(n_rep)}</div><div class="kpi-sub">{funil.get('taxa_reprovacao', 0):.1f}% dos finalizados</div></div>
          <div class="kpi-card"><div class="kpi-label">Aprovados</div>
            <div class="kpi-value" style="color:#FEC52E">{_nbr(n_ap)}</div><div class="kpi-sub">taxa de aprovação: {_taxa_ap}</div></div>
        </div>
        """, unsafe_allow_html=True)

    elif slide == 1:
        _tv_h("Distribuição por Status", periodo)
        fig = _fig_donut(funil.get("_d_status", {}))
        if fig:
            fig.update_traces(textfont=dict(size=27))
            fig.update_annotations(font_size=30)
            fig.update_layout(height=620, legend=dict(font=dict(size=30, color="#94a3b8")))
            st.plotly_chart(fig, width='stretch', config=_CONF)
        else:
            st.info("Sem dados de status.")

    elif slide == 2:
        _tv_h("Funil de Conversão", periodo)
        fig = _fig_funil_rico(funil)
        if fig:
            fig.update_traces(textfont=dict(size=32, color="#e2e8f0"),
                              texttemplate="%{value:,}  %{percentInitial:.1%}")
            fig.update_layout(height=620, title=dict(text=""),
                xaxis=dict(tickfont=_TV_AF), yaxis=dict(tickfont=_TV_YTXT, automargin=True),
                margin=dict(t=10, b=20, l=250, r=40))
            st.plotly_chart(fig, width='stretch', config=_CONF)

    elif slide == 3:
        _tv_h("Evolução Temporal — Leads por Status", periodo)
        fig = _fig_evolucao(agg, n_dias, dias_raw=dias_raw, datas_sel=datas_sel)
        if fig:
            fig.update_layout(height=620, title=dict(text=""),
                margin=dict(t=120, b=20, l=10, r=20),
                xaxis=dict(tickfont=_TV_AF, title=dict(font=_TV_AF)),
                yaxis=dict(tickfont=_TV_AF, title=dict(font=_TV_AF)),
                legend=dict(orientation="h", x=0.5, y=1.07, xanchor="center", yanchor="bottom",
                    bgcolor="rgba(15,14,11,0.88)", bordercolor="rgba(255,255,255,0.10)",
                    borderwidth=1, font=dict(size=34, color="#94a3b8")))
            st.plotly_chart(fig, width='stretch', config=_CONF)

    # ═══════════════ B · APROVADOS ═══════════════
    elif slide == 4:
        _tv_h("Aprovados — Indicadores Financeiros", periodo)
        _vol = fin.get("ValorContratacao", {}); _lib = fin.get("ValorLiquido", {})
        _prz = fin.get("Prazo", {}); _tx = fin.get("Taxa", {}); _pc = fin.get("ValorParcela", {})
        _taxa_txt = (f"{_tx['media']:.2f}".replace('.', ',') + "% a.m.") if _tx.get("media") else "—"
        _prz_txt  = f"{_prz['media']:.0f}" if _prz.get("media") else "—"
        st.markdown(f"""
        <div class="kpi-row" style="grid-template-columns:repeat(4,1fr)">
          <div class="kpi-card"><div class="kpi-label">Contratos aprovados</div>
            <div class="kpi-value" style="color:#FEC52E">{_nbr(n_ap)}</div><div class="kpi-sub">leads aprovados</div></div>
          <div class="kpi-card"><div class="kpi-label">Total contratado (com IOF)</div>
            <div class="kpi-value">{_brl(_vol.get('total'))}</div><div class="kpi-sub">valor contratado</div></div>
          <div class="kpi-card"><div class="kpi-label">Total liberado (sem IOF)</div>
            <div class="kpi-value">{_brl(_lib.get('total'))}</div><div class="kpi-sub">recebido pelo cliente</div></div>
          <div class="kpi-card"><div class="kpi-label">Ticket contratado</div>
            <div class="kpi-value">{_brl(_vol.get('media'))}</div><div class="kpi-sub">por contrato</div></div>
        </div>
        <div class="kpi-row" style="grid-template-columns:repeat(4,1fr)">
          <div class="kpi-card"><div class="kpi-label">Ticket liberado</div>
            <div class="kpi-value">{_brl(_lib.get('media'))}</div><div class="kpi-sub">por contrato</div></div>
          <div class="kpi-card"><div class="kpi-label">Valor da parcela</div>
            <div class="kpi-value">{_brl(_pc.get('media'))}</div><div class="kpi-sub">média pond. pelo prazo</div></div>
          <div class="kpi-card"><div class="kpi-label">Taxa mensal</div>
            <div class="kpi-value">{_taxa_txt}</div><div class="kpi-sub">pond. pelo nº de parcelas</div></div>
          <div class="kpi-card"><div class="kpi-label">Nº de parcelas</div>
            <div class="kpi-value">{_prz_txt}</div><div class="kpi-sub">média</div></div>
        </div>
        """, unsafe_allow_html=True)

    elif slide == 5:
        _tv_h("Aprovados — Estatísticas Financeiras", periodo)
        html = _html_tabela_financeira(fin)
        if html:
            st.markdown(html, unsafe_allow_html=True)
        else:
            st.info("Sem dados financeiros.")

    elif slide == 6:
        _tv_h("Aprovados — Distribuição do Valor Contratado", periodo)
        fig = _fig_histograma(agg.get("valores_contratacao", []))
        if fig:
            fig.update_annotations(font_size=25)
            fig.update_layout(height=680, title=dict(text=""),
                xaxis=dict(title=dict(text="Valor (R$)", font=_TV_AF), tickformat=",.0f", tickfont=_TV_AF),
                yaxis=dict(title=dict(text="Contratos", font=_TV_AF), tickfont=_TV_AF),
                margin=dict(t=10, b=40, l=10, r=10))
            st.plotly_chart(fig, width='stretch', config=_CONF)
        else:
            st.info("Sem dados de distribuição.")

    elif slide == 7:
        _tv_h("Aprovados — Top Empregadores", periodo)
        if not _tv_bar(_fig_barras_h(agg.get("top_empregadores", {}), "", "#22c55e", pct_base=n_ap)):
            st.info("Sem dados de empregadores.")

    elif slide == 8:
        _tv_h("Aprovados — Top CBOs", periodo)
        if not _tv_bar(_fig_barras_h(_sem_codigo(agg.get("top_cbos", {})), "", "#3b82f6", pct_base=n_ap), r=55):
            st.info("Sem dados de CBOs.")

    # ═══════════════ C · DESEMBOLSOS ═══════════════
    elif slide == 9:
        _tv_h("Desembolsos no Período", periodo)
        _dd = _build_desemb_det(datas, d_ini, d_fim)
        if not _dd:
            st.info("Sem contratos desembolsados no período.")
        else:
            _n = len(_dd)
            _tot_val = sum((r.get("valor", 0.0) or 0.0) for r in _dd)
            _tot_lib = sum((r.get("liberado", 0.0) or 0.0) for r in _dd)
            _tot_iof = sum((r.get("iof", 0.0) or 0.0) for r in _dd)
            _txpz = [(r["taxa"], r["prazo"]) for r in _dd if r.get("taxa") and r.get("prazo")]
            _pcpz = [(r["parcela"], r["prazo"]) for r in _dd if r.get("parcela") and r.get("prazo")]
            _przs = [r["prazo"] for r in _dd if r.get("prazo")]
            _tx_m = (sum(t * z for t, z in _txpz) / sum(z for _, z in _txpz)) if _txpz else None
            _pc_m = (sum(p * z for p, z in _pcpz) / sum(z for _, z in _pcpz)) if _pcpz else None
            _prz_m = (sum(_przs) / len(_przs)) if _przs else None
            _tk = (_tot_val / _n) if _n else 0
            _taxa_txt = (f"{_tx_m:.2f}".replace('.', ',') + "% a.m.") if _tx_m else "—"
            _prz_txt  = f"{_prz_m:.0f}" if _prz_m else "—"
            st.markdown(f"""
            <div class="kpi-row" style="grid-template-columns:repeat(4,1fr)">
              <div class="kpi-card"><div class="kpi-label">Contratos desembolsados</div>
                <div class="kpi-value" style="color:#FEC52E">{_nbr(_n)}</div><div class="kpi-sub">{periodo}</div></div>
              <div class="kpi-card"><div class="kpi-label">Total contratado (com IOF)</div>
                <div class="kpi-value" style="color:#FEC52E">{_brl(_tot_val)}</div><div class="kpi-sub">valor do empréstimo</div></div>
              <div class="kpi-card"><div class="kpi-label">Total liberado (sem IOF)</div>
                <div class="kpi-value" style="color:#FEC52E">{_brl(_tot_lib)}</div><div class="kpi-sub">recebido pelo cliente</div></div>
              <div class="kpi-card"><div class="kpi-label">IOF total</div>
                <div class="kpi-value">{_brl(_tot_iof)}</div><div class="kpi-sub">soma do período</div></div>
            </div>
            <div class="kpi-row" style="grid-template-columns:repeat(4,1fr)">
              <div class="kpi-card"><div class="kpi-label">Ticket contratado</div>
                <div class="kpi-value">{_brl(_tk)}</div><div class="kpi-sub">por contrato</div></div>
              <div class="kpi-card"><div class="kpi-label">Valor da parcela</div>
                <div class="kpi-value">{_brl(_pc_m)}</div><div class="kpi-sub">média pond. pelo prazo</div></div>
              <div class="kpi-card"><div class="kpi-label">Taxa mensal</div>
                <div class="kpi-value">{_taxa_txt}</div><div class="kpi-sub">pond. pelo nº de parcelas</div></div>
              <div class="kpi-card"><div class="kpi-label">Nº de parcelas</div>
                <div class="kpi-value">{_prz_txt}</div><div class="kpi-sub">média</div></div>
            </div>
            """, unsafe_allow_html=True)

    elif slide == 10:
        _tv_h("Evolução Temporal de Desembolsos", periodo)
        _dd = _build_desemb_det(datas, d_ini, d_fim)
        _acc: dict = {}
        for r in _dd:
            k = r.get("pd")
            if not k:
                continue
            a = _acc.setdefault(k, {"count": 0, "valor": 0.0, "lib": 0.0})
            a["count"] += 1; a["valor"] += r.get("valor", 0.0) or 0; a["lib"] += r.get("liberado", 0.0) or 0
        if not _acc:
            st.info("Sem contratos desembolsados no período.")
        else:
            ks = sorted(_acc)
            _tv_line_valor(
                [datetime.strptime(k, "%Y%m%d").strftime("%d/%m") for k in ks],
                [round(_acc[k]["valor"], 2) for k in ks],
                [_acc[k]["count"] for k in ks],
                [round(_acc[k]["lib"], 2) for k in ks],
                "Data de Desembolso")

    elif slide == 11:
        _tv_h("Desembolsos por Data de Criação do Lead", periodo)
        _dd = _build_desemb_det(datas, d_ini, d_fim)
        _acc: dict = {}
        for r in _dd:
            k = r.get("data_criacao")
            if not k:
                continue
            try:
                datetime.strptime(str(k), "%Y%m%d")
            except (ValueError, TypeError):
                continue
            a = _acc.setdefault(str(k), {"count": 0, "valor": 0.0, "lib": 0.0})
            a["count"] += 1; a["valor"] += r.get("valor", 0.0) or 0; a["lib"] += r.get("liberado", 0.0) or 0
        if not _acc:
            st.info("Sem contratos desembolsados no período.")
        else:
            ks = sorted(_acc)
            _tv_line_valor(
                [datetime.strptime(k, "%Y%m%d").strftime("%d/%m") for k in ks],
                [round(_acc[k]["valor"], 2) for k in ks],
                [_acc[k]["count"] for k in ks],
                [round(_acc[k]["lib"], 2) for k in ks],
                "Data de Criação do Lead")

    elif slide in (12, 13, 14, 15):
        _dd = _build_desemb_det(datas, d_ini, d_fim)
        _n = len(_dd)
        _seg = {"emp": {}, "cbo": {}, "cnae": {}, "ori": {}, "uf": {}}
        for r in _dd:
            for key, field in (("emp", "emp"), ("cbo", "cbo"), ("cnae", "cnae"), ("ori", "origem"), ("uf", "uf")):
                k = r.get(field)
                if not k:
                    continue
                a = _seg[key].setdefault(k, {"n": 0, "valor": 0.0, "liberado": 0.0})
                a["n"] += 1; a["valor"] += r.get("valor", 0.0) or 0; a["liberado"] += r.get("liberado", 0.0) or 0

        def _it(m, by):
            return [{"label": k, "n": v["n"], "valor": v["valor"], "liberado": v["liberado"]}
                    for k, v in sorted(m.items(), key=lambda x: -x[1][by])]

        def _trunc(s, m=42):
            s = str(s)
            return s if len(s) <= m else s[:m - 1].rstrip() + "…"

        if slide == 12:
            _tv_h("Desembolsados — Top Empregadores (R$ contratado)", periodo)
            if not _dd:
                st.info("Sem contratos desembolsados no período.")
            else:
                _chart: dict = {}
                for it in _it(_seg["emp"], "valor")[:12]:
                    kk = _trunc(it["label"])
                    _chart[kk] = _chart.get(kk, 0.0) + it["valor"]
                fig = _fig_barras_reais(_chart, "", "#FEC52E")
                if fig:
                    fig.update_traces(textfont=_TV_TXT)
                    fig.update_layout(height=680, title=dict(text=""),
                        xaxis=dict(tickfont=_TV_AF), yaxis=dict(tickfont=_TV_YTXT, automargin=True),
                        margin=dict(t=10, b=20, l=20, r=200))
                    st.plotly_chart(fig, width='stretch', config=_CONF)
        elif slide == 13:
            _tv_h("Desembolsados — Top CBOs", periodo)
            if not _tv_bar(_fig_barras_h(_sem_codigo({it["label"]: it["n"] for it in _it(_seg["cbo"], "n")}),
                                         "", "#3b82f6", pct_base=_n, show_abs=True), r=55):
                st.info("Sem contratos desembolsados no período.")
        elif slide == 14:
            _tv_h("Desembolsados — Top CNAEs", periodo)
            if not _tv_bar(_fig_barras_h(_sem_codigo({it["label"]: it["n"] for it in _it(_seg["cnae"], "n")}),
                                         "", "#a855f7", pct_base=_n, show_abs=True), r=55):
                st.info("Sem contratos desembolsados no período.")
        else:  # slide 15
            _tv_h("Desembolsados — Por Origem e UF", periodo)
            if not _dd:
                st.info("Sem contratos desembolsados no período.")
            else:
                _c1, _c2 = st.columns(2)
                with _c1:
                    _tv_bar(_fig_barras_h({it["label"]: it["n"] for it in _it(_seg["ori"], "n")},
                                          "", "#f59e0b", pct_base=_n, show_abs=True, text_auto=True), h=560, r=110)
                with _c2:
                    _tv_bar(_fig_barras_h({it["label"]: it["n"] for it in _it(_seg["uf"], "n")},
                                          "", "#06b6d4", n=27, pct_base=_n, show_abs=True), h=560, r=70)

    elif slide == 16:
        _tv_h("Projeção a Desembolsar", periodo)
        _ref_lbl, _pess, _otim = _compute_projecao_live(datas)
        _p_com = _pess["valor"]; _p_sem = _pess["valor"] - _pess["iof"]
        _o_com = _otim["valor"]; _o_sem = _otim["valor"] - _otim["iof"]
        st.markdown(f"""
        <div class="kpi-row" style="grid-template-columns:repeat(3,1fr)">
          <div class="kpi-card"><div class="kpi-label">Projeção pessimista de leads</div>
            <div class="kpi-value">{_nbr(_pess['count'])}</div><div class="kpi-sub">via Pix {_ref_lbl}</div></div>
          <div class="kpi-card"><div class="kpi-label">Valor contratado (com IOF)</div>
            <div class="kpi-value" style="color:#FEC52E">{_brl(_p_com)}</div><div class="kpi-sub">cenário pessimista</div></div>
          <div class="kpi-card"><div class="kpi-label">Valor liberado (sem IOF)</div>
            <div class="kpi-value">{_brl(_p_sem)}</div><div class="kpi-sub">cenário pessimista</div></div>
          <div class="kpi-card"><div class="kpi-label">Projeção otimista de leads</div>
            <div class="kpi-value">{_nbr(_otim['count'])}</div><div class="kpi-sub">via Pix {_ref_lbl}</div></div>
          <div class="kpi-card"><div class="kpi-label">Valor contratado (com IOF)</div>
            <div class="kpi-value" style="color:#FEC52E">{_brl(_o_com)}</div><div class="kpi-sub">cenário otimista</div></div>
          <div class="kpi-card"><div class="kpi-label">Valor liberado (sem IOF)</div>
            <div class="kpi-value">{_brl(_o_sem)}</div><div class="kpi-sub">cenário otimista</div></div>
        </div>
        <p style="color:#64748b;font-size:20px;margin-top:10px">Pessimista = 4 etapas finais da esteira · Otimista = todas as etapas com valor liberado + bloqueio temporário.</p>
        """, unsafe_allow_html=True)

    # ═══════════════ D · REPROVAÇÕES ═══════════════
    elif slide == 17:
        _tv_h("Etapas de Reprovação — Funil", periodo)
        etapas_d = agg.get("etapas", {})
        if etapas_d and n_rep > 0:
            _etapas_c, _, _ordem_c = _combinar_etapas_conceito(etapas_d, agg.get("etapa_motivos", {}))
            result_f = _fig_funil_etapa(_etapas_c, n_rep, order=_ordem_c)
            if result_f:
                fig_f, _ = result_f
                fig_f.update_traces(textfont=dict(size=40, color="rgba(255,255,255,0.92)"),
                                    selector=dict(type="bar"))
                fig_f.update_layout(height=620, title=dict(text=""),
                    xaxis=dict(tickfont=_TV_AF), yaxis=dict(tickfont=_TV_YTXT, automargin=True),
                    legend=dict(orientation="v", x=0.82, y=0.04, xanchor="left", yanchor="bottom",
                        bgcolor="rgba(15,14,11,0.85)", bordercolor="rgba(255,255,255,0.08)",
                        borderwidth=1, font=dict(size=28)),
                    margin=dict(t=10, b=20, l=20, r=40))
                st.plotly_chart(fig_f, width='stretch', config=_CONF)
        else:
            st.info("Sem dados de etapas.")

    elif slide == 18:
        _tv_h("Motivos de Reprovação — Alto Nível", periodo)
        if not _tv_bar(_fig_barras_h(agg.get("top_motivos", {}), "", "#ef4444", pct_base=n_rep)):
            st.info("Sem dados de motivos.")

    elif slide == 19:
        _tv_h("Motivos de Reprovação — Detalhado", periodo)
        mot_det = _merge_motivos_det(agg.get("top_motivos_det", {}))
        if mot_det:
            _tv_bar(_fig_barras_h(mot_det, "", "#f97316", pct_base=sum(mot_det.values())))
        else:
            st.info("Sem dados de motivos detalhados.")

    elif slide == 20:
        _tv_h("Leads com Bloqueio por Tipo", periodo)
        fig = _fig_bloqueios(agg.get("bloqueios", {}), n_bloq=agg.get("bloqueados_total", 0))
        if fig:
            fig.update_traces(textfont=dict(size=28, color="#e2e8f0"))
            fig.update_layout(height=560, title=dict(text=""),
                xaxis=dict(tickfont=dict(size=28, color="#cbd5e1")), yaxis=dict(tickfont=_TV_AF),
                margin=dict(t=10, b=40, l=80, r=80))
            st.plotly_chart(fig, width='stretch', config=_CONF)
        else:
            st.info("Sem dados de bloqueios.")

    elif slide == 21:
        _tv_h("Top Empregadores dos Reprovados", periodo)
        if not _tv_bar(_fig_barras_h(agg.get("top_emp_rep", {}), "", "#ef4444", pct_base=n_rep, show_pct=False)):
            st.info("Sem dados de empregadores dos reprovados.")

    elif slide == 22:
        _tv_h("CNAEs Bloqueados dos Reprovados", periodo)
        cnaes = agg.get("top_cnaes", {})
        if cnaes:
            _tv_bar(_fig_barras_h(_sem_codigo(cnaes), "", "#eab308", pct_base=sum(cnaes.values()), show_abs=True), r=55)
        else:
            st.info("Sem dados de CNAE bloqueado.")

    elif slide == 23:
        _tv_h("CBOs Bloqueados dos Reprovados", periodo)
        cbos_rep = agg.get("top_cbos_rep", {})
        if cbos_rep:
            _tv_bar(_fig_barras_h(_sem_codigo(cbos_rep), "", "#a855f7", pct_base=sum(cbos_rep.values()), show_abs=True), r=55)
        else:
            st.info("Sem dados de CBO dos reprovados.")

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
                    "_login_via":   "cookie",
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

# ── Admin & registro de acesso ────────────────────────────────────────────────
_user_email_sess = st.session_state.get("user_email", "")
_is_admin_sess   = (not st.session_state.get("_is_tv")) and _is_admin_user(_user_email_sess)

# Registra o acesso 1× por sessão (grava no repo privado; falha de escrita não derruba o app).
if (st.session_state.get("logged_in") and not st.session_state.get("_is_tv")
        and not st.session_state.get("_acesso_registrado")):
    import threading
    threading.Thread(
        target=_registrar_acesso,
        args=(_user_email_sess,
              st.session_state.get("display_name", _user_email_sess),
              st.session_state.pop("_login_via", "cookie")),
        daemon=True,
    ).start()
    st.session_state["_acesso_registrado"] = True

# Página admin — histórico de acessos (apenas admin, via ?page=acessos).
if _is_admin_sess and st.query_params.get("page") == "acessos":
    try:
        _pagina_acessos()
    except Exception as _e_acc:
        st.error("Erro ao carregar o histórico de acessos.")
        with st.expander("Detalhes do erro"):
            st.exception(_e_acc)
    st.stop()

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
    
        # Tela cheia automática removida: usava components.html (depreciado) só para injetar
        # JS de requestFullscreen — "melhor esforço" que o sandbox do iframe costumava bloquear.
        # O modo TV segue normal; para tela cheia, F11. (git guarda a versão anterior.)
    
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
            if st.button("‹", key="tv_prev", width='stretch'):
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
            if st.button("Últimos 7 dias", key="tv_7d", width='stretch'):
                st.session_state["_tv_date"] = max(data_min, data_max - timedelta(days=6))
                st.session_state["_tv_picker_ver"] += 1
                st.session_state["tv_slide"] = 0
                st.rerun()
        with _cp_3d:
            if st.button("Últimos 3 dias", key="tv_3d", width='stretch'):
                st.session_state["_tv_date"] = max(data_min, data_max - timedelta(days=2))
                st.session_state["_tv_picker_ver"] += 1
                st.session_state["tv_slide"] = 0
                st.rerun()
        with _cp_1d:
            if st.button("Desde Ontem", key="tv_1d", width='stretch'):
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
            if st.button("›", key="tv_next", width='stretch'):
                st.session_state["tv_slide"] = _tv_next
                st.rerun()
        with _cp_exit:
            if st.button("Sair do modo TV", key="tv_exit", width='stretch'):
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
            _d_ini_tv, data_max,
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
    
    # ── Saída de modo TV ──────────────────────────────────────────────────────────
    else:
        # (JS de exitFullscreen removido — usava components.html depreciado.)
        _origins_avail = ["B2B", "B2B-API", "B2C", "B2C-CT", "CTPS"]

        with _slot.container():

            # ── Aviso de manutenção (banner global; ligado/desligado por admin) ────────────
            _manut = _ler_manutencao()
            if _manut.get("ativo"):
                _mmsg = _manut.get("mensagem") or "Os dados podem estar temporariamente desatualizados — já estamos atualizando."
                _mdesde = ""
                try:
                    _mdesde = " · desde " + datetime.fromisoformat(_manut["desde"]).strftime("%d/%m %H:%M")
                except Exception:
                    pass
                st.markdown(
                    '<div style="background:rgba(254,197,46,0.12);border:1px solid rgba(254,197,46,0.45);'
                    'border-left:4px solid #FEC52E;border-radius:10px;padding:11px 16px;margin:2px 0 14px;'
                    'display:flex;align-items:center;gap:12px">'
                    '<span style="font-size:19px;line-height:1">&#128295;</span>'
                    '<div style="font-size:14px;color:#e2e8f0;line-height:1.45">'
                    f'<b style="color:#FEC52E">Em manutenção</b> &mdash; {_mmsg}'
                    f'<span style="color:#94a3b8">{_mdesde}</span></div></div>',
                    unsafe_allow_html=True,
                )

            # ── Header + seletor ──────────────────────────────────────────────────────────

            col_title, col_picker = st.columns([1, 1])

            with col_title:
                if _is_admin_sess:
                    _c_tit, _c_adm, _c_man, _c_tv, _c_out = st.columns([3, 1.05, 0.9, 1, 1])
                else:
                    _c_tit, _c_tv, _c_out = st.columns([3, 1, 1])
                    _c_adm = _c_man = None
                with _c_tit:
                    st.markdown(
                        '<div style="display:flex;align-items:flex-end;gap:10px;margin:4px 0 6px">'
                        '<svg viewBox="0 0 483 462" xmlns="http://www.w3.org/2000/svg" '
                        'style="height:52px;width:auto;flex-shrink:0;display:block;'
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
                        '<span style="font-size:32px;font-weight:700;line-height:1;'
                        'color:#e2e8f0;letter-spacing:-0.5px">ileads</span>'
                        '</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div class="periodo">Dados de {data_min.strftime("%d/%m/%Y")} '
                        f'até {data_max.strftime("%d/%m/%Y")}</div>',
                        unsafe_allow_html=True,
                    )
                if _c_adm is not None:
                    with _c_adm:
                        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                        if st.button("🔐 Acessos", width='stretch',
                                     help="Histórico de acessos (admin)"):
                            st.query_params["page"] = "acessos"
                            st.rerun()
                if _c_man is not None:
                    with _c_man:
                        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                        with st.popover("🛠", help="Aviso de manutenção (admin)"):
                            st.markdown("**Aviso de manutenção** — visível a todos os usuários")
                            _mc = _ler_manutencao()
                            st.caption("🟠 ATIVO agora" if _mc.get("ativo") else "⚪ Inativo")
                            _mtxt = st.text_area(
                                "Mensagem exibida no topo",
                                value=(_mc.get("mensagem")
                                       or "Os dados podem estar temporariamente desatualizados — já estamos atualizando."),
                                key="_manut_txt", height=90)
                            _mb1, _mb2 = st.columns(2)
                            with _mb1:
                                if st.button("Ativar", key="_manut_on", width='stretch', type="primary"):
                                    _ok = _set_manutencao(True, _mtxt, _user_email_sess)
                                    _ler_manutencao.clear()
                                    st.toast("Manutenção ativada." if _ok else "Falha ao ativar (token sem escrita?).")
                                    st.rerun()
                            with _mb2:
                                if st.button("Desativar", key="_manut_off", width='stretch'):
                                    _ok = _set_manutencao(False, _mtxt, _user_email_sess)
                                    _ler_manutencao.clear()
                                    st.toast("Manutenção desativada." if _ok else "Falha ao desativar.")
                                    st.rerun()
                with _c_tv:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    if st.button("📺 Modo TV", width='stretch'):
                        st.session_state["tv_slide"] = 0
                        st.query_params["tv"] = "1"
                        st.rerun()
                with _c_out:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    if st.button("Sair", width='stretch'):
                        _cookies.remove(_COOKIE_NAME)
                        for _k in ["logged_in", "user_email", "display_name", "_cookie_set",
                                   "_cookie_checked", "_acesso_registrado", "_login_via"]:
                            st.session_state.pop(_k, None)
                        st.session_state["_cookie_checked"] = True  # evita tela preta pós-logout
                        st.session_state["_force_logout"] = True    # impede restore do cookie no mesmo rerun
                        st.rerun()
            
            with col_picker:
                _cp_dl, _cp_dat, _cp_orig, _cp_ref = st.columns([0.4, 2.1, 2, 0.5])
                with _cp_dl:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    if st.session_state.get("_baixando"):
                        st.markdown(
                            "<div id='_dlspin' style='height:38px;display:flex;align-items:center;"
                            "justify-content:center'><div style='width:15px;height:15px;border:2px solid "
                            "#3a3733;border-top-color:#FEC52E;border-radius:50%;"
                            "animation:_dlsp .7s linear infinite'></div></div>"
                            "<style>@keyframes _dlsp{to{transform:rotate(360deg)}}</style>",
                            unsafe_allow_html=True)
                    elif st.button("↓", key="_dl_html_btn", width='stretch',
                                   help="Baixar um HTML da visualização atual"):
                        st.session_state["_baixando"] = True
                        st.rerun()
                with _cp_dat:
                    intervalo = st.date_input(
                        "Período de análise",
                        value=(d_ini_default, data_max),
                        min_value=data_min, max_value=data_max,
                        format="DD/MM/YYYY",
                    )
                with _cp_orig:
                    # Rótulo custom "Origem" + "i" (pj-i) com balão estilizado ao lado do rótulo.
                    # Label do widget colapsado p/ não duplicar e p/ o "i" ficar colado em "Origem".
                    _origem_tip = (
                        "Os leads possuem as seguintes origens:<br><br>"
                        "<b>B2C</b> → Leads originados pelo cliente via Site e direcionados ao Bot do WhatsApp<br>"
                        "<b>B2B</b> → Leads originados pelos Corbans via Zili+<br>"
                        "<b>B2B-API</b> → Leads originados pelos Corbans via API<br>"
                        "<b>CTPS</b> → Leads originados via Leilão e direcionados ao Bot do WhatsApp<br>"
                        "<b>B2C-CT</b> → Leads originados via Leilão e direcionados ao Bot do WhatsApp que, por não "
                        "terem perfis adequados à taxa inicial ofertada, receberam nova proposta, fora do "
                        "Leilão, com uma taxa maior"
                    )
                    st.markdown(
                        '<div style="font-size:0.875rem;line-height:1.6;margin-bottom:0.35rem;'
                        f'white-space:nowrap">Origem {_info_i(_origem_tip)}</div>',
                        unsafe_allow_html=True,
                    )
                    _origem_raw = st.multiselect(
                        "Origem",
                        options=_origins_avail,
                        default=[],
                        key="origem_sel",
                        placeholder="Todas",
                        label_visibility="collapsed",
                    )
                with _cp_ref:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    if st.button("↺", width='stretch', help="Forçar atualização dos dados"):
                        # Só os recentes (mutáveis) + a lista de datas. Históricos são
                        # imutáveis — re-baixá-los a cada clique só traria de volta a lentidão.
                        _carregar_dia_recente.clear()
                        listar_datas.clear()
                        st.rerun()

            # Download de um HTML da visualização atual: com o spinner no lugar do ↓, injeta
            # um JS que clona o DOM ao vivo do parent, REMOVE os <script> (evita re-hidratação
            # que apagaria o snapshot) e insere <base href> na origem do app (p/ o CSS/fontes
            # relativos carregarem). setTimeout dá tempo do restante da página renderizar.
            if st.session_state.get("_baixando"):
                components.html('''
<script>
(function(){
  var d=window.parent.document;
  // Pronto = sem DOM "stale" (do rerun) e todos os graficos plotly ja com <svg>.
  function ready(){
    if(d.querySelector('[data-stale="true"]')) return false;
    var divs=d.querySelectorAll('.js-plotly-plot'), drawn=0;
    for(var k=0;k<divs.length;k++){ if(divs[k].querySelector('svg')) drawn++; }
    return divs.length===0 || drawn>=divs.length;
  }
  function capture(){
   try{
    var o=d.location.origin;
    // Le TODAS as folhas (externas + inline). O emotion do Streamlit usa "speedy mode":
    // injeta as regras no CSSOM e deixa as <style> VAZIAS no HTML -> tem que ler .cssRules.
    // Ordem do document.styleSheets = ordem da cascata; concatenando, preserva a cascata.
    var css='';
    for(var i=0;i<d.styleSheets.length;i++){
      var ss=d.styleSheets[i]; if(!ss) continue;
      try{ var r=ss.cssRules; for(var j=0;j<r.length;j++){ css+=r[j].cssText; } }catch(_e){}
    }
    var c=d.documentElement.cloneNode(true);
    c.querySelectorAll('script,iframe,style,link[rel="stylesheet"],link[rel="modulepreload"],link[rel="preload"],[data-stale="true"]').forEach(function(n){n.remove();});
    var hd=c.querySelector('head');
    if(hd){
      var b=d.createElement('base'); b.setAttribute('href',o+'/'); hd.insertBefore(b,hd.firstChild);
      if(css){ var st=d.createElement('style'); st.textContent=css; hd.insertBefore(st,b.nextSibling); }
    }
    var s2=c.querySelector('#_dlspin'); if(s2){s2.innerHTML='';}
    var h='<!doctype html>'+c.outerHTML;
    var bl=new Blob([h],{type:'text/html;charset=utf-8'}); var u=URL.createObjectURL(bl);
    var a=d.createElement('a'); a.href=u;
    a.download='zileads_'+new Date().toISOString().slice(0,19).replace(/[:T]/g,'-')+'.html';
    d.body.appendChild(a); a.click(); d.body.removeChild(a); URL.revokeObjectURL(u);
    var sp=d.getElementById('_dlspin'); if(sp){sp.innerHTML='<div style="color:#8a8a8a;text-align:center;line-height:38px">&#8595;</div>';}
   }catch(e){ try{window.parent.alert('Falha ao gerar HTML: '+e.message);}catch(_){}}
  }
  var tries=0;
  (function w(){ if(ready()||tries>50){ capture(); } else { tries++; setTimeout(w,200); } })();
})();
</script>
''', height=0)
                st.session_state["_baixando"] = False

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

            # Origens selecionadas (vazio → sem filtro). Quando ativo, reconstrói cada
            # dia com a soma das origens selecionadas (por_origem) e re-agrega — assim
            # financeiro + segmentações (seções 8–13) também respeitam o filtro.
            _ori_ativas = _origem_raw or None
            _dias_agg = ([_apply_origem(_d, _ori_ativas) for _d in dias_raw]
                         if _ori_ativas else dias_raw)
            agg = agregar(_dias_agg)

            if _ori_ativas:
                _fpo = agg.get("funil_por_origem", {})
                _ap_f  = sum(_fpo.get(o, {}).get("aprovados",  0) for o in _ori_ativas)
                _rp_f  = sum(_fpo.get(o, {}).get("reprovados", 0) for o in _ori_ativas)
                _ca_f  = sum(_fpo.get(o, {}).get("cancelados", 0) for o in _ori_ativas)
                _ec_f  = sum(_fpo.get(o, {}).get("em_curso",   0) for o in _ori_ativas)
                _nv_f  = sum(_fpo.get(o, {}).get("novos",      0) for o in _ori_ativas)
                _tot_f = _ap_f + _rp_f + _ca_f + _ec_f
                _trm_f = _ap_f + _rp_f + _ca_f
                agg["funil"] = {
                    "total":           _tot_f,
                    "aprovados":       _ap_f,
                    "reprovados":      _rp_f,
                    "cancelados":      _ca_f,
                    "terminais":       _trm_f,
                    "em_curso":        _ec_f,
                    "novos":           _nv_f,
                    "taxa_aprovacao":  _ap_f / _trm_f * 100 if _trm_f else 0.0,
                    "taxa_reprovacao": _rp_f / _trm_f * 100 if _trm_f else 0.0,
                    "_d_status":       {3: _ap_f, 4: _rp_f, 8: _ca_f, -1: _ec_f, 0: _nv_f},
                }

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
            
            # ── Pré-computa desembolsos (usa cache de carregar_dia) ───────────────────────
            _d_desemb_ini = d_ini - timedelta(days=7)
            _d_desemb_datas = [
                d for d in datas
                if _d_desemb_ini <= datetime.strptime(d, "%Y%m%d").date() <= d_fim
            ]
            # Detalhe por contrato desembolsado (data de desembolso `pd` no período),
            # já aplicando o filtro de Origem — `desembolsos_detalhe` carrega o campo
            # `origem` por registro. Toda a informação de desembolso do dash (KPIs do
            # topo, seção 1 e seção 14) é derivada daqui, então tudo respeita o filtro.
            # Desembolso = QUALQUER status com PaymentDate (não só aprovados; inclui casos
            # raros s7/s8 que tiveram ordem de pagamento). Cada registro traz `status`.
            _ori_set = set(_ori_ativas) if _ori_ativas else None
            _desemb_det: list = []
            for _dd in _d_desemb_datas:
                _dj = carregar_dia(_dd)
                if not _dj:
                    continue
                for _det in _dj.get("desembolsos_detalhe", []):
                    _pdk = _det.get("pd")
                    if not _pdk:
                        continue
                    try:
                        _pdk_date = datetime.strptime(str(_pdk), "%Y%m%d").date()
                    except (ValueError, TypeError):
                        continue
                    if not (d_ini <= _pdk_date <= d_fim):
                        continue
                    if _ori_set is not None and (_det.get("origem") or "Outros") not in _ori_set:
                        continue
                    _desemb_det.append(_det)
            # Agregado por data de desembolso (para a seção 1 e os KPIs), derivado do
            # detalhe filtrado — por isso reflete o filtro de Origem.
            _desemb_agg: dict = {}
            for _det in _desemb_det:
                _pd = _det.get("pd")
                if not _pd:
                    continue
                if _pd not in _desemb_agg:
                    _desemb_agg[_pd] = {"count": 0, "valor": 0.0, "liberado": 0.0}
                _desemb_agg[_pd]["count"]    += 1
                _desemb_agg[_pd]["valor"]    += _det.get("valor", 0.0) or 0.0
                _desemb_agg[_pd]["liberado"] += _det.get("liberado", 0.0) or 0.0
            _desemb_tot_count = len(_desemb_det)
            _desemb_tot_valor = sum((_d.get("valor", 0.0) or 0.0) for _d in _desemb_det)
            _desemb_tot_lib   = sum((_d.get("liberado", 0.0) or 0.0) for _d in _desemb_det)

            # ── KPIs ──────────────────────────────────────────────────────────────────────
            
            taxa     = f"{f['taxa_aprovacao']:.1f}%" if f.get("terminais") else "—"
            vol      = fin.get("ValorContratacao", {})
            vol_s    = ("R$ " + f"{vol['total']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if vol.get("total") else "—"
            # BT live: independente do período — data de referência baseada no horário BRT atual
            _now_brt_nm  = datetime.utcnow() - timedelta(hours=3)
            _pix_ab_nm   = _now_brt_nm.weekday() < 5 and (7, 0) <= (_now_brt_nm.hour, _now_brt_nm.minute) <= (18, 30)
            _default_ref_nm = _now_brt_nm.date()
            _avancar_nm  = _now_brt_nm.weekday() >= 5 or (_now_brt_nm.hour, _now_brt_nm.minute) > (18, 30)
            if _avancar_nm:
                _default_ref_nm += timedelta(days=1)
                while _default_ref_nm.weekday() >= 5:
                    _default_ref_nm += timedelta(days=1)
            _data_ref_nm   = st.session_state.get("_proj_ref_nm", _default_ref_nm)
            _ultimo_nm      = carregar_dia(max(datas)) if datas else {}
            _ref_str_kpi    = _default_ref_nm.strftime("%Y%m%d")
            _ref_short_kpi  = _default_ref_nm.strftime("%d/%m")
            _bt_live_kpi_nm = _ultimo_nm.get("bt_pix_days", {}).get(_ref_str_kpi, {})
            # Non-BT live: últimos 5 dias a partir de hoje, independente do período
            _non_bt_live_nm: dict = {}
            _today_nm = _now_brt_nm.date()
            for _d5nm in range(5):
                _s5nm = (_today_nm - timedelta(days=_d5nm)).strftime("%Y%m%d")
                if _s5nm not in datas:
                    continue
                _j5nm = carregar_dia(_s5nm)
                if not _j5nm:
                    continue
                for _ts5nm, _v5nm in _j5nm.get("projecao_tipos", {}).items():
                    if _ts5nm == "BLOQUEIO_TEMPORARIO":
                        continue
                    if _v5nm.get("count", 0) > 0:
                        if _ts5nm not in _non_bt_live_nm:
                            _non_bt_live_nm[_ts5nm] = {"count": 0, "valor": 0.0, "liberado": 0.0, "iof": 0.0}
                        _non_bt_live_nm[_ts5nm]["count"]    += _v5nm.get("count", 0)
                        _non_bt_live_nm[_ts5nm]["valor"]    += _v5nm.get("valor", 0.0)
                        _non_bt_live_nm[_ts5nm]["liberado"] += _v5nm.get("liberado", 0.0)
                        _non_bt_live_nm[_ts5nm]["iof"]      += _v5nm.get("iof", 0.0)
            _proj_cnt   = sum(d["count"]    for d in _non_bt_live_nm.values()) + _bt_live_kpi_nm.get("count", 0)
            _proj_cnt_s = f"{_proj_cnt:,}".replace(",", ".")
            # Labels e ordem das etapas — fonte única (reusadas na tabela de projeção e no heatmap).
            _TIPO_LABEL_MAP = {
                "PAGAMENTO":                 "Aguardando próxima janela de pagamento PIX (Suspenso)",
                "ASSINADO":                  "Falha em etapa pós-assinatura de CCB (Pendente Falha)",
                "ASSINATURA":                "Aguardando assinatura do cliente na CCB enviada (Suspenso)",
                "ENTREVISTA":                "Aguardando realização de entrevista anti-fraude da Nuvidio (Suspenso)",
                "FORMALIZACAO":              "Aguardando aceite do cliente na etapa de formalização (Suspenso)",
                "PRE_APROVADO":              "Aguardando aceite do cliente quanto à proposta inicial (Suspenso)",
                "SIMULACAO":                 "Aguardando aceite do cliente quanto a uma nova proposta simulada (Suspenso)",
                "PENDENTE_DADOS_PAGAMENTO":  "Falha em dados de pagamento do cliente (Suspenso)",
                "BLOQUEIO_TEMPORARIO":       "Aguardando 24h para envio de nova proposta (Em andamento)",
                "AVERBACAO_PENDENTE_MANUAL": "Falha na etapa de averbação (Pendente Manual)",
            }
            # Ordem fixa das etapas (fonte única) — projeção, tabela e heatmap reusam abaixo.
            # BLOQUEIO_TEMPORARIO: 1º na tabela; fora do heatmap; demais fora da lista vão ao fim.
            _ETAPA_ORDER = [
                "PRE_APROVADO", "SIMULACAO", "FORMALIZACAO", "ASSINATURA", "ASSINADO",
                "AVERBACAO_PENDENTE_MANUAL", "ENTREVISTA", "PAGAMENTO", "PENDENTE_DADOS_PAGAMENTO",
            ]
            _ORD = {t: i for i, t in enumerate(_ETAPA_ORDER)}
            def _etapa_key(ts):
                if ts == "BLOQUEIO_TEMPORARIO":
                    return -1                      # 1ª na tabela de projeção
                return _ORD.get(ts, len(_ETAPA_ORDER))

            # Ambas as projeções contam SÓ etapas com valor liberado preenchido (liberado>0).
            # PESSIMISTA = as 4 etapas finais da esteira; OTIMISTA = TODAS as etapas com liberado
            # (superconjunto da pessimista → otimista >= pessimista sempre) + BLOQUEIO_TEMPORARIO.
            _PROJ_PESS = {"AVERBACAO_PENDENTE_MANUAL", "ENTREVISTA", "PAGAMENTO", "PENDENTE_DADOS_PAGAMENTO"}
            def _lib_pos(ts):
                return ((_non_bt_live_nm.get(ts) or {}).get("liberado") or 0) > 0
            _pess_etapas = [ts for ts in _ETAPA_ORDER if ts in _PROJ_PESS and _lib_pos(ts)]
            _otim_etapas = sorted((ts for ts in _non_bt_live_nm if _lib_pos(ts)), key=_etapa_key)
            _proj_pess_cnt = sum((_non_bt_live_nm.get(ts) or {}).get("count", 0) for ts in _pess_etapas)
            _proj_otim_cnt = sum((_non_bt_live_nm.get(ts) or {}).get("count", 0) for ts in _otim_etapas)
            if (_bt_live_kpi_nm.get("liberado") or 0) > 0:
                _proj_otim_cnt += _bt_live_kpi_nm.get("count", 0)
                _otim_etapas = ["BLOQUEIO_TEMPORARIO"] + _otim_etapas
            # (o valor da projeção é somado POR CENÁRIO — pessimista/otimista — no grupo 4 abaixo)
            
            _prazo_d   = fin.get("Prazo", {})
            _taxa_d    = fin.get("Taxa", {})
            _parcela_d = fin.get("ValorParcela", {})
            prazo_s   = f"{_prazo_d['media']:.0f} parcelas"  if _prazo_d.get("media") else "—"
            ticket_s  = ("R$ " + f"{vol['media']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if vol.get("media") else "—"
            parcela_s = ("R$ " + f"{_parcela_d['media']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if _parcela_d.get("media") else "—"
            taxa_s    = f"{_taxa_d['media']:.2f}".replace(".", ",") + "% a.m." if _taxa_d.get("media") else "—"
            
            _f_total_fmt = _nbr(f["total"])
            _f_aprov_fmt = _nbr(f["aprovados"])
            _f_novos_fmt = _nbr(f.get("novos", 0))
            _f_term_fmt  = _nbr(f["terminais"])
            _f_repro_fmt = _nbr(f["reprovados"])
            # % em relação ao total de leads (vírgula decimal, 2 casas): "34,21%"
            def _pct_tot(v):
                return (f"{100 * v / f['total']:.2f}".replace(".", ",") + "%") if f.get("total") else "—"
            _pct_novos_s = _pct_tot(f.get("novos", 0))
            _pct_aprov_s = _pct_tot(f["aprovados"])
            _pct_repro_s = _pct_tot(f["reprovados"])
            # Distribuição de Leads — Total + 9 status (SWorks 0-8). Cada KPI = 1 status
            # específico. O bucket -1 (em_curso, que só aparece sob filtro de origem, onde os
            # não-terminais vêm consolidados) NÃO é somado a nenhum status — é descartado,
            # pra "Em andamento" refletir só o status 2, batendo com o S-Works.
            _dist = dict(f.get("_d_status", {}))
            _dist.pop(-1, None)
            def _dnum(_c): return _nbr(_dist.get(_c, 0))
            def _dpct(_c): return _pct_tot(_dist.get(_c, 0))
            def _esc_ttl(_s):
                return (_s.replace("&", "&amp;").replace('"', "&quot;")
                          .replace("<", "&lt;").replace(">", "&gt;"))
            _DIST_CARDS = [
                (None, "Total",           "Total de Leads criados na esteira, incluindo todos os status possíveis"),
                (0,    "Novo",            "Leads que estão esperando estímulo do cliente para que seja iniciado o fluxo na esteira"),
                (2,    "Em andamento",    "Leads que estão sendo processados por um sistema em alguma etapa da esteira"),
                (4,    "Reprovado",       "Leads que foram reprovados em alguma etapa da esteira"),
                (3,    "Aprovado",        "Leads que foram convertidos em clientes"),
                (5,    "Suspenso",        "Leads que estão esperando estímulo do cliente ou de um sistema para seguir o fluxo na esteira"),
                (1,    "Pendente",        "Leads que estão aguardando processamento por um sistema em alguma etapa da esteira"),
                (6,    "Pendente Manual", "Leads que estão esperando estímulo interno para seguir o fluxo na esteira"),
                (7,    "Pendente Falha",  "Leads que resultaram em alguma falha ao longo da esteira e estão aguardando correção"),
                (8,    "Cancelado",       "Leads que foram cancelados manualmente em alguma etapa da esteira"),
            ]
            _dist_html = ""
            for _dc, _dl, _dt in _DIST_CARDS:
                _dv = _f_total_fmt if _dc is None else _dnum(_dc)
                _dp = ("100,00%" if f.get("total") else "—") if _dc is None else _dpct(_dc)
                _di = _info_i(_esc_ttl(_dt))
                _dist_html += (f'<div class="kpi-card"><div class="kpi-label">{_dl} {_di}</div>'
                               f'<div class="kpi-value">{_dv}</div>'
                               f'<div class="kpi-sub">{_dp} do Total</div></div>')
            _f_ag_fmt    = _nbr(_proj_cnt)
            _proj_global_tag = (
                " · <span style='color:#64748b;font-size:0.82em'>global</span>"
                if _ori_ativas else ""
            )

            # Desembolsos realizados (2 casas decimais nos valores $).
            _desemb_kpi_val_s    = ("R$ " + f"{_desemb_tot_valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if _desemb_tot_valor else "—"
            _desemb_kpi_lib_s    = ("R$ " + f"{_desemb_tot_lib:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if _desemb_tot_lib else "—"
            _desemb_ticket_s     = ("R$ " + f"{_desemb_tot_valor/_desemb_tot_count:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if _desemb_tot_count else "—"
            _desemb_ticket_lib_s = ("R$ " + f"{_desemb_tot_lib/_desemb_tot_count:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if _desemb_tot_count else "—"
            _desemb_cnt_s        = _nbr(_desemb_tot_count) if _desemb_tot_count else "—"

            # ── KPIs em 4 grupos: 1) funil · 2) aprovados · 3) desembolsados · 4) projeção ──
            # A separação aprovados × desembolsados é proposital: data de aprovação ≠ data
            # de desembolso, então as mesmas métricas (ticket, taxa, prazo, liberado) são
            # calculadas em bases distintas e nunca misturadas no mesmo bloco.
            _brl = lambda x: ("R$ " + f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if x else "—"
            # Grupo 2 — liberado ao cliente dos APROVADOS (fin['ValorLiquido']; fica "—" nos
            # dias exportados antes de o produtor passar a emitir esse campo).
            _ap_lib_d     = fin.get("ValorLiquido", {})
            _ap_lib_tot_s = _brl(_ap_lib_d.get("total"))
            _ap_lib_tk_s  = _brl(_ap_lib_d.get("media"))
            # Grupo 3 — taxa / nº de parcelas / valor da parcela médios dos DESEMBOLSADOS
            # (de _desemb_det; ignora registros sem o campo). Parcela = média ponderada pelo
            # prazo (mesmo critério dos aprovados).
            _dz_prazos  = [d["prazo"] for d in _desemb_det if d.get("prazo")]
            _dz_parc_pz = [(d["parcela"], d["prazo"]) for d in _desemb_det if d.get("parcela") and d.get("prazo")]
            _dz_taxa_pz = [(d["taxa"], d["prazo"]) for d in _desemb_det if d.get("taxa") and d.get("prazo")]
            _dz_taxa_m  = (sum(_t * _z for _t, _z in _dz_taxa_pz) / sum(_z for _, _z in _dz_taxa_pz)) if _dz_taxa_pz else None
            _dz_prazo_m = (sum(_dz_prazos) / len(_dz_prazos)) if _dz_prazos else None
            _dz_parc_m  = (sum(p * z for p, z in _dz_parc_pz) / sum(z for _, z in _dz_parc_pz)) if _dz_parc_pz else None
            _dz_taxa_s  = (f"{_dz_taxa_m:.2f}".replace(".", ",") + "% a.m.") if _dz_taxa_m else "—"
            _dz_prazo_s = f"{_dz_prazo_m:.0f} parcelas" if _dz_prazo_m else "—"
            _dz_parc_s  = _brl(_dz_parc_m)
            # Grupo 4 — projeção POR CENÁRIO (2 linhas × 3 col): nº de leads + valor liberado
            # (sem IOF) + valor contratado (com IOF). O valor é somado sobre as etapas de cada
            # cenário (pessimista = _pess_etapas; otimista = _otim_etapas). valor = liberado + iof.
            def _proj_sum(_etapas, _field):
                _t = 0.0
                for _ts in _etapas:
                    _src = _bt_live_kpi_nm if _ts == "BLOQUEIO_TEMPORARIO" else (_non_bt_live_nm.get(_ts) or {})
                    _t += _src.get(_field, 0.0)
                return _t
            _pess_val = _proj_sum(_pess_etapas, "valor"); _pess_iof = _proj_sum(_pess_etapas, "iof")
            _otim_val = _proj_sum(_otim_etapas, "valor"); _otim_iof = _proj_sum(_otim_etapas, "iof")
            _pess_comiof_fmt = _brl(_pess_val)
            _pess_semiof_fmt = _brl(_pess_val - _pess_iof)
            _otim_comiof_fmt = _brl(_otim_val)
            _otim_semiof_fmt = _brl(_otim_val - _otim_iof)
            _pix_ref_sub     = f"(via PIX em {_ref_short_kpi}){_proj_global_tag}"
            _proj_pess_fmt   = _nbr(_proj_pess_cnt)
            _proj_otim_fmt   = _nbr(_proj_otim_cnt)
            def _proj_tip(_codes):
                def _esc(_s):
                    return (_s.replace("&", "&amp;").replace('"', "&quot;")
                              .replace("<", "&lt;").replace(">", "&gt;"))
                _nm = [_esc(_TIPO_LABEL_MAP.get(_c, _c)) for _c in _codes]
                if not _nm:
                    return "Nenhuma etapa com valor liberado no período."
                return "Etapas consideradas:<br>" + "<br>".join("• " + _lbl for _lbl in _nm)
            _pess_tip = _proj_tip(_pess_etapas)
            _otim_tip = _proj_tip(_otim_etapas)

            _nat_ag = agg.get("natureza_leads") or {}
            _nat_pf_n = int(_nat_ag.get("PF", 0)); _nat_pj_n = int(_nat_ag.get("PJ", 0))
            _nat_base = _nat_pf_n + _nat_pj_n
            _nat_pf_fmt, _nat_pj_fmt = _nbr(_nat_pf_n), _nbr(_nat_pj_n)
            _nat_pf_sub = (f"{100*_nat_pf_n/_nat_base:.1f}% dos identificados" if _nat_base else "sem dados no período")
            _nat_pj_sub = (f"{100*_nat_pj_n/_nat_base:.1f}% dos identificados" if _nat_base else "sem dados no período")

            _pf = agg.get("pipeline_financeiro", {})   # usado por Alertas e Desembolsos por Data
            _dup = agg.get("duplicatas_cpf", [])       # idem (hoisted p/ ficar sempre disponivel)
            # ── Hub de navegação ──────────────────────────────────────────────
            # 6 botões (3 col × 2 linhas) que selecionam um grupo de seções.
            # ETAPA 1 (esta): apenas criar os botões e guardar a escolha em
            # st.session_state["hub_sel"] (None = nada selecionado ainda).
            # PRÓXIMA ETAPA: exibir abaixo só o grupo de seções escolhido
            # (gating por _HUB_SECOES), escondendo o resto enquanto não houver clique.
            _HUB_LABELS = {
                "principais_kpis":      "Principais KPIs",
                "evolucao_leads":       "Evolução de Leads",
                "leads_reprovados":     "Leads Reprovados",
                "projecao_desembolsos": "Projeção de Desembolsos",
                "leads_desembolsados":  "Leads desembolsados",
                "leads_aprovados":      "Leads Aprovados",
            }
            _HUB_LAYOUT = [
                ["principais_kpis", "evolucao_leads", "leads_reprovados"],
                ["projecao_desembolsos", "leads_desembolsados", "leads_aprovados"],
            ]
            st.session_state.setdefault("hub_sel", None)
            for _hub_linha in _HUB_LAYOUT:
                for _hcol, _hkey in zip(st.columns(3, gap="small"), _hub_linha):
                    with _hcol:
                        if st.button(
                            _HUB_LABELS[_hkey], key=f"hub_{_hkey}", width='stretch',
                            type=("primary" if st.session_state["hub_sel"] == _hkey else "secondary"),
                        ):
                            st.session_state["hub_sel"] = _hkey
                            st.rerun()

            def _show(*_keys):
                """True se o hub tem um dos grupos `_keys` selecionado (None => nada)."""
                return st.session_state.get("hub_sel") in _keys

            # Empty state: nenhum botão selecionado ainda → orienta o usuário.
            if st.session_state.get("hub_sel") is None:
                st.markdown(
                    '<div style="text-align:center;color:#64748b;font-size:.98em;'
                    'padding:34px 16px;margin-top:8px;border:1px dashed #cbd5e1;'
                    'border-radius:12px;background:rgba(148,163,184,0.06)">'
                    '👆 Selecione uma das seções acima para visualizar os dados.'
                    '</div>',
                    unsafe_allow_html=True,
                )

            if _show("principais_kpis", "evolucao_leads"):
                st.markdown(f"""
            <div class="kpi-grp">Distribuição de Leads <span>{periodo_label} · {n_dias} dia(s)</span></div>
            <div class="kpi-row" style="grid-template-columns:repeat(5,1fr)">
              {_dist_html}
            </div>
                """, unsafe_allow_html=True)
            if _show("principais_kpis"):
                st.markdown(f"""
            <div class="kpi-grp">Distribuição de Leads por Natureza do Empregador <span>(entre os leads com natureza identificada)</span></div>
            <div class="kpi-row" style="grid-template-columns:repeat(2,1fr)">
              <div class="kpi-card"><div class="kpi-label">Empregador Pessoa Física</div><div class="kpi-value">{_nat_pf_fmt}</div><div class="kpi-sub">{_nat_pf_sub}</div></div>
              <div class="kpi-card"><div class="kpi-label">Empregador Pessoa Jurídica</div><div class="kpi-value">{_nat_pj_fmt}</div><div class="kpi-sub">{_nat_pj_sub}</div></div>
            </div>
                """, unsafe_allow_html=True)
            if _show("principais_kpis", "leads_aprovados"):
                st.markdown(f"""
            <div class="kpi-grp">Aprovados <span>(leads aprovados no período)</span></div>
            <div class="kpi-row" style="grid-template-columns:repeat(4,1fr)">
              <div class="kpi-card"><div class="kpi-label">Contratos aprovados</div><div class="kpi-value">{_f_aprov_fmt}</div><div class="kpi-sub">leads aprovados</div></div>
              <div class="kpi-card"><div class="kpi-label">Total contratado (com IOF)</div><div class="kpi-value">{vol_s}</div><div class="kpi-sub">valor contratado total</div></div>
              <div class="kpi-card"><div class="kpi-label">Valor contratado médio (com IOF)</div><div class="kpi-value">{ticket_s}</div><div class="kpi-sub">por contrato aprovado</div></div>
              <div class="kpi-card"><div class="kpi-label">Valor da parcela médio</div><div class="kpi-value">{parcela_s}</div><div class="kpi-sub">média pond. pelo prazo</div></div>
              <div class="kpi-card"><div class="kpi-label">Taxa mensal média</div><div class="kpi-value">{taxa_s}</div><div class="kpi-sub">média pond. pelo nº de parcelas</div></div>
              <div class="kpi-card"><div class="kpi-label">Total liberado (sem IOF)</div><div class="kpi-value">{_ap_lib_tot_s}</div><div class="kpi-sub">valor recebido pelo cliente</div></div>
              <div class="kpi-card"><div class="kpi-label">Valor liberado médio (sem IOF)</div><div class="kpi-value">{_ap_lib_tk_s}</div><div class="kpi-sub">por contrato aprovado</div></div>
              <div class="kpi-card"><div class="kpi-label">Número de parcelas médio</div><div class="kpi-value">{prazo_s}</div><div class="kpi-sub">contratos aprovados</div></div>
            </div>
                """, unsafe_allow_html=True)
            if _show("principais_kpis", "leads_desembolsados"):
                st.markdown(f"""
            <div class="kpi-grp">Desembolsados <span>(leads desembolsados no período)</span></div>
            <div class="kpi-row" style="grid-template-columns:repeat(4,1fr)">
              <div class="kpi-card"><div class="kpi-label">Contratos desembolsados</div><div class="kpi-value">{_desemb_cnt_s}</div><div class="kpi-sub">{periodo_label}</div></div>
              <div class="kpi-card"><div class="kpi-label">Total contratado (com IOF)</div><div class="kpi-value">{_desemb_kpi_val_s}</div><div class="kpi-sub">valor contratado</div></div>
              <div class="kpi-card"><div class="kpi-label">Valor contratado médio (com IOF)</div><div class="kpi-value">{_desemb_ticket_s}</div><div class="kpi-sub">por contrato desembolsado</div></div>
              <div class="kpi-card"><div class="kpi-label">Valor da parcela médio</div><div class="kpi-value">{_dz_parc_s}</div><div class="kpi-sub">média pond. pelo prazo</div></div>
              <div class="kpi-card"><div class="kpi-label">Taxa mensal média</div><div class="kpi-value">{_dz_taxa_s}</div><div class="kpi-sub">média pond. pelo nº de parcelas</div></div>
              <div class="kpi-card"><div class="kpi-label">Total liberado (sem IOF)</div><div class="kpi-value">{_desemb_kpi_lib_s}</div><div class="kpi-sub">valor recebido pelo cliente</div></div>
              <div class="kpi-card"><div class="kpi-label">Valor liberado médio (sem IOF)</div><div class="kpi-value">{_desemb_ticket_lib_s}</div><div class="kpi-sub">por contrato desembolsado</div></div>
              <div class="kpi-card"><div class="kpi-label">Número de parcelas médio</div><div class="kpi-value">{_dz_prazo_s}</div><div class="kpi-sub">contratos desembolsados</div></div>
            </div>
                """, unsafe_allow_html=True)
            if _show("principais_kpis", "projecao_desembolsos"):
                st.markdown(f"""
            <div class="kpi-grp">Projeção a desembolsar <span>{_pix_ref_sub}</span></div>
            <div class="kpi-row" style="grid-template-columns:repeat(3,1fr)">
              <div class="kpi-card"><div class="kpi-label">Projeção pessimista de leads {_info_i(_pess_tip)}</div><div class="kpi-value">{_proj_pess_fmt}</div><div class="kpi-sub">leads</div></div>
              <div class="kpi-card"><div class="kpi-label">Valor contratado (com IOF)</div><div class="kpi-value">{_pess_comiof_fmt}</div><div class="kpi-sub">cenário pessimista</div></div>
              <div class="kpi-card"><div class="kpi-label">Valor liberado (sem IOF)</div><div class="kpi-value">{_pess_semiof_fmt}</div><div class="kpi-sub">cenário pessimista</div></div>
              <div class="kpi-card"><div class="kpi-label">Projeção otimista de leads {_info_i(_otim_tip)}</div><div class="kpi-value">{_proj_otim_fmt}</div><div class="kpi-sub">leads</div></div>
              <div class="kpi-card"><div class="kpi-label">Valor contratado (com IOF)</div><div class="kpi-value">{_otim_comiof_fmt}</div><div class="kpi-sub">cenário otimista</div></div>
              <div class="kpi-card"><div class="kpi-label">Valor liberado (sem IOF)</div><div class="kpi-value">{_otim_semiof_fmt}</div><div class="kpi-sub">cenário otimista</div></div>
            </div>
                """, unsafe_allow_html=True)
            # ── 1. Desembolsos no Período ─────────────────────────────────────────────────
            if _show("leads_desembolsados"):

                st.markdown('<div class="sec">Desembolsos no Período</div>', unsafe_allow_html=True)

                if _desemb_agg:
                    _desemb_sorted = dict(sorted(_desemb_agg.items()))
                    _d_x    = [datetime.strptime(d, "%Y%m%d").strftime("%d/%m") for d in _desemb_sorted]
                    _d_y_val = [round(v["valor"],    2) for v in _desemb_sorted.values()]
                    _d_y_cnt = [v["count"]              for v in _desemb_sorted.values()]
                    _d_y_lib = [round(v["liberado"],  2) for v in _desemb_sorted.values()]
                    _cap_val_s = "R$ " + f"{_desemb_tot_valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    _fig_desemb = go.Figure()
                    _fig_desemb.add_trace(go.Scatter(
                        x=_d_x,
                        y=_d_y_val,
                        name="Valor Contratado",
                        mode="lines+markers",
                        line=dict(color="#10b981", width=2),
                        marker=dict(size=6, color="#10b981"),
                        fill="tozeroy",
                        fillcolor="rgba(16,185,129,0.08)",
                        customdata=list(zip(_d_y_cnt, _d_y_lib)),
                        hovertemplate=(
                            "<b>%{x}</b><br>"
                            "Valor contratado: <b>R$ %{y:,.2f}</b><br>"
                            "Contratos: <b>%{customdata[0]}</b><br>"
                            "Liberado: <b>R$ %{customdata[1]:,.2f}</b>"
                            "<extra></extra>"
                        ),
                    ))
                    _fig_desemb.update_layout(
                        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
                        title=dict(text="Evolução Temporal de Desembolsos", font=_TF),
                        xaxis=dict(title="Data de Desembolso", tickfont=_AF, showgrid=True, gridcolor=_GRID),
                        yaxis=dict(title="Valor (R$)", tickfont=_AF, showgrid=True, gridcolor=_GRID, tickformat=",.0f", tickprefix="R$ "),
                        showlegend=False,
                        margin=dict(t=50, b=40, l=10, r=10),
                        height=360,
                        hovermode="x unified",
                    )
                    st.plotly_chart(_fig_desemb, width='stretch', config=_CONF)
                    st.caption(
                        f"Inclui leads criados até 7 dias antes do período filtrado · "
                        f"{_desemb_tot_count} contrato(s) · {_cap_val_s}"
                    )
                else:
                    _msg_ori = " para a(s) origem(ns) selecionada(s)" if _ori_ativas else ""
                    st.info(f"Sem contratos desembolsados no período selecionado{_msg_ori}.")

            # ── 2. Projeção de Desembolso ────────────────────────────────────────────────
            @st.fragment
            def _sec2_frag():

                # Spillover = próximo dia útil de Pix após o ÚLTIMO dia útil. O corte é
                # 18h30 do último dia útil (fim de semana -> sexta), computado no produtor.
                _ldu_nm = _now_brt_nm.date()
                while _ldu_nm.weekday() >= 5:
                    _ldu_nm -= timedelta(days=1)
                _next_ref_nm = _ldu_nm + timedelta(days=1)
                while _next_ref_nm.weekday() >= 5:
                    _next_ref_nm += timedelta(days=1)
                st.session_state.setdefault("proj_prox_dia_nm", False)   # default: DESLIGADO
                _c2ttl, _c2sw, _c2lbl = st.columns([3, 1, 6], gap="small", vertical_alignment="bottom")
                with _c2sw:
                    # label do widget colapsado; o rótulo + "?" (balão padrão) vão ao lado
                    _ver_prox_nm = st.toggle(
                        "dia útil seguinte", key="proj_prox_dia_nm",
                        label_visibility="collapsed",
                    )
                with _c2lbl:
                    _tog_tip = (f"Projeção do próximo dia útil ({_next_ref_nm.strftime('%d/%m')}): só leads em "
                                "bloqueio temporário com validade a partir das 18h30 do último dia útil.")
                    st.markdown(
                        f'<div style="font-size:0.9rem;line-height:2.2;white-space:nowrap">'
                        f'dia útil seguinte {_info_i(_tog_tip)}</div>',
                        unsafe_allow_html=True,
                    )
                _proj_ref_show_nm = _next_ref_nm if _ver_prox_nm else _default_ref_nm
                with _c2ttl:
                    st.markdown(f'<div class="sec">Projeção de Desembolso ({_proj_ref_show_nm.strftime("%d/%m/%Y")})</div>', unsafe_allow_html=True)

                # Data de referência Pix — próximo horário Pix possível (igual aos KPI cards)
                _data_ref_nm = _default_ref_nm
                _ref_str_nm    = _data_ref_nm.strftime("%Y%m%d")
                _ref_label_nm  = _data_ref_nm.strftime("%d/%m/%Y")
                _ref_short_nm  = _data_ref_nm.strftime("%d/%m")
                _bt_live_nm    = _ultimo_nm.get("bt_pix_days", {}).get(_ref_str_nm, {})
                # Non-BT e breakdown por dia (seção 1) — 5 dias relativo a _data_ref_nm
                _non_bt_sec_nm: dict = {}
                _pt_por_dia: dict = {}
                # 5 dias — projecao / breakdown da secao 1 (separado do heatmap)
                for _d5pd in range(5):
                    _s5pd = (_data_ref_nm - timedelta(days=_d5pd)).strftime("%Y%m%d")
                    if _s5pd not in datas:
                        continue
                    _dj2 = carregar_dia(_s5pd)
                    if not _dj2:
                        continue
                    for _ts2, _v2 in _dj2.get("projecao_tipos", {}).items():
                        if _ts2 == "BLOQUEIO_TEMPORARIO":
                            continue
                        if _v2.get("count", 0) > 0:
                            if _ts2 not in _non_bt_sec_nm:
                                _non_bt_sec_nm[_ts2] = {"count": 0, "valor": 0.0, "liberado": 0.0, "iof": 0.0, "taxa_sum": 0.0, "taxa_n": 0}
                            _non_bt_sec_nm[_ts2]["count"]    += _v2.get("count", 0)
                            _non_bt_sec_nm[_ts2]["valor"]    += _v2.get("valor", 0.0)
                            _non_bt_sec_nm[_ts2]["liberado"] += _v2.get("liberado", 0.0)
                            _non_bt_sec_nm[_ts2]["iof"]      += _v2.get("iof", 0.0)
                            _non_bt_sec_nm[_ts2]["taxa_sum"] += (_v2.get("taxa_media") or 0.0) * _v2.get("taxa_n", 0)
                            _non_bt_sec_nm[_ts2]["taxa_n"]   += _v2.get("taxa_n", 0)
                            if _ts2 not in _pt_por_dia:
                                _pt_por_dia[_ts2] = {}
                            _pt_por_dia[_ts2][_s5pd] = {
                                "count":      _v2.get("count", 0),
                                "valor":      _v2.get("valor", 0.0),
                                "liberado":   _v2.get("liberado", 0.0),
                                "iof":        _v2.get("iof", 0.0),
                                "taxa_media": _v2.get("taxa_media"),
                                "taxa_n":     _v2.get("taxa_n", 0),
                            }
                # BT: breakdown já está keyed por dia Pix no JSON mais recente
                _pt_por_dia["BLOQUEIO_TEMPORARIO"] = _ultimo_nm.get("bt_pix_days", {})
                # Derivar taxa_media por etapa (média ponderada sobre os 5 dias acumulados)
                for _ts3 in _non_bt_sec_nm:
                    _tn3 = _non_bt_sec_nm[_ts3].get("taxa_n", 0)
                    _non_bt_sec_nm[_ts3]["taxa_media"] = (_non_bt_sec_nm[_ts3]["taxa_sum"] / _tn3) if _tn3 > 0 else None

                # _TIPO_LABEL_MAP / _ETAPA_ORDER / _ORD / _etapa_key definidos acima (grupo 4 de KPIs) — fonte única.

                # Tabela: non-BT live (5 dias) + BT live. Toggle "dia útil seguinte" mostra
                # APENAS os leads BT com validade >= hoje 18:30 (spillover p/ o próximo dia útil).
                if _ver_prox_nm:
                    _bt_prox_nm = _ultimo_nm.get("bt_proximo_dia_util", {})
                    _pt_sec = {"BLOQUEIO_TEMPORARIO": _bt_prox_nm} if _bt_prox_nm.get("count", 0) > 0 else {}
                    if not _pt_sec:
                        st.caption("Sem leads em bloqueio temporário com validade a partir das 18h30 do último dia útil (ou aguardando a próxima exportação dos dados).")
                else:
                    _pt_sec_base = dict(_non_bt_sec_nm)
                    if _bt_live_nm.get("count", 0) > 0:
                        _pt_sec_base["BLOQUEIO_TEMPORARIO"] = _bt_live_nm
                    _pt_sec = _pt_sec_base
                if _pt_sec:
                    def _r(v): return ("R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if v else "—"
                    def _n(v): return f"{v:,}".replace(",", ".")
                    def _pct(v): return (f"{v:.2f}".replace(".", ",") + "% a.m.") if v else "—"
                    def _tip(ts):
                        _tx = _ETAPA_TOOLTIPS.get(ts, "")
                        if not _tx:
                            return ""
                        _tx = (_tx.replace("&", "&amp;").replace('"', "&quot;")
                                  .replace("<", "&lt;").replace(">", "&gt;"))
                        return f"<span class='pj-i' title=\"{_tx}\">?</span>"
                    _HIDE_VALOR_TIPOS = {"PRE_APROVADO"}  # ASSINATURA voltou a exibir valor/liberado
            
                    _sorted = sorted(_pt_sec.items(), key=lambda x: (_etapa_key(x[0]), -x[1]["valor"]))
                    _t_cnt  = sum(d["count"]    for d in _pt_sec.values())
                    _t_val  = sum(d["valor"]    for ts, d in _pt_sec.items() if ts not in _HIDE_VALOR_TIPOS)
                    _t_lib  = sum(d["liberado"] for ts, d in _pt_sec.items() if ts not in _HIDE_VALOR_TIPOS)
                    _t_iof  = sum(d["iof"]      for ts, d in _pt_sec.items() if ts not in _HIDE_VALOR_TIPOS)
                    _t_taxa_n   = sum((d.get("taxa_n") or 0) for d in _pt_sec.values())
                    _t_taxa_sum = sum((d.get("taxa_media") or 0) * (d.get("taxa_n") or 0) for d in _pt_sec.values())
                    _t_taxa     = _t_taxa_sum / _t_taxa_n if _t_taxa_n > 0 else None
            
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
                                f"<span class='pj-det-x'>{_pct(_dv3.get('taxa_media'))}</span>"
                                f"</div>"
                                for _ds3, _dv3 in sorted(_dias_ts.items())
                            )
                            _cell_lbl = f"<details class='pj-det'><summary>{_label}{_tip(ts)}</summary>{_det_inner}</details>"
                        else:
                            _cell_lbl = f"{_label}{_tip(ts)}"
                        _hv = ts in _HIDE_VALOR_TIPOS
                        _rows += (
                            f"<tr>"
                            f"<td class='pj-lbl'>{_cell_lbl}</td>"
                            f"<td class='pj-n'>{_n(d['count'])}</td>"
                            f"<td class='pj-n'>{_pct(d.get('taxa_media'))}</td>"
                            f"<td class='pj-n'>{'—' if _hv else _r(d['valor'])}</td>"
                            f"<td class='pj-n'>{'—' if _hv else _r(d['liberado'])}</td>"
                            f"<td class='pj-n'>{'—' if _hv else _r(d['iof'])}</td>"
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
                .pj-det-x{{color:#64748b;font-variant-numeric:tabular-nums}}
                /* .pj-i definido no bloco de estilo global (topo do app) — fonte unica */
                </style>
                <div class="pj-wrap">
                <table class="pj-tbl">
                  <thead><tr>
                    <th>Etapa</th>
                    <th class="pj-n">Leads</th>
                    <th class="pj-n">Taxa Média</th>
                    <th class="pj-n">Valor Total</th>
                    <th class="pj-n">Liberado</th>
                    <th class="pj-n">IOF</th>
                  </tr></thead>
                  <tbody>
                    {_rows}
                    <tr class="pj-tot">
                      <td class="pj-lbl">Total</td>
                      <td class="pj-n">{_n(_t_cnt)}</td>
                      <td class="pj-n">{_pct(_t_taxa)}</td>
                      <td class="pj-n">{_r(_t_val)}</td>
                      <td class="pj-n">{_r(_t_lib)}</td>
                      <td class="pj-n">{_r(_t_iof)}</td>
                    </tr>
                  </tbody>
                </table>
                <p style='color:#475569;font-size:.8em;margin:6px 0 0'>* Etapas consideram leads dos últimos 5 dias a partir de hoje, independente do período selecionado.</p>
                </div>
                """, unsafe_allow_html=True)

                else:
                    st.markdown(
                        "<p style='color:#475569;font-size:.88em'>Sem dados de projeção para o período.</p>",
                        unsafe_allow_html=True,
                    )
            
            if _show("projecao_desembolsos"):
                _sec2_frag()

            # ── 3. Desembolsos por Data de Criação ───────────────────────────────────────
            if _show("leads_desembolsados"):

                st.markdown('<div class="sec">Desembolsos por Data de Criação</div>', unsafe_allow_html=True)


                # Mesmo padrão do gráfico da seção 1 (Evolução Temporal de Desembolsos), mas
                # distribui os contratos DESEMBOLSADOS no período pela DATA DE CRIAÇÃO do lead
                # (não pela data de desembolso). Reaproveita o mesmo `_desemb_det`, já filtrado
                # por período (data de desembolso) e por Origem.
                _cr_agg: dict = {}
                _cr_sem_dc = 0
                for _det in _desemb_det:
                    _dck = _det.get("data_criacao")
                    if not _dck:
                        _cr_sem_dc += 1
                        continue
                    try:
                        datetime.strptime(str(_dck), "%Y%m%d")
                    except (ValueError, TypeError):
                        _cr_sem_dc += 1
                        continue
                    _slot = _cr_agg.setdefault(str(_dck), {"count": 0, "valor": 0.0, "liberado": 0.0})
                    _slot["count"]    += 1
                    _slot["valor"]    += _det.get("valor", 0.0) or 0.0
                    _slot["liberado"] += _det.get("liberado", 0.0) or 0.0

                if not _cr_agg:
                    _msg_ori3 = " para a(s) origem(ns) selecionada(s)" if _ori_ativas else ""
                    st.info(f"Sem contratos desembolsados no período selecionado{_msg_ori3}.")
                else:
                    _cr_sorted = dict(sorted(_cr_agg.items()))
                    _c_x     = [datetime.strptime(d, "%Y%m%d").strftime("%d/%m") for d in _cr_sorted]
                    _c_y_val = [round(v["valor"], 2)    for v in _cr_sorted.values()]
                    _c_y_cnt = [v["count"]              for v in _cr_sorted.values()]
                    _c_y_lib = [round(v["liberado"], 2) for v in _cr_sorted.values()]
                    _cr_tot_cnt = sum(_c_y_cnt)
                    _cr_tot_val = sum(_c_y_val)
                    _cap_cr_s = "R$ " + f"{_cr_tot_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    _fig_cr = go.Figure()
                    _fig_cr.add_trace(go.Scatter(
                        x=_c_x,
                        y=_c_y_val,
                        name="Valor Contratado",
                        mode="lines+markers",
                        line=dict(color="#10b981", width=2),
                        marker=dict(size=6, color="#10b981"),
                        fill="tozeroy",
                        fillcolor="rgba(16,185,129,0.08)",
                        customdata=list(zip(_c_y_cnt, _c_y_lib)),
                        hovertemplate=(
                            "<b>%{x}</b><br>"
                            "Valor contratado: <b>R$ %{y:,.2f}</b><br>"
                            "Contratos: <b>%{customdata[0]}</b><br>"
                            "Liberado: <b>R$ %{customdata[1]:,.2f}</b>"
                            "<extra></extra>"
                        ),
                    ))
                    _fig_cr.update_layout(
                        template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
                        title=dict(text="Evolução Temporal por Data de Criação", font=_TF),
                        xaxis=dict(title="Data de Criação do Lead", tickfont=_AF, showgrid=True, gridcolor=_GRID),
                        yaxis=dict(title="Valor (R$)", tickfont=_AF, showgrid=True, gridcolor=_GRID, tickformat=",.0f", tickprefix="R$ "),
                        showlegend=False,
                        margin=dict(t=50, b=40, l=10, r=10),
                        height=360,
                        hovermode="x unified",
                    )
                    st.plotly_chart(_fig_cr, width='stretch', config=_CONF)
                    _cap_cr = (f"Distribui os {_cr_tot_cnt} contrato(s) desembolsados no período "
                               f"pela data de criação do lead · {_cap_cr_s}")
                    if _cr_sem_dc:
                        _cap_cr += f" · {_cr_sem_dc} sem data de criação (ignorado(s))"
                    st.caption(_cap_cr)

            # ── 4. Evolução Temporal — Médias por Dia ──────────────────────────────────
            if _show("leads_desembolsados"):

                st.markdown('<div class="sec">Evolução Temporal — Médias por Dia</div>', unsafe_allow_html=True)

                # Médias por DATA DE DESEMBOLSO, sobre os contratos DESEMBOLSADOS do período
                # (o mesmo _desemb_det já filtrado por período + Origem). Um ponto por dia.
                if not _desemb_det:
                    _msg_ori4 = " para a(s) origem(ns) selecionada(s)" if _ori_ativas else ""
                    st.info(f"Sem contratos desembolsados no período selecionado{_msg_ori4}.")
                else:
                    # taxa = [Σ(taxa×prazo), nº contratos, Σ(prazo)] -> média ponderada pelo prazo;
                    # demais campos = [soma, count] -> média simples.
                    _ev_dia: dict = {}
                    for _r in _desemb_det:
                        _pdk = _r.get("pd")
                        if not _pdk:
                            continue
                        _slot = _ev_dia.setdefault(_pdk, {"taxa": [0.0, 0, 0.0], "prazo": [0.0, 0],
                                                          "liberado": [0.0, 0], "parcela": [0.0, 0]})
                        for _k in ("prazo", "liberado", "parcela"):
                            _v = _r.get(_k)
                            if _v:
                                _slot[_k][0] += _v
                                _slot[_k][1] += 1
                        _tx, _pz = _r.get("taxa"), _r.get("prazo")
                        if _tx and _pz:
                            _slot["taxa"][0] += _tx * _pz   # Σ(taxa×prazo)
                            _slot["taxa"][1] += 1           # nº de contratos (hover)
                            _slot["taxa"][2] += _pz         # Σ(prazo) = peso

                    _dias_ev = sorted(_ev_dia.keys())
                    _x_ev = [datetime.strptime(_dk, "%Y%m%d").strftime("%d/%m") for _dk in _dias_ev]

                    def _serie_ev(_campo):
                        _y, _cnt = [], []
                        for _dk in _dias_ev:
                            _slotv = _ev_dia[_dk][_campo]
                            if _campo == "taxa":
                                _wsum, _c, _psum = _slotv
                                _y.append(round(_wsum / _psum, 4) if _psum else None)
                            else:
                                _s, _c = _slotv
                                _y.append(round(_s / _c, 4) if _c else None)
                            _cnt.append(_c)
                        return _y, _cnt

                    def _fig_media(_campo, _titulo, _ytitle, _tickfmt, _tickpref="", _ticksuf="", _hval="", _ymin=None, _dtick=None):
                        _y, _cnt = _serie_ev(_campo)
                        _yax = dict(title=_ytitle, tickfont=_AF, showgrid=True, gridcolor=_GRID,
                                    tickformat=_tickfmt, tickprefix=_tickpref, ticksuffix=_ticksuf)
                        if _ymin is not None:
                            _vals = [v for v in _y if v is not None]
                            if _vals and max(_vals) > _ymin:
                                _top = max(_vals)
                                _yax["range"] = [_ymin, _top + (_top - _ymin) * 0.08]
                                # 1º tick (base) = exatamente o mínimo (tickmode linear a partir de _ymin)
                                if _dtick:
                                    _yax["tickmode"] = "linear"
                                    _yax["tick0"] = _ymin
                                    _yax["dtick"] = _dtick
                        _figm = go.Figure()
                        _figm.add_trace(go.Scatter(
                            x=_x_ev, y=_y, name=_titulo, mode="lines+markers",
                            line=dict(color="#10b981", width=2),
                            marker=dict(size=6, color="#10b981"),
                            fill="tozeroy", fillcolor="rgba(16,185,129,0.08)",
                            connectgaps=True, customdata=_cnt,
                            hovertemplate=(f"<b>%{{x}}</b><br>{_titulo}: <b>{_hval}</b><br>"
                                           "Contratos: <b>%{customdata}</b><extra></extra>"),
                        ))
                        _figm.update_layout(
                            template=_TEMPLATE, paper_bgcolor=_BG, plot_bgcolor=_BG,
                            separators=",.",   # vírgula decimal, ponto milhar (pt-BR)
                            title=dict(text=_titulo, font=_TF),
                            xaxis=dict(title="Data de Desembolso", tickfont=_AF, showgrid=True, gridcolor=_GRID),
                            yaxis=_yax,
                            showlegend=False, margin=dict(t=50, b=40, l=10, r=10),
                            height=360, hovermode="x unified",
                        )
                        return _figm

                    _tab_tx, _tab_pz, _tab_lb, _tab_pc = st.tabs(
                        ["Taxa média", "Número de parcelas médio", "Valor liberado médio", "Valor da parcela médio"])
                    with _tab_tx:
                        st.plotly_chart(_fig_media("taxa", "Taxa média", "Taxa (% a.m.)", ".2f",
                                        _ticksuf="%", _hval="%{y:.2f}%", _ymin=1.98, _dtick=0.5),
                                        width='stretch', config=_CONF)
                    with _tab_pz:
                        st.plotly_chart(_fig_media("prazo", "Número de parcelas médio", "Número de parcelas", ".0f",
                                        _hval="%{y:.1f} parcelas", _ymin=12.0, _dtick=6),
                                        width='stretch', config=_CONF)
                    with _tab_lb:
                        st.plotly_chart(_fig_media("liberado", "Valor liberado médio", "Valor (R$)", ",.2f",
                                        _tickpref="R$ ", _hval="R$ %{y:,.2f}", _ymin=600, _dtick=1000),
                                        width='stretch', config=_CONF)
                    with _tab_pc:
                        _yp, _cp = _serie_ev("parcela")
                        if any(_cp):
                            st.plotly_chart(_fig_media("parcela", "Valor da parcela médio", "Valor (R$)",
                                            ",.2f", _tickpref="R$ ", _hval="R$ %{y:,.2f}", _ymin=50, _dtick=50),
                                            width='stretch', config=_CONF)
                        else:
                            st.info("Sem valor de parcela nos desembolsos do período.")
                    st.caption(
                        "Média por data de desembolso entre os contratos desembolsados no período."
                    )

            # ── 5. Alertas ────────────────────────────────────────────────────────────────
            if _show("principais_kpis"):

                st.markdown('<div class="sec">Alertas</div>', unsafe_allow_html=True)

                if _dup:
                    _brl2 = lambda x: "R$ " + f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

                    # Pre-load historical approved leads for each CPF in _dup
                    _dup_cpf_set = {str(_it["cpf"]).strip().zfill(11) for _it in _dup}
                    _dup_hist: dict = {}
                    for _dd_h in datas:
                        _dj_h = carregar_dia(_dd_h)
                        if not _dj_h:
                            continue
                        for _cpf_h, _vh in (_dj_h.get("aprovados_por_cpf") or {}).items():
                            _cpf_h_z = str(_cpf_h).strip().zfill(11)
                            if _cpf_h_z not in _dup_cpf_set:
                                continue
                            if _cpf_h_z not in _dup_hist:
                                _dup_hist[_cpf_h_z] = {"_seen": set(), "leads": []}
                            for _lh in (_vh.get("leads") or []):
                                if _ori_ativas and (_lh.get("origem") or "Outros") not in _ori_ativas:
                                    continue
                                _lid_h = _lh.get("id", "")
                                if _lid_h and _lid_h in _dup_hist[_cpf_h_z]["_seen"]:
                                    continue
                                if _lid_h:
                                    _dup_hist[_cpf_h_z]["_seen"].add(_lid_h)
                                _dup_hist[_cpf_h_z]["leads"].append(_lh)

                    def _mask_ccb_dup(c):
                        c = str(c).strip()
                        if len(c) <= 4:
                            return c
                        return c[:3] + "*" * (len(c) - 4) + c[-1]

                    def _fmt_d_dup(d):
                        if not d:
                            return "—"
                        try:
                            return datetime.strptime(d, "%Y%m%d").strftime("%d/%m/%Y")
                        except ValueError:
                            return d

                    _dup_rows = []
                    for _i, _item in enumerate(_dup):
                        _rc = "g0" if _i % 2 == 0 else "g1"
                        _conts = "<br>".join(
                            f'{c["codigo"] or c["identificador"][:8]} — {c["etapa"]} — {_brl2(c["valor"])}'
                            for c in _item["contratos"]
                        )
                        _cpf_d = str(_item["cpf"]).strip().zfill(11)
                        _cpf_d_mask = f"{_cpf_d[:3]}.***.***-**"
                        _nome_d = str(_item["nome"]).strip().split()
                        _nome_d_mask = (_nome_d[0].capitalize() + (" *" if len(_nome_d) > 1 else "")) if _nome_d else "—"

                        _hist_leads = _dup_hist.get(_cpf_d, {}).get("leads", [])
                        if _hist_leads:
                            _dup_det_hdr = (
                                "<div class='pj-det-row' style='font-size:.7em;color:#475569;font-weight:600;"
                                "letter-spacing:.04em;text-transform:uppercase;border-top:none'>"
                                "<span class='pj-det-dt'>CCB</span>"
                                "<span class='pj-det-n'>C&#243;digo do Lead</span>"
                                "<span class='pj-det-n'>Data do Lead</span>"
                                "<span class='pj-det-n'>Data Desembolso</span>"
                                "</div>"
                            )
                            _dup_det_body = "".join(
                                f"<div class='pj-det-row'>"
                                f"<span class='pj-det-dt' style='font-family:monospace'>{_mask_ccb_dup(_lh.get('ccb',''))}</span>"
                                f"<span class='pj-det-n'>{_lh.get('codigo','—')}</span>"
                                f"<span class='pj-det-n'>{_fmt_d_dup(_lh.get('data_criacao'))}</span>"
                                f"<span class='pj-det-n'>{_fmt_d_dup(_lh.get('data_desembolso'))}</span>"
                                f"</div>"
                                for _lh in _hist_leads
                            )
                            _nome_cell = (
                                f"<details class='pj-det'><summary>{_nome_d_mask}</summary>"
                                f"{_dup_det_hdr}{_dup_det_body}</details>"
                            )
                        else:
                            _nome_cell = _nome_d_mask

                        _dup_rows.append(
                            f'<tr class="{_rc}">'
                            f'<td style="font-family:monospace">{_cpf_d_mask}</td>'
                            f'<td>{_nome_cell}</td>'
                            f'<td class="r">{len(_item["contratos"])}</td>'
                            f'<td class="r">{_brl2(_item["total"])}</td>'
                            f'<td style="font-size:.82em;line-height:1.5">{_conts}</td>'
                            f'</tr>'
                        )
                    _dup_html = (
                        '<div class="dtbl-title" style="color:#f59e0b">&#9888; CPFs com múltiplos contratos &mdash; total liberado &gt; R$&nbsp;15k</div>'
                        '<div class="dtbl-wrap"><table class="dtbl">'
                        '<thead><tr>'
                        '<th>CPF</th><th>Nome</th><th class="r">Contratos</th>'
                        '<th class="r">Liberado</th><th>Detalhes</th>'
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

                # ── Clientes aprovados com total histórico > 15k ──────────────────────────
                _cpfs_periodo: set = set()
                for _dj_p in dias_raw:
                    for _cpf_k in (_dj_p.get("aprovados_por_cpf") or {}).keys():
                        if _cpf_k:
                            _cpfs_periodo.add(_cpf_k)

                if _cpfs_periodo:
                    # Agrega todos os dias, deduplicando por lead ID para evitar dupla contagem
                    _aprov_glob: dict = {}
                    for _dd_all in datas:
                        _dj_all = carregar_dia(_dd_all)
                        if not _dj_all:
                            continue
                        for _cpf_k, _vk in (_dj_all.get("aprovados_por_cpf") or {}).items():
                            if not _cpf_k:
                                continue
                            if _cpf_k not in _aprov_glob:
                                _aprov_glob[_cpf_k] = {"nome": _vk.get("nome", ""), "valor": 0.0, "liberado": 0.0, "_seen": set(), "leads": []}
                            if not _aprov_glob[_cpf_k]["nome"] and _vk.get("nome"):
                                _aprov_glob[_cpf_k]["nome"] = _vk["nome"]
                            for _lv in (_vk.get("leads") or []):
                                if _ori_ativas and (_lv.get("origem") or "Outros") not in _ori_ativas:
                                    continue
                                _lid = _lv.get("id", "")
                                if _lid and _lid in _aprov_glob[_cpf_k]["_seen"]:
                                    continue
                                if _lid:
                                    _aprov_glob[_cpf_k]["_seen"].add(_lid)
                                _aprov_glob[_cpf_k]["valor"]    += _lv.get("valor", 0.0)
                                _aprov_glob[_cpf_k]["liberado"] += _lv.get("liberado", 0.0)
                                _aprov_glob[_cpf_k]["leads"].append(_lv)

                    def _mask_cpf(c):
                        c = str(c).strip().zfill(11)
                        return f"{c[:3]}.***.***-**"

                    def _mask_nome(n):
                        parts = str(n).strip().split()
                        if not parts:
                            return "—"
                        return parts[0].capitalize() + (" *" if len(parts) > 1 else "")

                    def _mask_ccb(c):
                        c = str(c).strip()
                        if len(c) <= 4:
                            return c
                        return c[:3] + "*" * (len(c) - 4) + c[-1]

                    _brl3 = lambda x: "R$ " + f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

                    _alto_valor = sorted(
                        [
                            (cpf, d)
                            for cpf, d in _aprov_glob.items()
                            if cpf in _cpfs_periodo and d["liberado"] > 15_000
                        ],
                        key=lambda x: x[1]["liberado"],
                        reverse=True,
                    )

                    if _alto_valor:
                        _av_rows = ""
                        for _cpf_v, _dv in _alto_valor:
                            def _fmt_d(d):
                                if not d:
                                    return "—"
                                try:
                                    return datetime.strptime(d, "%Y%m%d").strftime("%d/%m/%Y")
                                except ValueError:
                                    return d
                            _det_hdr = (
                                "<div class='pj-det-row' style='font-size:.7em;color:#475569;font-weight:600;"
                                "letter-spacing:.04em;text-transform:uppercase;border-top:none'>"
                                "<span class='pj-det-dt'>CCB</span>"
                                "<span class='pj-det-n'>C&#243;digo do Lead</span>"
                                "<span class='pj-det-n'>Data do Lead</span>"
                                "<span class='pj-det-n'>Data Desembolso</span>"
                                "</div>"
                            )
                            _det_inner = _det_hdr + "".join(
                                f"<div class='pj-det-row'>"
                                f"<span class='pj-det-dt' style='font-family:monospace'>{_mask_ccb(_ld.get('ccb',''))}</span>"
                                f"<span class='pj-det-n'>{_ld.get('codigo','—')}</span>"
                                f"<span class='pj-det-n'>{_fmt_d(_ld.get('data_criacao'))}</span>"
                                f"<span class='pj-det-n'>{_fmt_d(_ld.get('data_desembolso'))}</span>"
                                f"</div>"
                                for _ld in _dv["leads"]
                            )
                            _name_cell = (
                                f"<details class='pj-det'><summary>{_mask_nome(_dv['nome'])}</summary>"
                                f"{_det_inner}</details>"
                            )
                            _av_rows += (
                                f"<tr>"
                                f"<td class='pj-lbl'>{_name_cell}</td>"
                                f"<td class='pj-n' style='font-family:monospace'>{_mask_cpf(_cpf_v)}</td>"
                                f"<td class='pj-n'>{len(_dv['leads'])}</td>"
                                f"<td class='pj-n'>{_brl3(_dv['valor'])}</td>"
                                f"<td class='pj-n'>{_brl3(_dv['liberado'])}</td>"
                                f"</tr>"
                            )
                        _av_html = f"""
    <style>
    .av-wrap{{overflow-x:auto;margin:6px 0 18px}}
    .av-tbl{{width:100%;border-collapse:collapse;font-size:.91em}}
    .av-tbl th{{background:#1c1a17;color:#94a3b8;font-weight:600;padding:9px 16px;
                text-align:left;border-bottom:2px solid #272420;white-space:nowrap}}
    .av-tbl th.pj-n{{text-align:right}}
    .av-tbl td{{padding:7px 16px;border-bottom:1px solid #1c1a17;color:#e2e8f0}}
    .av-tbl tr:hover td{{background:#1a1815}}
    .pj-lbl{{color:#cbd5e1;white-space:nowrap}}
    .pj-n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
    .pj-det{{cursor:pointer}}
    .pj-det summary{{list-style:none;display:flex;align-items:center;gap:6px;
                     cursor:pointer;color:#cbd5e1;white-space:nowrap}}
    .pj-det summary::-webkit-details-marker{{display:none}}
    .pj-det summary::before{{content:'▶';font-size:.6em;color:#64748b;
                              transition:transform .15s;flex-shrink:0}}
    .pj-det[open] summary::before{{transform:rotate(90deg)}}
    .pj-det-row{{display:flex;gap:16px;padding:3px 0 3px 18px;font-size:.82em;
                 color:#94a3b8;border-top:1px solid #272420}}
    .pj-det-dt{{min-width:120px;color:#64748b}}
    .pj-det-n{{min-width:80px}}
    </style>
    <div class="dtbl-title" style="color:#f59e0b">&#9888; Clientes aprovados com total liberado &gt; R$&nbsp;15k (histórico completo)</div>
    <div class="av-wrap"><table class="av-tbl">
    <thead><tr>
      <th>Nome</th><th>CPF</th>
      <th class="pj-n">Contratos</th>
      <th class="pj-n">Total Contratado</th>
      <th class="pj-n">Total Liberado</th>
    </tr></thead>
    <tbody>{_av_rows}</tbody>
    </table></div>"""
                        st.markdown(_av_html, unsafe_allow_html=True)

            # ── 6. Distribuição por Status ────────────────────────────────────────────────
            if _show("evolucao_leads"):

                st.markdown('<div class="sec">Distribuição por Status</div>', unsafe_allow_html=True)
            
                col_d, col_f = st.columns(2)
                with col_d:
                    fig = _fig_donut(f.get("_d_status", {}))
                    if fig:
                        st.plotly_chart(fig, width='stretch', config=_CONF)
                with col_f:
                    fig = _fig_funil_rico(f)
                    if fig:
                        st.plotly_chart(fig, width='stretch', config=_CONF)
            
            # ── 7. Status Novo — CTPS ─────────────────────────────────────────────────────

            # OCULTA temporariamente (pedido): 'CTPS — Aguardando clique' fica SUPERESTIMADO e
            # 'CTPS — Bot WhatsApp iniciado' SUBESTIMADO, pois só sabemos do clique quando o lead
            # entra no fluxo do S-Works (aceite dos termos), nao no clique real no WhatsApp.
            # Para reativar a secao 7: trocar para _MOSTRAR_SEC7_CTPS = True.
            _MOSTRAR_SEC7_CTPS = False
            if _MOSTRAR_SEC7_CTPS:
                st.markdown('<div class="sec">7. Status Novo — CTPS</div>', unsafe_allow_html=True)
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

            # ── 7. Evolução Temporal ──────────────────────────────────────────────────────
            if _show("evolucao_leads"):

                st.markdown('<div class="sec">Evolução Temporal</div>', unsafe_allow_html=True)
            
                # Botões (1 linha, multi-seleção) p/ mostrar/ocultar cada status no gráfico.
                # Mantidos sempre os 9 visíveis; toggle roda só o fragment (não recarrega a página).
                _EVO_ORDEM = [3, 4, 5, 2, 0, 7, 8, 1, 6]   # ordem dos status = ordem das linhas
                _EVO_BTNS = ["TOTAL"] + _EVO_ORDEM         # 1º botão = linha do Total (soma dos status)
                if "evo_status_sel" not in st.session_state:
                    st.session_state["evo_status_sel"] = list(_EVO_ORDEM)   # 9 status on; Total off por padrão

                @st.fragment
                def _evo_frag():
                    _sel = set(st.session_state.get("evo_status_sel", _EVO_ORDEM))
                    _cols = st.columns(10, gap="small")
                    for _i, _s in enumerate(_EVO_BTNS):
                        _on = _s in _sel
                        _lbl = "Total" if _s == "TOTAL" else _STATUS_NOMES.get(_s, str(_s))
                        if _cols[_i].button(_lbl,
                                            key=f"evo_btn_{_s}",
                                            type=("primary" if _on else "secondary"),
                                            width='stretch'):
                            if _on:
                                _sel.discard(_s)
                            else:
                                _sel.add(_s)
                            st.session_state["evo_status_sel"] = [x for x in _EVO_BTNS if x in _sel]
                            st.rerun(scope="fragment")
                    _sel_now = st.session_state.get("evo_status_sel", _EVO_ORDEM)
                    _fig = _fig_evolucao(agg, n_dias, dias_raw=dias_raw, datas_sel=datas_sel,
                                         statuses_sel=_sel_now) if _sel_now else None
                    if _fig:
                        st.plotly_chart(_fig, width='stretch', config=_CONF)
                    else:
                        st.caption("Selecione ao menos um status nos botões acima para ver as linhas.")

                _evo_frag()
            
            if _show("evolucao_leads"):
                @st.fragment
                def _heatmap_frag():
                    _data_ref_nm = _default_ref_nm
                    # Heatmap: ultima_atualizacao por etapa. Janela de 15 dias p/ capturar
                    # leads antigos ainda nao-terminais e preencher as faixas mais longas
                    # (4-5d, >5d) — leads parados ha dias vivem em JSONs antigos. Historicos
                    # ficam em cache permanente, entao so pesa no 1o load da sessao.
                    _hm_ts: dict = {}
                    for _dhm in range(15):
                        _shm = (_data_ref_nm - timedelta(days=_dhm)).strftime("%Y%m%d")
                        if _shm not in datas:
                            continue
                        _djhm = carregar_dia(_shm)
                        if not _djhm:
                            continue
                        for _tsh, _lst in (_djhm.get("heatmap_ts", {}) or {}).items():
                            _hm_ts.setdefault(_tsh, []).extend(_lst)
                    # ── Heatmap: tempo desde a ultima_atualizacao, por etapa ──────────
                    _FAIXAS = [
                        ("<1h", 0, 1), ("1–3h", 1, 3), ("3–6h", 3, 6), ("6–12h", 6, 12),
                        ("12–24h", 12, 24), ("1–2d", 24, 48), ("2–3d", 48, 72),
                        ("3–4d", 72, 96), ("4–5d", 96, 120), (">5d", 120, None),
                    ]
                    def _faixa_idx(h):
                        for _i, (_fl, _lo, _hi) in enumerate(_FAIXAS):
                            if h >= _lo and (_hi is None or h < _hi):
                                return _i
                        return len(_FAIXAS) - 1
                    _hm_mat = {}
                    _hm_leads: dict = {}   # etapa -> {cod: faixa_idx} (dedup por cod, snapshot mais recente 1o)
                    for _tsh, _lst in _hm_ts.items():
                        if _tsh == "BLOQUEIO_TEMPORARIO":
                            continue  # BT = countdown de 24h (nao staleness); contagem diverge da tabela
                        _row = [0] * len(_FAIXAS)
                        _seen = _hm_leads.setdefault(_tsh, {})
                        for _entry in _lst:
                            # Compat: formato novo = [ts, codigo]; antigo = string ts.
                            if isinstance(_entry, (list, tuple)):
                                _tsraw = _entry[0] if _entry else ""
                                _cod   = str(_entry[1]).strip() if len(_entry) > 1 else ""
                            else:
                                _tsraw, _cod = _entry, ""
                            try:
                                _dt = datetime.fromisoformat(str(_tsraw)[:19])
                            except (ValueError, TypeError):
                                continue
                            _idade_h = max(0.0, (_now_brt_nm - _dt).total_seconds() / 3600.0)
                            _bi = _faixa_idx(_idade_h)
                            _row[_bi] += 1
                            if _cod and _cod not in _seen:
                                _seen[_cod] = (_bi, str(_tsraw)[:19], round(_idade_h / 24.0, 2), _entry)
                        if sum(_row):
                            _hm_mat[_tsh] = _row
                    if _hm_mat:
                        _hm_max = max(max(r) for r in _hm_mat.values()) or 1
                        _N_FAIXAS = len(_FAIXAS)
                        # ── Trilha C: anomalia vs referência (30d por hora × tipo-de-dia) ──────
                        # DESATIVADA por ora (_ANOM_ATIVO=False): a referência ainda é prematura —
                        # a mudança de regime ~02/08 (coletor passou a 24h) contamina os horários
                        # de madrugada, e as faixas longas (>5d/4-5d) sofrem o artefato de
                        # congelamento dos JSONs de 9-15 dias atrás. A coleta de snapshots e o
                        # recompute diário seguem rodando (a referência amadurece sozinha).
                        # Reativar quando a janela 30d for majoritariamente pós-regime (~set) E o
                        # artefato das faixas longas for tratado. Limiares ajustáveis abaixo.
                        _ANOM_ATIVO = False
                        _ANOM_MIN_N, _ANOM_MIN_CNT, _ANOM_K_MAD = 8, 3, 3.0
                        _ref_map  = (_carregar_referencia() or {}).get("ref", {}) if _ANOM_ATIVO else {}
                        _anom_cls = "util" if _now_brt_nm.weekday() < 5 else "fds"
                        _anom_hr  = str(_now_brt_nm.hour)
                        def _hm_anom(_t, _i, v):
                            """(flagged, tooltip) — contagem ao vivo v vs referência da etapa `_t` /
                            faixa `_i` na classe+hora atuais. Sinaliza excesso robusto: acima de
                            max(p90, med + K·MAD). Sem referência suficiente → não sinaliza.
                            Governado por _ANOM_ATIVO (desativado por ora — ver comentário acima)."""
                            if not _ANOM_ATIVO:
                                return False, ""
                            _s = ((((_ref_map.get(_t) or {}).get(str(_i)) or {}).get(_anom_cls)) or {}).get(_anom_hr)
                            if not _s or _s.get("n", 0) < _ANOM_MIN_N or v < _ANOM_MIN_CNT:
                                return False, ""
                            _med = _s.get("med", 0.0); _mad = _s.get("mad", 0.0); _p90 = _s.get("p90", 0.0)
                            _upper = max(_p90, _med + _ANOM_K_MAD * _mad)
                            if v > _upper:
                                _cl = "útil" if _anom_cls == "util" else "fim de semana"
                                return True, (f"Anomalia: atual {v} · normal ~{_med:.0f} "
                                              f"p/ {_anom_hr}h em dia {_cl}")
                            return False, ""
                        def _hm_base(_i):
                            # verde (2 primeiras) → amarelo (3 seguintes) → vermelho (restantes)
                            # → cinza escuro na última faixa (>5d). Tonalidade varia pela contagem.
                            if _i >= _N_FAIXAS - 1:
                                return (82, 82, 91)      # >5d: cinza escuro
                            if _i <= 1:
                                return (34, 197, 94)     # verde
                            if _i <= 4:
                                return (254, 197, 46)    # amarelo
                            return (239, 68, 68)         # vermelho
                        def _hm_cell(v, _i, _t):
                            if not v:
                                return '<td class="hm-c hm-0">·</td>'
                            _r, _g, _b = _hm_base(_i)
                            _a = 0.12 + 0.88 * (v / _hm_max)
                            _fl, _tp = _hm_anom(_t, _i, v)
                            _cls = "hm-c hm-anom" if _fl else "hm-c"
                            _tt  = (' title="%s"' % _tp) if _tp else ""
                            return '<td class="%s" style="background:rgba(%d,%d,%d,%.2f)"%s>%d</td>' % (
                                _cls, _r, _g, _b, _a, _tt, v)
                        def _hm_lk_color(_i):
                            # cor da faixa; >5d (cinza escuro) clareia p/ legibilidade do link
                            if _i >= _N_FAIXAS - 1:
                                return "#94a3b8"
                            _r, _g, _b = _hm_base(_i)
                            return "rgb(%d,%d,%d)" % (_r, _g, _b)
                        def _hm_links(_seen):
                            # até 15 links, distribuídos ~igualmente entre verde/amarelo/vermelho
                            if not _seen:
                                return ""
                            _grp = {0: [], 1: [], 2: []}   # 0=verde(faixas 0-1) 1=amarelo(2-4) 2=vermelho(5+)
                            for _c, _v in _seen.items():
                                _bi = _v[0] if isinstance(_v, (list, tuple)) else _v
                                _grp[0 if _bi <= 1 else 1 if _bi <= 4 else 2].append((_bi, _c))
                            for _gk in _grp:
                                _grp[_gk].sort(key=lambda x: -x[0])   # mais parado primeiro
                            _sel   = {_gk: _grp[_gk][:5] for _gk in _grp}
                            _extra = {_gk: _grp[_gk][5:] for _gk in _grp}
                            _tot = sum(len(v) for v in _sel.values()); _gk = 0
                            while _tot < 15 and any(_extra.values()):
                                if _extra[_gk]:
                                    _sel[_gk].append(_extra[_gk].pop(0)); _tot += 1
                                _gk = (_gk + 1) % 3
                            _picked = sorted(_sel[0] + _sel[1] + _sel[2], key=lambda x: x[0])
                            _lines = "".join(
                                f"<a class='hm-lk' style='color:{_hm_lk_color(_bi)}' target='_blank' "
                                f"href='https://sworks.zilicorp.net/Processo?codigo={_c}'>#{_c}"
                                f"<span class='hm-lk-fx'>{_FAIXAS[_bi][0]}</span></a>"
                                for _bi, _c in _picked
                            )
                            _resto = len(_seen) - len(_picked)
                            _mais  = f"<div class='hm-lk-mais'>+{_resto} lead(s) nesta etapa</div>" if _resto > 0 else ""
                            return f"<div class='hm-lks'>{_lines}{_mais}</div>"
                        # ── Download por etapa (template Operações + Faixa + Dias na etapa) ──
                        _HM_DL_HEADER = ("Lead;Link S-Works;Data do Lead;Origem;CPF;Nome;E-mail;"
                                         "Telefone;Data de Nascimento;Valor do Emprestimo Solicitado;"
                                         "Numero de Parcelas Solicitado;Faixa;Dias na etapa")
                        def _hm_fmt_data(_s):
                            _s = str(_s or "").strip()
                            if not _s:
                                return ""
                            _m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", _s)          # ISO
                            if _m:
                                return f"{_m.group(3)}/{_m.group(2)}/{_m.group(1)}"
                            _m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", _s)          # já BR
                            if _m:
                                return _m.group(0)
                            _m = re.match(r"^(\d{2})(\d{2})(\d{4})", _s)            # DDMMYYYY
                            if _m:
                                return f"{_m.group(1)}/{_m.group(2)}/{_m.group(3)}"
                            return _s[:10]
                        def _hm_xlsx_b64(_seen):
                            # .xlsx no template de Operações + Faixa + Dias na etapa. Todas as
                            # células saem como TEXTO (openpyxl grava str como célula de texto),
                            # então CPF/Telefone preservam os dígitos e o Excel não converte em
                            # número/notação científica — sem precisar de apóstrofo.
                            def _f(_e, _i):
                                return str(_e[_i]).strip() if isinstance(_e, (list, tuple)) and len(_e) > _i and _e[_i] else ""
                            def _dias_of(_v):
                                return (_v[2] if isinstance(_v, (list, tuple)) and len(_v) > 2 else 0) or 0
                            _wb = Workbook(write_only=True)
                            _ws = _wb.create_sheet("Leads")
                            _ws.append(_HM_DL_HEADER.split(";"))
                            for _c, _v in sorted(_seen.items(), key=lambda kv: -_dias_of(kv[1])):
                                _bi   = _v[0] if isinstance(_v, (list, tuple)) else _v
                                _dias = _v[2] if isinstance(_v, (list, tuple)) and len(_v) > 2 else ""
                                _e    = _v[3] if isinstance(_v, (list, tuple)) and len(_v) > 3 else None
                                _ws.append([
                                    str(_c), f"https://sworks.zilicorp.net/Processo?codigo={_c}",
                                    _hm_fmt_data(_f(_e, 2)), _f(_e, 3), _f(_e, 4), _f(_e, 5),
                                    _f(_e, 6), _f(_e, 7), _hm_fmt_data(_f(_e, 8)), _f(_e, 9),
                                    _f(_e, 10), _FAIXAS[_bi][0], str(_dias).replace(".", ","),
                                ])
                            _buf = BytesIO(); _wb.save(_buf)
                            return base64.b64encode(_buf.getvalue()).decode()
                        # ── Autorização de download: senha 1x na sessão via 🔒 discreto ──
                        try:
                            _hm_sec = st.secrets["senha_download_heatmap"]
                        except Exception:
                            _hm_sec = None
                        _hm_auth = bool(st.session_state.get("hm_dl_ok"))
                        _ct, _cq = st.columns([10, 1])
                        with _ct:
                            st.markdown('<div class="sec" style="font-size:.95em;margin-top:6px">Tempo desde a última atualização (por etapa)</div>', unsafe_allow_html=True)
                        with _cq:
                            with st.popover("🔒", help="Liberar download dos leads (senha)"):
                                if not _hm_sec:
                                    st.caption("Configure o secret `senha_download_heatmap`.")
                                elif _hm_auth:
                                    st.caption("✓ Downloads liberados nesta sessão.")
                                else:
                                    _pw = st.text_input("Senha p/ baixar leads", type="password", key="hm_dl_pw")
                                    if _pw and _pw == _hm_sec:
                                        st.session_state["hm_dl_ok"] = True
                                        _hm_auth = True
                                    elif _pw:
                                        st.caption("Senha incorreta.")
                        _hrows = ""
                        for _t in sorted(_hm_mat, key=lambda t: (_etapa_key(t), -sum(_hm_mat[t]))):
                            _lblt    = _TIPO_LABEL_MAP.get(_t, _t)
                            _leads_t = _hm_leads.get(_t, {})
                            _lks     = _hm_links(_leads_t)
                            _cell    = (f"<details class='hm-det'><summary>{_lblt}</summary>{_lks}</details>"
                                        if _lks else _lblt)
                            if _hm_auth and _leads_t:
                                _dl = ("data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,"
                                       + _hm_xlsx_b64(_leads_t))
                                _dlcell = (f'<td class="hm-dl"><a class="hm-dlbtn" download="leads_{_t}.xlsx" '
                                           f'href="{_dl}" title="Baixar {len(_leads_t)} lead(s) — template Operações">&#8595;</a></td>')
                            else:
                                _dttl = "Sem dados ainda (aguardando exportação)" if not _leads_t else "Libere no cadeado acima"
                                _dlcell = f'<td class="hm-dl"><span class="hm-dlbtn hm-dlbtn-off" title="{_dttl}">&#8595;</span></td>'
                            _hrows += ('<tr><td class="hm-lbl">' + _cell + '</td>'
                                       + "".join(_hm_cell(v, _ci, _t) for _ci, v in enumerate(_hm_mat[_t]))
                                       + '<td class="hm-tot">' + str(sum(_hm_mat[_t])) + '</td>'
                                       + _dlcell + '</tr>')
                        _hhead = "".join('<th class="hm-c">' + _fl + '</th>' for _fl, _, _ in _FAIXAS)
                        _hm_css = """
                <style>
                .hm-wrap{overflow-x:auto;margin:2px 0 18px}
                .hm-tbl{border-collapse:collapse;font-size:.85em}
                .hm-tbl th{background:#1c1a17;color:#94a3b8;font-weight:600;padding:6px 9px;text-align:center;border-bottom:2px solid #272420;white-space:nowrap}
                .hm-tbl th.hm-lbl-h{text-align:left}
                .hm-lbl{color:#cbd5e1;white-space:nowrap;padding:5px 12px 5px 4px;border-bottom:1px solid #1c1a17}
                .hm-c{text-align:center;padding:5px 9px;border-bottom:1px solid #1c1a17;color:#e2e8f0;font-variant-numeric:tabular-nums;min-width:46px}
                .hm-0{color:#3f3b35}
                .hm-anom{box-shadow:inset 0 0 0 2px #ef4444;font-weight:700;cursor:help}
                .hm-tot{text-align:center;padding:5px 11px;color:#FEC52E;font-weight:700;border-bottom:1px solid #1c1a17;border-left:2px solid #272420}
                .hm-det summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:6px}
                .hm-det summary::-webkit-details-marker{display:none}
                .hm-det summary::before{content:'\\25B6';font-size:.6em;color:#64748b;transition:transform .15s;flex-shrink:0}
                .hm-det[open] summary::before{transform:rotate(90deg)}
                .hm-lks{padding:4px 0 4px 16px;white-space:normal}
                .hm-lk{display:flex;gap:8px;align-items:baseline;padding:2px 0;font-size:.92em;text-decoration:none;font-variant-numeric:tabular-nums}
                .hm-lk:hover{text-decoration:underline}
                .hm-lk-fx{color:#64748b;font-size:.82em}
                .hm-lk-mais{color:#64748b;font-size:.8em;padding:4px 0 0 2px}
                .hm-dl-h{border-left:1px solid #272420;min-width:30px}
                .hm-dl{text-align:center;padding:4px 8px;border-bottom:1px solid #1c1a17;border-left:1px solid #272420}
                .hm-dlbtn{display:inline-flex;align-items:center;justify-content:center;width:20px;height:18px;border:1px solid #333;border-radius:4px;color:#94a3b8;text-decoration:none;font-size:.8em;background:#17150f;line-height:1}
                .hm-dlbtn:hover{border-color:#FEC52E;color:#FEC52E}
                .hm-dlbtn-off{opacity:.28;cursor:not-allowed}
                </style>
                """
                        _anom_leg = ("  <span style='color:#ef4444'>Contorno vermelho</span> = acima do normal para o horário (referência de 30 dias por hora × dia útil/fim de semana)."
                                     if _ref_map else "")
                        st.markdown(
                            _hm_css
                            + "<p style='color:#475569;font-size:.78em;margin:0 0 6px'>Nº de leads por faixa de tempo desde a última mudança de status/etapa — atualiza com o \"agora\". Faixas à direita = candidatos a intervenção. ↓ = baixar os leads da etapa (libere no 🔒 ao lado do título)." + _anom_leg + "</p>"
                            + '<div class="hm-wrap"><table class="hm-tbl"><thead><tr><th class="hm-lbl-h">Etapa</th>'
                            + _hhead + '<th class="hm-c">Total</th><th class="hm-c hm-dl-h">&#8595;</th></tr></thead><tbody>'
                            + _hrows + "</tbody></table></div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown("<p style='color:#475569;font-size:.78em'>Heatmap de tempo: aguardando os primeiros dados de <code>ultima_atualizacao</code> (aparece após a próxima coleta).</p>", unsafe_allow_html=True)
                _heatmap_frag()

            # ── 8. Perfil Financeiro — Aprovados ─────────────────────────────────────────
            if _show("leads_aprovados"):

                st.markdown('<div class="sec">Perfil Financeiro — Aprovados</div>', unsafe_allow_html=True)
            
                html_fin = _html_tabela_financeira(fin)
                if html_fin:
                    st.markdown(html_fin, unsafe_allow_html=True)
                    if n_dias > 1:
                        st.caption("*Mediana = média ponderada das medianas diárias")
            
                fig = _fig_histograma(agg.get("valores_contratacao", []))
                if fig:
                    st.plotly_chart(fig, width='stretch', config=_CONF)

                # Distribuição de taxa — taxa média por empregador por dia, agregada pelo dash
                _dist_taxa = agg.get("taxa_dist", {})
                if _dist_taxa:
                        _n_taxa_total = sum(_dist_taxa.values())
                        _taxa_sorted = dict(sorted(
                            ((f"{float(k):.2f}".replace(".", ",") + "% a.m.", v)
                             for k, v in _dist_taxa.items()),
                            key=lambda x: float(x[0].replace(",", ".").replace("% a.m.", ""))
                        ))
                        fig_taxa = _fig_barras_h(
                            _taxa_sorted,
                            "Distribuição de Taxa — Aprovados",
                            "#3b82f6",
                            n=50,
                            pct_base=_n_taxa_total,
                            show_abs=True,
                        )
                        if fig_taxa:
                            st.plotly_chart(fig_taxa, width='stretch', config=_CONF)

                # Distribuição do número de parcelas — aprovados
                _fig_pz_ap = _fig_dist_prazo(
                    agg.get("prazo_dist", {}), "Distribuição de Nº de Parcelas — Aprovados")
                if _fig_pz_ap:
                    st.plotly_chart(_fig_pz_ap, width='stretch', config=_CONF)

            # ── 9. Etapa de Reprovação ────────────────────────────────────────────────────
            if _show("leads_reprovados"):

                st.markdown('<div class="sec">Etapa de Reprovação</div>', unsafe_allow_html=True)
            
                n_rep    = f.get("reprovados", 0)
                etapas_d = agg.get("etapas", {})
                etapa_motivos_d = agg.get("etapa_motivos", {})
            
                # Diagrama interativo do Workflow 166 — drill-down por CLIQUE na caixa (JS,
                # client-side, instantâneo). Clicar na caixa 'Motor de Crédito' entra nela; a
                # setinha ◂ discreta no topo-esquerdo volta. Documento HTML completo (renderiza
                # de forma confiável no iframe, ao contrário do fragmento HTML anterior).
                # Diagrama do Workflow 166 — drill-down por clique SEM recarregar a página.
                # As caixas são cards numa faixa com scroll horizontal; o Motor de Crédito é um
                # botão (clicável) dentro de um @st.fragment → só a seção 9 re-renderiza (entrar
                # E voltar). (components.html/iframe vem vazio neste deploy → sem JS.)
                _WF166_FASES = ["Inicializa Dados", "Motor de Crédito", "Cálculo Proposta",
                    "Cadastro Proposta", "Formalização", "Atualização Dados Cliente", "Obter CCB",
                    "Envia CCB Único", "Averbação Dataprev", "Nuvidio Antifraude",
                    "Envio de Informações Dataprev", "Pagamento Pix", "Atualizar Tesouraria",
                    "Atualizar Portal de Crédito", "Contratar o Seguro", "Aprovação Processo"]
                _WF166_MOTOR = ["Validações Iniciais", "Token", "Dataprev Vínculos",
                    "Dataprev Dados do Trabalhador", "RF PJ", "RF PF", "SCR", "BDC PJ Dados Básicos",
                    "BDC PJ Dados Unificados", "PH3A PJ", "BDC PF Dados Unificados",
                    "BDC PF Risco Financeiro", "BDC PF Dados Básicos", "PH3A PF", "Decisão Motor"]
                _WF166_CSS = """<style>
                .st-key-wf166flow [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;overflow-x:auto;gap:8px;padding:12px 12px 16px;border:1px solid #2a2620;border-radius:10px;background:#100e0a}
                .st-key-wf166flow [data-testid="stColumn"]{min-width:150px!important;width:150px!important;flex:0 0 150px!important}
                .st-key-wf166flow [data-testid="stColumn"] [data-testid="stVerticalBlock"]{gap:0!important}
                .wfbox{background:#15130e;border:1px solid #332e25;border-radius:9px;padding:10px 11px;min-height:66px;display:flex;align-items:center;color:#e2e8f0;font-size:12px;font-weight:600;line-height:1.25}
                .wfbox.sub{background:#141019;border-color:rgba(99,102,241,0.35);color:#c4b5fd}
                .wfbox.dec{background:#1a1420;border-color:rgba(167,139,250,0.55);color:#d8b4fe}
                .st-key-wf166_motor button{min-height:66px;width:100%;white-space:normal;background:rgba(99,102,241,0.12)!important;border:1.5px solid #6366f1!important;color:#c7d2fe!important;font-size:12px!important;font-weight:700!important;border-radius:9px!important;box-shadow:0 0 0 3px rgba(99,102,241,0.07)}
                .st-key-wf166_motor button:hover{background:rgba(99,102,241,0.22)!important;border-color:#818cf8!important;color:#e0e7ff!important}
                .st-key-wf166_back button{padding:2px 11px!important;min-height:0;color:#a5b4fc!important;background:#15130e!important;border:1px solid #332e25!important;border-radius:7px!important}
                .st-key-wf166_back button:hover{border-color:#6366f1!important;background:#1a1726!important;color:#c7d2fe!important}
                </style>"""

                @st.fragment
                def _wf166_frag():
                    st.session_state.setdefault("wf166_lvl", "root")
                    st.markdown(_WF166_CSS, unsafe_allow_html=True)
                    if st.session_state["wf166_lvl"] == "motor":
                        _bk, _cr = st.columns([0.55, 9], vertical_alignment="center")
                        with _bk:
                            if st.button("◂", key="wf166_back", help="Voltar ao nível externo"):
                                st.session_state["wf166_lvl"] = "root"
                                st.rerun(scope="fragment")
                        with _cr:
                            st.markdown('<div style="color:#94a3b8;font-size:13px;">&#128194; Esteira Zili'
                                        '&nbsp;&#8250;&nbsp; <b style="color:#c7d2fe;">Motor de Cr&#233;dito</b></div>',
                                        unsafe_allow_html=True)
                    else:
                        st.markdown('<div style="color:#94a3b8;font-size:13px;margin-bottom:2px;">&#128194; Esteira Zili '
                                    '&#183; <span style="color:#64748b;">n&#237;vel externo (16 fases) &#183; clique no '
                                    'Motor de Cr&#233;dito para entrar</span></div>', unsafe_allow_html=True)
                    with st.container(key="wf166flow"):
                        if st.session_state["wf166_lvl"] == "motor":
                            _cols = st.columns(len(_WF166_MOTOR))
                            for _i, _n in enumerate(_WF166_MOTOR):
                                with _cols[_i]:
                                    _cls = "wfbox dec" if _n == "Decisão Motor" else "wfbox sub"
                                    st.markdown('<div class="' + _cls + '">' + _n + '</div>', unsafe_allow_html=True)
                        else:
                            _cols = st.columns(len(_WF166_FASES))
                            for _i, _n in enumerate(_WF166_FASES):
                                with _cols[_i]:
                                    if _n == "Motor de Crédito":
                                        if st.button("Motor de Crédito", key="wf166_motor",
                                                     width='stretch'):
                                            st.session_state["wf166_lvl"] = "motor"
                                            st.rerun(scope="fragment")
                                    else:
                                        st.markdown('<div class="wfbox">' + _n + '</div>', unsafe_allow_html=True)
                _wf166_frag()
            
                # 2 abas: Visão geral | Visão de Funil
                if etapas_d and n_rep > 0:
                    tab_g, tab_f = st.tabs(["Visão geral", "Visão de Funil"])

                    # Agrupa por conceito: cada workflow com seu nome; conceito presente nos
                    # dois (período misto) vira "nome_v38 | nome_v39" numa linha só.
                    _etapas_c, _motivos_c, _ordem_c = _combinar_etapas_conceito(etapas_d, etapa_motivos_d)

                    with tab_g:
                        _order_idx = {e: i for i, e in enumerate(_ordem_c)}
                        ordered = sorted(
                            [(e, _etapas_c.get(e, 0)) for e in _etapas_c if _etapas_c.get(e, 0) > 0],
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
                        st.plotly_chart(fig_g, width='stretch', config=_CONF)

                        tbl_g = _html_tabela_etapa_motivo(_motivos_c, _etapas_c, n_rep, order=_ordem_c)
                        if tbl_g:
                            st.markdown(tbl_g, unsafe_allow_html=True)

                    with tab_f:
                        result_f = _fig_funil_etapa(_etapas_c, n_rep, order=_ordem_c)
                        if result_f:
                            fig_f, rows_f = result_f
                            st.plotly_chart(fig_f, width='stretch', config=_CONF)
                            tbl_resumo = _html_tabela_resumo_funil(rows_f)
                            if tbl_resumo:
                                st.markdown(tbl_resumo, unsafe_allow_html=True)
                else:
                    st.info("Sem dados de etapas (JSONs desta data ainda não possuem o campo).")
            
            # ── 10. Motivos de Reprovação ──────────────────────────────────────────────────
            if _show("leads_reprovados"):

                st.markdown('<div class="sec">Motivos de Reprovação</div>', unsafe_allow_html=True)
            
                # Uma coluna (empilhados): primeiro Alto Nível, depois Detalhado.
                fig = _fig_barras_h(agg.get("top_motivos", {}),
                                    "Motivo de Reprovação — Alto Nível", "#ef4444", pct_base=n_rep)
                if fig:
                    st.plotly_chart(fig, width='stretch', config=_CONF)
                else:
                    st.info("Sem dados de motivos.")

                mot_det = _merge_motivos_det(agg.get("top_motivos_det", {}))
                if mot_det:
                    n_det = sum(mot_det.values())
                    fig = _fig_barras_h(mot_det, "Motivo de Reprovação — Detalhado", "#f97316",
                                        pct_base=n_det)
                    if fig:
                        st.plotly_chart(fig, width='stretch', config=_CONF)
                else:
                    st.info("Motivos detalhados ainda não disponíveis (requer nova exportação dos JSONs).")
            
            # ── 11. Bloqueios ─────────────────────────────────────────────────────────────
            if _show("leads_reprovados"):

                st.markdown('<div class="sec">Bloqueios por Tipo</div>', unsafe_allow_html=True)
            
                fig = _fig_bloqueios(agg.get("bloqueios", {}), n_bloq=agg.get("bloqueados_total", 0))
                if fig:
                    col_bl, _ = st.columns([1, 1])
                    with col_bl:
                        st.plotly_chart(fig, width='stretch', config=_CONF)
                else:
                    st.info("Sem dados de bloqueios.")
            
            # ── 12. Segmentação — Reprovados ─────────────────────────────────────────────
            if _show("leads_reprovados"):

                st.markdown('<div class="sec">Segmentação — Reprovados</div>', unsafe_allow_html=True)
            
            
                emp_rep = agg.get("top_emp_rep", {})
                emp_mot = agg.get("emp_motivos", {})
                if emp_rep:
                    fig = _fig_barras_h(emp_rep, "Top Empregadores dos Reprovados", "#ef4444", pct_base=n_rep, show_pct=False)
                    if fig:
                        st.plotly_chart(fig, width='stretch', config=_CONF)
                    _tbl_html = _html_emp_rep_expandable(emp_rep, emp_mot, agg.get("emp_motivos_leads", {}), n_rep)
                    if _tbl_html:
                        st.markdown(_tbl_html, unsafe_allow_html=True)
                else:
                    st.info("Sem dados de empregadores dos reprovados (requer nova exportação dos JSONs).")

                cnaes = agg.get("top_cnaes", {})
                if cnaes:
                    n_cnae = sum(cnaes.values())
                    fig = _fig_barras_h(_sem_codigo(cnaes), "Top CNAEs Bloqueados (Reprovados)", "#eab308",
                                        pct_base=n_cnae)
                    if fig:
                        st.plotly_chart(fig, width='stretch', config=_CONF)
                    tbl = _html_tabela_ranking(cnaes, "Descrição CNAE", n_cnae, code_col_title="Código CNAE")
                    if tbl:
                        st.markdown(tbl, unsafe_allow_html=True)
                else:
                    st.info("Sem dados de CNAE bloqueado.")
            
                cbos_rep = agg.get("top_cbos_rep", {})
                if cbos_rep:
                    n_cbo_r = sum(cbos_rep.values())
                    fig = _fig_barras_h(_sem_codigo(cbos_rep), "Top CBOs Bloqueados (Reprovados)", "#a855f7",
                                        pct_base=n_cbo_r)
                    if fig:
                        st.plotly_chart(fig, width='stretch', config=_CONF)
                    tbl = _html_tabela_ranking(cbos_rep, "Descrição CBO", n_cbo_r, code_col_title="Código CBO")
                    if tbl:
                        st.markdown(tbl, unsafe_allow_html=True)
                else:
                    st.info("Sem dados de CBO dos reprovados.")
            
            # ── 13. Aprovados — Empregadores e CBOs ──────────────────────────────────────
            if _show("leads_aprovados"):

                st.markdown('<div class="sec">Aprovados — Empregadores e CBOs</div>', unsafe_allow_html=True)
            
                n_ap = f.get("aprovados", 0)
            

                emp_ap = agg.get("top_empregadores", {})
                emp_ap_stats = agg.get("emp_ap_stats", {})
                fig = _fig_barras_h(emp_ap, "Top Empregadores (Aprovados)", "#22c55e", pct_base=n_ap)
                if fig:
                    st.plotly_chart(fig, width='stretch', config=_CONF)
                tbl = _html_emp_ap_expandable(emp_ap, emp_ap_stats, n_ap)
                if tbl:
                    st.markdown(tbl, unsafe_allow_html=True)

                cbos_ap = agg.get("top_cbos", {})
                fig = _fig_barras_h(_sem_codigo(cbos_ap), "Top CBOs (Aprovados)", "#3b82f6", pct_base=n_ap)
                if fig:
                    st.plotly_chart(fig, width='stretch', config=_CONF)
                tbl = _html_tabela_ranking(cbos_ap, "Descrição CBO", n_ap, code_col_title="Código CBO")
                if tbl:
                    st.markdown(tbl, unsafe_allow_html=True)

            # ── 14. Desembolsados no Período — Segmentação ──────────────────────────────
            if _show("leads_desembolsados"):

                st.markdown('<div class="sec">Desembolsados no Período — Segmentação</div>', unsafe_allow_html=True)

                if not _desemb_det:
                    _msg_ori14 = " para a(s) origem(ns) selecionada(s)" if _ori_ativas else ""
                    st.info(f"Sem contratos desembolsados no período selecionado{_msg_ori14}.")
                else:
                    # ── Agrega por dimensão (soma contratos, valor contratado e liberado) ──────
                    _emp_d, _cbo_d, _cnae_d, _ori_d, _uf_d = {}, {}, {}, {}, {}
                    _cid_d: dict = {}        # cidade -> {n, valor, liberado}
                    _gen_d: dict = {}        # genero -> contagem
                    _nat_d: dict = {}        # natureza do empregador (PF/PJ) -> contagem
                    _idades: list = []       # idades dos tomadores
                    _iof_tot = 0.0
                    _prz_vals = []
                    _tx_pz    = []   # (taxa, prazo) para média ponderada pelo nº de parcelas

                    def _bump(_m, _k, _rec):
                        if not _k:
                            return
                        _a = _m.setdefault(_k, {"n": 0, "valor": 0.0, "liberado": 0.0})
                        _a["n"]        += 1
                        _a["valor"]    += _rec.get("valor", 0.0) or 0.0
                        _a["liberado"] += _rec.get("liberado", 0.0) or 0.0

                    for _rec in _desemb_det:
                        _bump(_emp_d,  _rec.get("emp"),    _rec)
                        _bump(_cbo_d,  _rec.get("cbo"),    _rec)
                        _bump(_cnae_d, _rec.get("cnae"),   _rec)
                        _bump(_ori_d,  _rec.get("origem"), _rec)
                        _bump(_uf_d,   _rec.get("uf"),     _rec)
                        _bump(_cid_d,  _rec.get("cidade"), _rec)
                        _g = str(_rec.get("genero") or "").strip().upper()
                        if _g:
                            _gen_d[_g] = _gen_d.get(_g, 0) + 1
                        _nt = str(_rec.get("natureza") or "").strip().upper()
                        if _nt:
                            _nat_d[_nt] = _nat_d.get(_nt, 0) + 1
                        _ida = _rec.get("idade")
                        if _ida:
                            _idades.append(int(_ida))
                        _iof_tot += _rec.get("iof", 0.0) or 0.0
                        if _rec.get("prazo"):
                            _prz_vals.append(_rec["prazo"])
                        if _rec.get("taxa") and _rec.get("prazo"):
                            _tx_pz.append((_rec["taxa"], _rec["prazo"]))

                    _n_det   = len(_desemb_det)
                    _sum_val = sum((r.get("valor", 0.0) or 0.0) for r in _desemb_det)
                    _sum_lib = sum((r.get("liberado", 0.0) or 0.0) for r in _desemb_det)
                    _ticket  = (_sum_val / _n_det) if _n_det else 0.0
                    _prz_med = (sum(_prz_vals) / len(_prz_vals)) if _prz_vals else 0.0
                    _tx_med  = (sum(_t * _z for _t, _z in _tx_pz) / sum(_z for _, _z in _tx_pz)) if _tx_pz else 0.0

                    def _brl2(v):
                        return ("R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if v else "—"

                    # ── KPIs dos desembolsados (mesmos do grupo inicial "3 · Desembolsados") ────
                    st.markdown(f"""
                    <div class="kpi-row" style="grid-template-columns:repeat(4,1fr)">
                      <div class="kpi-card"><div class="kpi-label">Contratos desembolsados</div><div class="kpi-value">{_desemb_cnt_s}</div><div class="kpi-sub">{periodo_label}</div></div>
                      <div class="kpi-card"><div class="kpi-label">Total contratado (com IOF)</div><div class="kpi-value">{_desemb_kpi_val_s}</div><div class="kpi-sub">valor contratado</div></div>
                      <div class="kpi-card"><div class="kpi-label">Valor contratado médio (com IOF)</div><div class="kpi-value">{_desemb_ticket_s}</div><div class="kpi-sub">por contrato desembolsado</div></div>
                      <div class="kpi-card"><div class="kpi-label">Valor da parcela médio</div><div class="kpi-value">{_dz_parc_s}</div><div class="kpi-sub">média pond. pelo prazo</div></div>
                      <div class="kpi-card"><div class="kpi-label">Taxa mensal média</div><div class="kpi-value">{_dz_taxa_s}</div><div class="kpi-sub">média pond. pelo nº de parcelas</div></div>
                      <div class="kpi-card"><div class="kpi-label">Total liberado (sem IOF)</div><div class="kpi-value">{_desemb_kpi_lib_s}</div><div class="kpi-sub">valor recebido pelo cliente</div></div>
                      <div class="kpi-card"><div class="kpi-label">Valor liberado médio (sem IOF)</div><div class="kpi-value">{_desemb_ticket_lib_s}</div><div class="kpi-sub">por contrato desembolsado</div></div>
                      <div class="kpi-card"><div class="kpi-label">Número de parcelas médio</div><div class="kpi-value">{_dz_prazo_s}</div><div class="kpi-sub">contratos desembolsados</div></div>
                    </div>
                    """, unsafe_allow_html=True)

                    st.caption(
                        "Contratos com data de desembolso (Pix) dentro do período filtrado · "
                        "inclui leads criados até 7 dias antes do início do período."
                    )

                    # ── Distribuição do nº de parcelas (só NumeroParcelasContrato; sem fallback) ─
                    _pzn_dist: dict = {}
                    for _rec in _desemb_det:
                        _npz = _rec.get("n_parcelas")
                        if _npz and _npz > 0:
                            _npk = str(int(round(_npz)))
                            _pzn_dist[_npk] = _pzn_dist.get(_npk, 0) + 1
                    _fig_pzn = _fig_dist_prazo(
                        _pzn_dist, "Distribuição de Nº de Parcelas — Desembolsados")
                    if _fig_pzn:
                        st.plotly_chart(_fig_pzn, width='stretch', config=_CONF)

                    # ── Ordenações ─────────────────────────────────────────────────────────────
                    def _items(_m, by="valor"):
                        return [
                            {"label": k, "n": v["n"], "valor": v["valor"], "liberado": v["liberado"]}
                            for k, v in sorted(_m.items(), key=lambda x: -x[1][by])
                        ]

                    def _trunc(s, m=42):
                        s = str(s)
                        return s if len(s) <= m else s[:m - 1].rstrip() + "…"

                    _emp_items  = _items(_emp_d,  "valor")   # empregadores: por R$ contratado
                    _cbo_items  = _items(_cbo_d,  "n")       # CBOs / CNAEs: por nº de contratos
                    _cnae_items = _items(_cnae_d, "n")
                    _ori_items  = _items(_ori_d,  "n")
                    _uf_items   = _items(_uf_d,   "n")

                    # ── Top Empregadores (R$) | Top CBOs (contratos) ───────────────────────────
                    # soma na colisão de rótulo truncado (não sobrescreve), igual _sem_codigo
                    _emp_chart: dict = {}
                    for it in _emp_items[:12]:
                        _k = _trunc(it["label"])
                        _emp_chart[_k] = _emp_chart.get(_k, 0.0) + it["valor"]
                    fig = _fig_barras_reais(_emp_chart, "Top Empregadores · Valor Contratado", "#FEC52E")
                    if fig:
                        st.plotly_chart(fig, width='stretch', config=_CONF)
                    tbl = _html_tabela_desemb(_emp_items, "Empregador", _n_det)
                    if tbl:
                        st.markdown(tbl, unsafe_allow_html=True)
                    _cbo_chart = _sem_codigo({it["label"]: it["n"] for it in _cbo_items})
                    fig = _fig_barras_h(_cbo_chart, "Top CBOs · Nº de Contratos", "#3b82f6",
                                        pct_base=_n_det, show_abs=True)
                    if fig:
                        st.plotly_chart(fig, width='stretch', config=_CONF)
                    tbl = _html_tabela_desemb(_cbo_items, "Descrição CBO", _n_det, code_col_title="Código CBO")
                    if tbl:
                        st.markdown(tbl, unsafe_allow_html=True)

                    # ── Top CNAEs (largura total) ──────────────────────────────────────────────
                    _cnae_chart = _sem_codigo({it["label"]: it["n"] for it in _cnae_items})
                    fig = _fig_barras_h(_cnae_chart, "Top CNAEs · Nº de Contratos", "#a855f7",
                                        pct_base=_n_det, show_abs=True)
                    if fig:
                        st.plotly_chart(fig, width='stretch', config=_CONF)
                    tbl = _html_tabela_desemb(_cnae_items, "Descrição CNAE", _n_det, code_col_title="Código CNAE")
                    if tbl:
                        st.markdown(tbl, unsafe_allow_html=True)

                    # ── Por Origem | Por UF ────────────────────────────────────────────────────
                    _ori_chart = {it["label"]: it["n"] for it in _ori_items}
                    fig = _fig_barras_h(_ori_chart, "Desembolsos por Origem", "#f59e0b",
                                        pct_base=_n_det, show_abs=True, text_auto=True)
                    if fig:
                        st.plotly_chart(fig, width='stretch', config=_CONF)
                    _uf_chart = {it["label"]: it["n"] for it in _uf_items}
                    fig = _fig_barras_h(_uf_chart, "Desembolsos por UF", "#06b6d4",
                                        pct_base=_n_det, show_abs=True)
                    if fig:
                        st.plotly_chart(fig, width='stretch', config=_CONF)

                    # ── Distribuição de Idade do tomador (faixas etárias) ──────────────────────
                    # Faixas meio-abertas: o limite superior cai na faixa seguinte (25 -> "25-30").
                    _FAIXAS_IDADE = [("21-25", 21, 24), ("25-30", 25, 29), ("30-35", 30, 34),
                                     ("35-40", 35, 39), ("40-45", 40, 44), ("45-50", 45, 49),
                                     ("50-55", 50, 54), ("55-60", 55, 59)]
                    _id_counts = {_lbl: 0 for _lbl, _, _ in _FAIXAS_IDADE}
                    for _a in _idades:
                        for _lbl, _lo, _hi in _FAIXAS_IDADE:
                            if _lo <= _a <= _hi:
                                _id_counts[_lbl] += 1
                                break
                    fig = _fig_barras_v([(_lbl, _id_counts[_lbl]) for _lbl, _, _ in _FAIXAS_IDADE],
                                        "Distribuição de Idade — Tomadores Desembolsados", "Faixa etária")
                    if fig:
                        st.plotly_chart(fig, width='stretch', config=_CONF)

                    # ── Distribuição por Gênero do tomador ─────────────────────────────────────
                    _GEN_LBL = {"M": "Masculino", "F": "Feminino"}
                    _gen_chart = {_GEN_LBL.get(_k, _k or "—"): _v
                                  for _k, _v in sorted(_gen_d.items(), key=lambda x: -x[1])}
                    fig = _fig_barras_h(_gen_chart, "Distribuição por Gênero — Tomadores", "#ec4899",
                                        pct_base=sum(_gen_d.values()), show_abs=True)
                    if fig:
                        st.plotly_chart(fig, width='stretch', config=_CONF)

                    # ── Distribuição por Natureza do Empregador (PF/PJ) ────────────────────────
                    _NAT_LBL = {"PJ": "Empregador Pessoa Jurídica", "PF": "Empregador Pessoa Física"}
                    _nat_chart = {_NAT_LBL.get(_k, _k): _v
                                  for _k, _v in sorted(_nat_d.items(), key=lambda x: -x[1])}
                    fig = _fig_barras_h(_nat_chart, "Distribuição por Natureza do Empregador — Desembolsados",
                                        "#8b5cf6", pct_base=sum(_nat_d.values()), show_abs=True)
                    if fig:
                        st.plotly_chart(fig, width='stretch', config=_CONF)

                    # ── Top 50 Cidades por nº de desembolsos ────────────────────────────────────
                    _cid_items = _items(_cid_d, "n")
                    _cid_chart = {_trunc(it["label"]): it["n"] for it in _cid_items[:50]}
                    fig = _fig_barras_h(_cid_chart, "Top 50 Cidades · Nº de Desembolsos", "#22c55e",
                                        n=50, pct_base=_n_det, show_abs=True)
                    if fig:
                        st.plotly_chart(fig, width='stretch', config=_CONF)
                    tbl = _html_tabela_desemb(_cid_items, "Cidade", _n_det, n=50)
                    if tbl:
                        st.markdown(tbl, unsafe_allow_html=True)

except Exception as _exc:
    import traceback as _tb
    st.warning(
        "⚠️ **Plataforma em manutenção** — houve um erro inesperado. "
        "Aguarde alguns minutos e recarregue a página."
    )
    with st.expander("🔍 Detalhes do erro (debug)"):
        st.code(_tb.format_exc(), language="python")
    st.stop()
