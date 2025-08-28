# app.py
import os
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Comparador de Odds – Escanteios", page_icon="📊", layout="wide")
st.title("📊 Comparador de Odds – Escanteios")
st.caption("Leitura de planilha pública (CSV) com cache compartilhado por 15s.")

# --- 1) Lê a URL do Secrets (Streamlit Cloud: Settings → Secrets) ---
def get_sheet_url() -> str:
    # Tenta via st.secrets (recomendado no Cloud) e cai para variável de ambiente
    url = st.secrets.get("SHEET_CSV_URL", None) if hasattr(st, "secrets") else None
    return url or os.getenv("SHEET_CSV_URL", "")

SHEET_URL = get_sheet_url()

# --- 2) Função cacheada para buscar a planilha (CSV) ---
@st.cache_data(ttl=15)  # evita sobrecarga e suporta muitos acessos simultâneos
def read_sheet(csv_url: str) -> pd.DataFrame:
    if not csv_url:
        raise ValueError("SHEET_CSV_URL não encontrado nos Secrets.")
    # read_csv precisa que o link termine com output=csv
    df = pd.read_csv(csv_url)
    return df

# --- 3) Botão de atualização manual (limpa cache) ---
col1, col2 = st.columns([1,3])
with col1:
    if st.button("🔄 Atualizar Odds agora"):
        read_sheet.clear()   # limpa o cache
        st.toast("Cache limpo. Recarregando dados…", icon="✅")

# --- 4) Carrega e exibe dados ---
try:
    df = read_sheet(SHEET_URL)

    if df.empty:
        st.warning("Nenhum dado encontrado na planilha (CSV vazio).")
    else:
        # Se existir a coluna de timestamp, mostra no topo
        ts = None
        for c in df.columns:
            if c.strip().lower() in {"atualizado_em", "updated_at", "timestamp"}:
                ts = df[c].iloc[0] if len(df[c]) else None
                break
        if ts:
            st.info(f"Última atualização da planilha: **{ts}**")

        st.dataframe(df, use_container_width=True)

        st.caption(
            "Obs.: “—” em alguma casa pode indicar que aquele mercado não está disponível no momento."
        )

except Exception as e:
    st.error(f"Erro ao carregar dados da planilha: {e}")
    st.stop()

# --- 5) Rodapé com ajuda rápida ---
with st.expander("Como configurar a planilha (uma vez)", expanded=False):
    st.markdown(
        """
**Passos:**
1. No Google Sheets, deixe as colunas por exemplo: `mercado`, `betano`, `bet365`, `kto`, `atualizado_em`.
2. **Arquivo → Compartilhar → Publicar na Web** → escolha **“Valores separados por vírgulas (.csv)”**.
3. Copie o link gerado (ele deve terminar com `output=csv`).
4. No Streamlit Cloud: **Manage app → Settings → Secrets** e adicione:

```toml
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/SEU_LINK/pub?gid=0&single=true&output=csv"
