import os
import pandas as pd
import streamlit as st

# Puxa a URL do Secrets
URL_CSV = os.environ.get("SHEET_CSV_URL")
@st.cache_data(ttl=15)  # cache de 15s para não sobrecarregar
def read_sheet(url):
    return pd.read_csv(url)

st.title("📊 Comparador de Odds – Escanteios")

try:
    df = read_sheet(CSV_URL)

    if df.empty:
        st.warning("Nenhum dado encontrado na planilha.")
    else:
        st.success("Odds atualizadas com sucesso!")
        st.dataframe(df, use_container_width=True)

except Exception as e:
    st.error(f"Erro ao carregar dados da planilha: {e}")
