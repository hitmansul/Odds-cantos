import re, json, time
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import streamlit as st

st.set_page_config(page_title="Odds de Escanteios", layout="wide")
st.title("📊 Comparador de Odds – Escanteios")
st.caption("Cole os links do MESMO jogo em cada casa e clique em Atualizar. (Protótipo educacional).")

# ---------- utilidades ----------

HEADERS = {
    # navegador comum (desktop)
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/123.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://www.betano.bet.br/",
    "Connection": "keep-alive",
}

def get_html(url: str) -> str:
    """Baixa HTML com headers básicos e pequeno retry."""
    for _ in range(2):
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200 and r.text:
            return r.text
        time.sleep(1)
    raise RuntimeError(f"Falha ao carregar {url} (status {r.status_code})")

def is_corners_label(txt: str) -> bool:
    """Detecta textos de mercado de escanteios."""
    t = txt.lower()
    return any(k in t for k in [
        "escanteio", "escanteios", "corners", "corner",
        "total de escanteios", "total corners"
    ])

ODD_RE = re.compile(r"\b(?:1|2|3)\.\d{2}\b")  # ex: 1.85, 2.10, 3.05

def normalize_market(raw: str) -> str:
    """Normaliza rótulos tipo 'Mais de 10.5 escanteios'/'Over 10.5 corners'."""
    t = " ".join(raw.split())
    t_low = t.lower()
    # capturar 8.5/9.5/10.5 etc
    m = re.search(r"(\d+(?:[.,]\d)?)", t_low)
    num = m.group(1).replace(",", ".") if m else ""
    if "menos" in t_low or "under" in t_low:
        base = f"Menos de {num} escanteios" if num else "Menos (escanteios)"
    elif "mais" in t_low or "over" in t_low:
        base = f"Mais de {num} escanteios" if num else "Mais (escanteios)"
    elif "handicap" in t_low:
        base = f"Handicap escanteios {num}" if num else "Handicap escanteios"
    else:
        base = t  # deixa como veio
    return base

# ---------- BETANO ----------

def scrape_betano(url: str):
    """
    Betano costuma embutir blocos <script> com JSON de mercados OU HTML com as linhas.
    Estratégia:
      1) procurar JSON com 'markets'/'selections'
      2) se não achar, varrer o HTML procurando blocos onde o título menciona escanteios
         e extrair odds (1.80, 1.95 etc).
    Retorna: dict { mercado_normalizado: odd }
    """
    data = {}
    html = get_html(url)
    soup = BeautifulSoup(html, "lxml")

    # 1) tentar achar JSON em scripts
    scripts = soup.find_all("script")
    for sc in scripts:
        txt = sc.string or sc.text or ""
        if not txt or ("market" not in txt and "markets" not in txt):
            continue
        # extrair trechos JSON grosseiramente
        for match in re.finditer(r"\{.*\}", txt, re.DOTALL):
            chunk = match.group(0)
            if "escante" in chunk.lower() or "corner" in chunk.lower():
                try:
                    obj = json.loads(chunk)
                except Exception:
                    continue
                # caminhos comuns (variável entre deploys)
                candidates = []
                if isinstance(obj, dict):
                    if "markets" in obj: candidates = obj["markets"]
                    elif "data" in obj and isinstance(obj["data"], dict) and "markets" in obj["data"]:
                        candidates = obj["data"]["markets"]
                for mk in candidates or []:
                    name = mk.get("name") or mk.get("marketName") or ""
                    if name and is_corners_label(name):
                        for sel in mk.get("selections", []) or mk.get("outcomes", []) or []:
                            label = sel.get("name") or sel.get("selectionName") or ""
                            price = sel.get("price") or sel.get("odd") or sel.get("odds")
                            if label and price:
                                market = normalize_market(f"{label} {name}")
                                try:
                                    data[market] = float(str(price).replace(",", "."))
                                except Exception:
                                    pass
    # 2) fallback: varrer HTML
    if not data:
        # procurar cards/blocos com títulos contendo escanteios
        for blk in soup.find_all(True, string=is_corners_label):
            # subir ao container
            cont = blk.parent
            for _ in range(3):
                if cont and cont.find_all(text=ODD_RE):
                    break
                cont = cont.parent
            if not cont:
                continue
            # odds no container
            odds_texts = [m.group(0) for m in ODD_RE.finditer(cont.get_text(" "))]
            # rótulos
            labels = [t for t in re.split(r"[\n\r]+", cont.get_text("\n")) if t.strip()]
            # tentar combinar
            for lab in labels:
                if any(x in lab.lower() for x in ["mais", "menos", "over", "under"]):
                    m = ODD_RE.search(lab)
                    odd_here = m.group(0) if m else (odds_texts.pop(0) if odds_texts else None)
                    if odd_here:
                        data[normalize_market(lab)] = float(odd_here)
    return data

# ---------- KTO ----------

def scrape_kto(url: str):
    """
    KTO normalmente traz HTML com os mercados na página do evento.
    Estratégia similar ao fallback da Betano.
    """
    data = {}
    html = get_html(url)
    soup = BeautifulSoup(html, "lxml")

    # procurar blocos que mencionam escanteios
    for title_node in soup.find_all(True, string=is_corners_label):
        cont = title_node.parent
        for _ in range(3):
            if cont and cont.get_text():
                break
            cont = cont.parent
        if not cont:
            continue

        text = cont.get_text("\n")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        # buscar linhas com "mais/menos/over/under" e um número com .5
        for ln in lines:
            if any(k in ln.lower() for k in ["mais", "menos", "over", "under"]):
                odd = None
                m = ODD_RE.search(ln)
                if m:
                    odd = m.group(0)
                # se a odd não estiver na mesma linha, procurar na sequência
                if odd is None:
                    # vasculhar vizinhança de odds
                    odds_around = ODD_RE.findall(text)
                    if odds_around:
                        odd = odds_around.pop(0)
                if odd:
                    data[normalize_market(ln)] = float(odd)
    return data

# ---------- Comparação & UI ----------

def compare_corners(betano_url, bet365_url, kto_url):
    """Retorna estrutura para exibir na tabela."""
    # raspa betano e kto
    betano = scrape_betano(betano_url) if betano_url else {}
    kto = scrape_kto(kto_url) if kto_url else {}

    # bet365 ainda simulado (até fazermos módulo próprio)
    bet365 = {}
    if bet365_url:
        # placeholder
        bet365 = {}

    # combinar todos os mercados encontrados
    all_markets = sorted(set(list(betano.keys()) + list(kto.keys()) + list(bet365.keys())))

    rows = []
    for mk in all_markets:
        rows.append({
            "Mercado": mk,
            "Betano": betano.get(mk, "—"),
            "Bet365": bet365.get(mk, "—"),
            "KTO":    kto.get(mk, "—"),
        })
    return rows

# ---------- UI ----------

c1, c2, c3 = st.columns(3)
with c1: link_betano = st.text_input("Link Betano", placeholder="https://br.betano.com/...")
with c2: link_bet365 = st.text_input("Link Bet365", placeholder="https://www.bet365.com/...")
with c3: link_kto    = st.text_input("Link KTO",    placeholder="https://kto.com/...")

if st.button("🔄 Atualizar Odds"):
    try:
        rows = compare_corners(link_betano.strip(), link_bet365.strip(), link_kto.strip())
        if not rows:
            st.warning("Não encontrei mercados de escanteios. Verifique se os links são de uma PÁGINA DE JOGO.")
        else:
            st.success("Odds atualizadas!")
            # montar tabela
            st.dataframe(rows, use_container_width=True)
            st.caption("Dica: onde aparecer '—' significa que a casa não oferece aquele mercado.")
    except Exception as e:
        st.error(f"Erro ao buscar: {e}")
        st.caption("Sites podem bloquear scraping, mudar HTML ou exigir login. Tente novamente mais tarde.")
