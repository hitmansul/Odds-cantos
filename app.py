# app.py
import re
import time
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

st.set_page_config(page_title="Comparador de Odds – Escanteios", page_icon="📊", layout="wide")

st.title("Comparador de Odds – Escanteios (navegador real / Playwright)")
st.caption(
    "Cole as URLs do MESMO jogo nas 3 casas e clique em **Atualizar Odds**. "
    "O app abre um Chromium invisível, renderiza a página e tenta extrair odds de escanteios de forma genérica."
)

colA, colB, colC = st.columns(3)
with colA:
    url_betano = st.text_input("URL Betano", placeholder="https://www.betano.bet.br/...")
with colB:
    url_bet365 = st.text_input("URL Bet365", placeholder="https://www.bet365.com/...")
with colC:
    url_kto = st.text_input("URL KTO", placeholder="https://kto.bet.br/...")

run_headless = st.toggle("Rodar navegador invisível (headless)", value=True, help="Desligue para depurar (vai abrir uma janela do Chromium).")
timeout_s = st.slider("Tempo máximo de carregamento por página (segundos)", 5, 40, 18)

st.divider()
btn = st.button("🔄 Atualizar Odds")

# --------- Funções utilitárias ---------
def open_with_playwright(url: str, headless: bool = True, timeout: int = 18000) -> tuple[str, str]:
    """
    Abre a URL com Chromium (Playwright), espera a rede acalmar e devolve (page_title, html_completo).
    timeout em milissegundos.
    """
    if not url:
        return ("", "")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        # Contexto "limpo", com user-agent e idioma
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1366, "height": 768},
        )
        page = context.new_page()

        # Algumas páginas precisam de navegação + scroll para renderizar blocos
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        try:
            page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            # nem sempre atinge 'networkidle', seguimos com o que já carregou
            pass

        # scroll para forçar lazy-loading
        for _ in range(4):
            page.mouse.wheel(0, 1200)
            time.sleep(0.5)

        title = page.title()
        html = page.content()

        context.close()
        browser.close()

        return (title, html)


def parse_escanteios_generic(html: str) -> dict[str, float]:
    """
    Extrai odds de escanteios de forma genérica a partir do HTML renderizado.
    A estratégia:
      1) extrai todo o texto (BeautifulSoup)
      2) procura padrões do tipo:
         (Mais|Menos) de {número}.5 escanteios ... {odd}
    Isso funciona como base para Betano/Bet365/KTO, mas os sites mudam muito;
    se algum não aparecer, ajustamos o regex/heurística depois.
    Retorna dict: { 'Mais de 9.5 escanteios': 1.85, ... }
    """
    if not html:
        return {}

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ").lower()
    text = re.sub(r"\s+", " ", text)

    # Mercados que vamos capturar (ex.: "mais de 8.5 escanteios" e "menos de 8.5 escanteios")
    # Regex: pega "mais/menos de X.Y escanteio(s)" e alguma odd tipo 1.85 / 2,10 logo depois
    # Guardamos uma janela de até 60 caracteres após o mercado para buscar a odd.
    markets = {}
    patt_market = re.compile(r"(mais|menos)\s+de\s+(\d+(?:[.,]\d+)?)\s+escanteios?", re.IGNORECASE)
    patt_odd = re.compile(r"\b(\d+(?:[.,]\d+)?)\b")  # odds do tipo 1.85 2,05 etc.

    for m in patt_market.finditer(text):
        side = m.group(1)  # mais|menos
        line_raw = m.group(2)  # ex 9.5
        start = m.end()
        window = text[start:start + 60]  # pequena janela de texto após o mercado
        # dentro da janela, tenta encontrar a 1ª "odd plausível"
        # (heurística simples – podemos refinar se necessário)
        odd_match = None
        for o in patt_odd.finditer(window):
            val = o.group(1)
            # ignora "números" que são a própria linha (ex 9.5) – queremos a odd
            if val.replace(",", ".") != line_raw.replace(",", "."):
                odd_match = val
                break

        market_name = f"{'Mais' if side.startswith('m') else 'Menos'} de {line_raw.replace(',', '.')} escanteios"
        if odd_match:
            try:
                odd_val = float(odd_match.replace(",", "."))
                # odds razoáveis entre 1.01 e 20.0
                if 1.01 <= odd_val <= 20.0:
                    # guarda somente a primeira encontrada para esse mercado
                    if market_name not in markets:
                        markets[market_name] = odd_val
            except Exception:
                pass

    return markets


def get_house_odds(url: str, headless: bool, timeout_s: int) -> tuple[str, dict[str, float], str]:
    """
    Faz tudo para uma casa:
      - abre a página com Playwright,
      - faz o parse genérico de escanteios,
      - devolve (titulo, dict mercados->odd, msg_erro)
    """
    if not url:
        return ("", {}, "")

    try:
        title, html = open_with_playwright(url, headless=headless, timeout=timeout_s * 1000)
        if not html:
            return (title or "", {}, "Página não retornou conteúdo (HTML vazio).")
        markets = parse_escanteios_generic(html)
        if not markets:
            return (title or "", {}, "Não consegui identificar odds de escanteios nessa página (pode precisar ajustar o detector).")
        return (title or "", markets, "")
    except Exception as e:
        return ("", {}, f"Erro ao carregar: {e}")


def merge_books(betano: dict, bet365: dict, kto: dict) -> pd.DataFrame:
    """
    Junta os dicionários de cada casa em um DataFrame:
       mercado | betano | bet365 | kto
    """
    all_keys = set(betano) | set(bet365) | set(kto)
    rows = []
    for k in sorted(all_keys, key=lambda s: (s.split()[0] != "Mais", s)):  # só para ficar consistente
        rows.append(
            {
                "mercado": k,
                "Betano": betano.get(k, "-"),
                "Bet365": bet365.get(k, "-"),
                "KTO": kto.get(k, "-"),
            }
        )
    return pd.DataFrame(rows)


# --------- Execução ---------
if btn:
    with st.spinner("Abrindo páginas nas casas e extraindo odds..."):
        title_betano, odds_betano, err_betano = get_house_odds(url_betano, run_headless, timeout_s)
        title_bet365, odds_bet365, err_bet365 = get_house_odds(url_bet365, run_headless, timeout_s)
        title_kto, odds_kto, err_kto = get_house_odds(url_kto, run_headless, timeout_s)

    cols = st.columns(3)
    for c, title, err, label in [
        (cols[0], title_betano, err_betano, "Betano"),
        (cols[1], title_bet365, err_bet365, "Bet365"),
        (cols[2], title_kto, err_kto, "KTO"),
    ]:
        with c:
            st.subheader(label)
            if title:
                st.caption(f"Página: {title}")
            if err:
                st.error(err)

    df = merge_books(odds_betano, odds_bet365, odds_kto)
    if not df.empty:
        st.success("Odds extraídas com sucesso (heurística genérica).")
        st.dataframe(df, use_container_width=True)
        st.caption("Obs.: “-” indica que a casa não ofereceu aquele mercado ou o detector não encontrou.")
    else:
        st.warning("Não foi possível montar a tabela. Verifique se as URLs são do mesmo jogo e se a página está acessível.")
