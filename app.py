import time, re, math
import pandas as pd
import requests
from bs4 import BeautifulSoup
import streamlit as st

st.set_page_config(page_title="Odds de Escanteios", layout="wide")
st.title("📊 Comparador de Odds – Escanteios")
st.caption("Frontend com cache global (15s). Betano/Bet365 via planilha; KTO raspado leve. Protótipo educacional.")

# 1) URL da planilha publicada como CSV (defina em Settings → Secrets do Streamlit Cloud)
SHEET_CSV_URL = st.secrets.get("SHEET_CSV_URL", "")

# 2) Cabeçalhos mais realistas (ajuda em raspagens simples)
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/123.0.0.0 Safari/537.36"),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://kto.bet.br/",
}

ODD_RE = re.compile(r"\b\d\.\d{2}\b")

# ---------- CACHE GLOBAL (15s) ----------
# Tudo que consulta fonte externa fica em cache por 15s e é COMPARTILHADO entre usuários
@st.cache_data(ttl=15)  # <-- cache global de 15 segundos
def read_sheet(csv_url: str) -> pd.DataFrame:
    """Lê a planilha (CSV publicado). Inclui backoff para evitar 429."""
    if not csv_url:
        return pd.DataFrame(columns=["mercado","betano","bet365","kto","atualizado_em"])

    # Exponential backoff para 429/erros transitórios
    delay = 0.5
    for attempt in range(5):
        try:
            df = pd.read_csv(csv_url)
            # normaliza colunas esperadas
            for c in ["mercado","betano","bet365","kto","atualizado_em"]:
                if c not in df.columns:
                    df[c] = ""
            return df[["mercado","betano","bet365","kto","atualizado_em"]]
        except Exception as e:
            if attempt == 4:
                raise
            time.sleep(delay)
            delay *= 2  # backoff

@st.cache_data(ttl=15)  # <-- cache global da raspagem KTO
def fetch_kto_html(url: str) -> str:
    if not url:
        return ""
    with requests.Session() as s:
        s.headers.update(HEADERS)
        r = s.get(url, timeout=20)
        # falhas transitórias → pequena espera e reler via cache na próxima chamada
        r.raise_for_status()
        return r.text

def normalize_market(raw: str) -> str:
    t = " ".join(str(raw).split())
    low = t.lower()
    m = re.search(r"(\d+(?:[.,]\d)?)", low)
    num = m.group(1).replace(",", ".") if m else ""
    if "menos" in low or "under" in low:
        return f"Menos de {num} escanteios" if num else "Menos (escanteios)"
    if "mais" in low or "over" in low:
        return f"Mais de {num} escanteios" if num else "Mais (escanteios)"
    return t

def scrape_kto(url: str) -> dict:
    data = {}
    if not url:
        return data
    try:
        html = fetch_kto_html(url)  # usa a função cacheada
        if not html:
            return data
        soup = BeautifulSoup(html, "lxml")
        # procurar blocos com "escanteios"/"corners"
        def has_corners(s):
            return s and any(k in s.lower() for k in ["escanteio", "escanteios", "corner", "corners"])
        for node in soup.find_all(True, string=has_corners):
            cont = node.parent
            text = cont.get_text("\n", strip=True)
            for ln in [ln for ln in text.splitlines() if ln]:
                if any(k in ln.lower() for k in ["mais", "menos", "over", "under"]):
                    m = ODD_RE.search(ln)
                    if m:
                        data[normalize_market(ln)] = float(m.group(0))
    except Exception:
        pass
    return data

# ---------- UI ----------
c1, c2, c3 = st.columns(3)
with c1: link_betano = st.text_input("Link Betano (referência)", placeholder="https://www.betano.bet.br/...")
with c2: link_bet365 = st.text_input("Link Bet365 (referência)", placeholder="https://www.bet365.com/...")
with c3: link_kto    = st.text_input("Link KTO (raspagem leve)", placeholder="https://kto.bet.br/...")

if st.button("🔄 Atualizar Odds"):
    # 1) Lê planilha (preenchida fora do Cloud). Aqui ficam Betano/Bet365.
    sheet = read_sheet(SHEET_CSV_URL)

    # 2) Raspagem leve da KTO (direto do link, cacheada por 15s)
    kto_map = scrape_kto(link_kto.strip())

    # 3) Junta tudo por mercado
    rows = {}
    for _, r in sheet.iterrows():
        mk = normalize_market(r["mercado"])
        rows.setdefault(mk, {"Mercado": mk, "Betano": "—", "Bet365": "—", "KTO": "—"})
        if str(r["betano"]).strip(): rows[mk]["Betano"] = r["betano"]
        if str(r["bet365"]).strip(): rows[mk]["Bet365"] = r["bet365"]
        if str(r["kto"]).strip():    rows[mk]["KTO"]    = r["kto"]
    for mk, odd in kto_map.items():
        rows.setdefault(mk, {"Mercado": mk, "Betano": "—", "Bet365": "—", "KTO": "—"})
        rows[mk]["KTO"] = odd

    if not rows:
        st.warning("Sem dados. Publique sua planilha (Arquivo → Publicar na Web → CSV) ou informe um link válido da KTO.")
    else:
        st.success("Odds atualizadas! (cache global por 15s)")
        st.dataframe(list(rows.values()), use_container_width=True)
        st.caption("Onde aparecer “—” significa que a casa não oferece aquele mercado ou não foi encontrado.")
