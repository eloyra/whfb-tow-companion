import streamlit as st

st.set_page_config(
    page_title="Warhammer: The Old World Assistant",
    page_icon="⚔️",
    layout="wide",
)

st.title("⚔️ Warhammer: The Old World Assistant")
st.caption("GraphRAG-powered rules assistant and army builder")

# TODO: wire up chat component and graph visualisation
st.info("Backend connection not yet configured. Run `make serve` to start the API.")
