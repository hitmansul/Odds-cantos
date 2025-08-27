import streamlit as st

st.set_page_config(page_title="Odds de Escanteios", layout="wide")
st.title("📊 Comparador de Odds – Escanteios")
st.caption("Cole os links do mesmo jogo em cada casa e clique em Atualizar.")

# Campos para links
c1, c2, c3 = st.columns(3)
with c1: link_betano = st.text_input("Link Betano")
with c2: link_bet365 = st.text_input("Link Bet365")
with c3: link_kto    = st.text_input("Link KTO")

# Botão de atualização manual
if st.button("🔄 Atualizar Odds"):
    # >>> TROCAR por scraping real depois <<<
    mercados = [
        "Mais de 9.5 escanteios", 
        "Menos de 9.5 escanteios", 
        "Mais de 10.5 escanteios"
    ]
    odds = {
        "Betano": [1.85, 1.95, 2.10],
        "Bet365": ["—", "—", 2.15],
        "KTO":    [1.87, 1.96, 2.60],
    }
    st.success("Odds atualizadas!")
    st.table({
        "Mercado": mercados,
        "Betano": odds["Betano"],
        "Bet365": odds["Bet365"],
        "KTO":    odds["KTO"],
    })

st.markdown("---")
st.subheader("🔑 Painel (básico)")
st.caption("Use o botão **Share** do Streamlit Cloud para convidar/retirar acesso por e-mail. O histórico de visitas aparece em *App analytics* do Cloud.")
