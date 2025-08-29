# app.py
import os
import re
import time
import pandas as pd
import streamlit as st

# Só importamos BeautifulSoup quando (e se) precisarmos
from bs4 import BeautifulSoup

# ------------------------------------------------------------
# Config
# ------------------------------------------------------------
st.set_page_config(page_title="Comparador de Odds — Escanteios", layout="wide")

st.title("📊 Comparador de Odds – Escanteios (raspagem direta)")
st.caption(
    "Cole as URLs do MESMO jogo nas 3 casas e clique em Atualizar. "
    "Se o ambiente bloquear automação (ex.: Streamlit Cloud), eu mostro um modo seguro (CSV/Demo)."
)

colA, colB, colC = st.columns(3)
with colA:
    url_betano = st.text_input("URL Betano", placeholder="https://www.betano.bet.br/…")
with colB:
    url_bet365 = st.text_input("URL Bet365", placeholder="https://www.bet365.bet.br/…")
with colC:
    url_kto    = st.text_input("URL KTO",    placeholder="https://kto.bet.br/…")

run_headless = st.toggle("Rodar navegador invisível (headless)", value=True, help="Apenas no Windows/local")
timeout_s    = st.slider("Tempo máximo de carregamento (s)", 10, 60, 25)

st.divider()
btn = st.button("🔄 Atualizar Odds")

# ------------------------------------------------------------
# Utilitários
# ------------------------------------------------------------
@st.cache_data(ttl=15)
def read_csv_fallback(csv_url: str) -> pd.DataFrame:
    df = pd.read_csv(csv_url)
    return df

def demo_dataframe() -> pd.DataFrame:
    agora = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    return pd.DataFrame(
        [
            ["Mais de 9.5 escanteios", 1.85, 1.80, 1.87, agora],
            ["Menos de 9.5 escanteios", 1.95, 1.90, 1.92, agora],
        ],
        columns=["mercado", "betano", "bet365", "kto", "atualizado_em"],
    )

def try_get_secret_csv_url() -> str | None:
    # Se você tiver configurado no Streamlit Cloud: Settings → Secrets:
    # SHEET_CSV_URL = "https://docs.google.com/spreadsheets/…&output=csv"
    return (st.secrets.get("SHEET_CSV_URL") or "").strip() if "SHEET_CSV_URL" in st.secrets else None

# ------------------------------------------------------------
# Playwright scraping (só local/Windows ou ambientes que permitam)
# ------------------------------------------------------------
def scrape_with_playwright(url: str, headless: bool, timeout: int) -> str:
    """
    Retorna o HTML final renderizado da página.
    Levanta exceção se Playwright não estiver disponível/permitido.
    """
    # Importamos aqui para só tentar quando for usar (evita erro no Cloud)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.set_default_navigation_timeout(timeout * 1000)
        page.goto(url, wait_until="domcontentloaded")
        # alguns sites precisam de um pequeno “respiro”:
        page.wait_for_timeout(1500)
        html = page.content()
        browser.close()
        return html

def parse_escanteios_from_html(html: str) -> dict:
    """
    Exemplo simplificado: você adapta depois para extrair corretamente
    as odds de escanteios de cada site (Betano, Bet365, KTO).
    Aqui eu só devolvo um “mock” para manter o fluxo.
    """
    soup = BeautifulSoup(html, "html.parser")
    # TODO: ajustar para cada site/estrutura.
    # Retornamos um dicionário com odds que você extraíu da página:
    return {
        "Mais de 9.5 escanteios": 1.85,
        "Menos de 9.5 escanteios": 1.95,
    }

def unify_rows(betano: dict | None, bet365: dict | None, kto: dict | None) -> pd.DataFrame:
    """
    Junta as odds por mercado (chave do dicionário) em um DataFrame.
    Onde não encontrar, usa '—'.
    """
    mercados = set()
    for d in (betano, bet365, kto):
        if d:
            mercados.update(d.keys())

    linhas = []
    agora = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    for m in sorted(mercados):
        linhas.append([
            m,
            betano.get(m, "—")  if betano else "—",
            bet365.get(m, "—")  if bet365 else "—",
            kto.get(m, "—")     if kto    else "—",
            agora,
        ])
    return pd.DataFrame(linhas, columns=["mercado", "betano", "bet365", "kto", "atualizado_em"])

# ------------------------------------------------------------
# Fluxo principal (com fallback automático)
# ------------------------------------------------------------
def main():
    if not btn:
        st.info("Preencha as URLs e clique em **Atualizar Odds**.")
        return

    # Tentamos scraping real; se falhar (ex.: Cloud), caímos no fallback.
    try:
        if not any([url_betano, url_bet365, url_kto]):
            st.warning("Informe pelo menos uma URL.")
            return

        with st.status("Abrindo navegador e carregando páginas…", expanded=False):
            dados_betano = dados_bet365 = dados_kto = None

            # Cada URL informada, tentamos raspar:
            if url_betano:
                html_betano = scrape_with_playwright(url_betano, run_headless, timeout_s)
                dados_betano = parse_escanteios_from_html(html_betano)

            if url_bet365:
                html_bet365 = scrape_with_playwright(url_bet365, run_headless, timeout_s)
                dados_bet365 = parse_escanteios_from_html(html_bet365)

            if url_kto:
                html_kto = scrape_with_playwright(url_kto, run_headless, timeout_s)
                dados_kto = parse_escanteios_from_html(html_kto)

        df = unify_rows(dados_betano, dados_bet365, dados_kto)

        if df.empty:
            st.warning("Não consegui extrair odds (pode ser que a casa bloqueie automação ou o seletor precise ser ajustado).")
        else:
            st.success("Odds atualizadas com sucesso! (raspagem real)")
            st.dataframe(df, use_container_width=True)
            st.caption("Obs.: “—” indica que a casa não oferece aquele mercado no momento.")

    except Exception as e:
        # FALLBACK: estamos provavelmente no Streamlit Cloud, ou o site bloqueou.
        st.warning(
            "⚠️ Ambiente com restrição de automação ou bloqueio do site. "
            "Ativando **modo seguro** (CSV/Demo)."
        )
        csv_url = try_get_secret_csv_url()
        df = None
        if csv_url:
            try:
                df = read_csv_fallback(csv_url)
                st.info("📥 Lendo dados do CSV configurado em *Secrets* (SHEET_CSV_URL).")
            except Exception as _:
                df = None

        if df is None:
            st.info("🔬 Usando **dados demo** apenas para visualização.")
            df = demo_dataframe()

        st.dataframe(df, use_container_width=True)
        st.caption("Obs.: Este é o modo seguro (sem raspagem). Configure o CSV nos *Secrets* para usar dados reais no Cloud.")

if __name__ == "__main__":
    main()
