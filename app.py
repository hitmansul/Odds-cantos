import re, time, json
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Comparador de Odds – Escanteios", layout="wide")
st.title("📊 Comparador de Odds – Escanteios (raspagem direta)")
st.caption("Cole as URLs do MESMO jogo nas 3 casas e clique em Atualizar. Protótipo educacional — alguns sites podem bloquear (403).")

# ---------- Config ----------
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/123.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://google.com",
    "Connection": "keep-alive",
}
ODD_RE = re.compile(r"\b\d\.\d{2}\b")

def is_corners_label(txt: str) -> bool:
    if not txt: return False
    t = txt.lower()
    return ("escanteio" in t) or ("corners" in t) or ("corner" in t)

def normalize_market(raw: str) -> str:
    t = " ".join(str(raw).split())
    low = t.lower()
    m = re.search(r"(\d+(?:[.,]\d)?)", low)
    num = m.group(1).replace(",", ".") if m else ""
    if ("menos" in low) or ("under" in low):
        return f"Menos de {num} escanteios" if num else "Menos (escanteios)"
    if ("mais" in low) or ("over" in low):
        return f"Mais de {num} escanteios" if num else "Mais (escanteios)"
    if "handicap" in low:
        return f"Handicap escanteios {num}" if num else "Handicap escanteios"
    return t

def get_html(url: str) -> str:
    host = urlparse(url).netloc.lower()
    home = None
    if "betano" in host:
        home = "https://www.betano.bet.br"
    elif "kto" in host:
        home = "https://kto.bet.br"
    with requests.Session() as s:
        s.headers.update(HEADERS)
        try:
            if home:
                s.get(home, timeout=15, allow_redirects=True)
        except Exception:
            pass
        last_exc = None
        for _ in range(2):
            try:
                r = s.get(url, timeout=25, allow_redirects=True)
                if r.status_code == 200 and r.text:
                    return r.text
                time.sleep(1.2)
            except Exception as e:
                last_exc = e
                time.sleep(1.2)
        if last_exc:
            raise last_exc
        raise RuntimeError(f"Falha ao carregar {url}")

# ---------- Betano ----------
def scrape_betano(url: str) -> dict:
    data = {}
    if not url: return data
    html = get_html(url)
    soup = BeautifulSoup(html, "lxml")

    for sc in soup.find_all("script"):
        txt = (sc.string or sc.text or "")
        if not txt or ("market" not in txt and "markets" not in txt):
            continue
        for match in re.finditer(r"\{.*\}", txt, re.DOTALL):
            chunk = match.group(0)
            if "escante" in chunk.lower() or "corner" in chunk.lower():
                try:
                    obj = json.loads(chunk)
                except Exception:
                    continue
                cands = []
                if isinstance(obj, dict):
                    if "markets" in obj: cands = obj["markets"]
                    elif "data" in obj and isinstance(obj["data"], dict) and "markets" in obj["data"]:
                        cands = obj["data"]["markets"]
                for mk in cands or []:
                    name = (mk.get("name") or mk.get("marketName") or "")
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
    if not data:
        node = soup.find(string=is_corners_label)
        if node:
            cont = node.parent
            for _ in range(3):
                if cont and cont.get_text(): break
                cont = cont.parent
            if cont:
                text = cont.get_text("\n", strip=True)
                lines = [ln for ln in text.splitlines() if ln]
                for ln in lines:
                    if any(k in ln.lower() for k in ["mais", "menos", "over", "under"]):
                        m = ODD_RE.search(ln)
                        if m:
                            data[normalize_market(ln)] = float(m.group(0))
    return data

# ---------- KTO ----------
def scrape_kto(url: str) -> dict:
    data = {}
    if not url: return data
    html = get_html(url)
    soup = BeautifulSoup(html, "lxml")
    node = soup.find(string=is_corners_label)
    if not node: return data
    cont = node.parent
    for _ in range(3):
        if cont and cont.get_text(): break
        cont = cont.parent
    if not cont: return data
    text = cont.get_text("\n", strip=True)
    lines = [ln for ln in text.splitlines() if ln]
    for ln in lines:
        if any(k in ln.lower() for k in ["mais", "menos", "over", "under"]):
            m = ODD_RE.search(ln)
            if m:
                data[normalize_market(ln)] = float(m.group(0))
    return data

# ---------- Bet365 (placeholder) ----------
def scrape_bet365(_url: str) -> dict:
    return {}  # vazio por enquanto

# ---------- UI ----------
c1, c2, c3 = st.columns(3)
with c1: url_betano = st.text_input("URL Betano", placeholder="https://www.betano.bet.br/...")
with c2: url_bet365 = st.text_input("URL Bet365", placeholder="https://www.bet365.com/...")
with c3: url_kto    = st.text_input("URL KTO",    placeholder="https://kto.bet.br/...")

if st.button("🔄 Atualizar Odds"):
    try:
        betano = scrape_betano(url_betano.strip()) if url_betano else {}
        bet365 = scrape_bet365(url_bet365.strip()) if url_bet365 else {}
        kto    = scrape_kto(url_kto.strip())       if url_kto else {}

        markets = sorted(set(betano) | set(bet365) | set(kto))
        if not markets:
            st.warning("Não encontrei mercados de escanteios. Verifique se as URLs são de páginas DE JOGO e com a seção de escanteios disponível.")
        else:
            rows = []
            for mk in markets:
                rows.append({
                    "Mercado": mk,
                    "Betano": betano.get(mk, "—"),
                    "Bet365": bet365.get(mk, "—"),
                    "KTO":    kto.get(mk, "—"),
                })
            df = pd.DataFrame(rows)
            st.success("Odds atualizadas!")
            st.dataframe(df, use_container_width=True)
            st.caption("“—” indica que a casa não oferece aquele mercado.")
    except requests.HTTPError as e:
        st.error(f"Falha HTTP ao carregar página: {e}")
    except Exception as e:
        st.error(f"Erro ao buscar: {e}")
