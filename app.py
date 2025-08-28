import os
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Comparador de Odds – Escanteios", page_icon="📊", layout="wide")
st.title("📊 Comparador de Odds – Escanteios")
st.caption("Leitura de planilha pública (CSV) com cache compartilhado por 15s.")

# --- 1) Lê a URL do Secrets (Streamlit Cloud: Settings → Secrets) ---
def get_sheet_url() -> str:
    url = st.secrets.get("SHEET_CSV_URL", None) if hasattr(st, "secrets") else None
    return url or os.getenv("SHEET_CSV_URL", "")

SHEET_URL = get_sheet_url()

# --- 2) Função cacheada para buscar a planilha (CSV) ---
@st.cache_data(ttl=15)
def read_sheet(csv_url: str) -> pd.DataFrame:
    if not csv_url:
        raise ValueError("SHEET_CSV_URL não encontrado nos Secrets.")
    return pd.read_csv(csv_url)

# --- 3) Botão de atualização manual ---
if st.button("🔄 Atualizar Odds agora"):
    read_sheet.clear()
    st.toast("Cache limpo. Recarregando dados…", icon="✅")

# --- 4) Carrega e exibe dados ---
try:
    df = read_sheet(SHEET_URL)

    if df.empty:
        st.warning("Nenhum dado encontrado na planilha (CSV vazio).")
    else:
        if "atualizado_em" in df.columns:
            ts = df["atualizado_em"].iloc[0]
            st.info(f"Última atualização da planilha: **{ts}**")

        st.dataframe(df, use_container_width=True)
        st.caption("Obs.: “—” pode indicar que a casa não oferece aquele mercado no momento.")

except Exception as e:
    st.error(f"Erro ao carregar dados da planilha: {e}")
