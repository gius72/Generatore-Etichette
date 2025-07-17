import requests
import tempfile
import os
import streamlit as st

def get_template_from_url():
    """
    Scarica il template da un URL pubblico (Dropbox)
    e lo restituisce come file temporaneo.
    """
    # URL per il download diretto da GitHub (sostituisci con il tuo username e repository)
    # Formato: https://raw.githubusercontent.com/USERNAME/REPOSITORY/main/template/template.xlsx
    template_url = "https://raw.githubusercontent.com/gius72/Generatore-Etichette/main/template/template.xlsx"
    
    try:
        # Scarica il file
        st.info(f"Tentativo di download da: {template_url}")
        response = requests.get(template_url, timeout=15)
        response.raise_for_status()  # Solleva un'eccezione per errori HTTP
        
        # Crea un file temporaneo
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            template_path = tmp.name
            tmp.write(response.content)
            st.success(f"Template scaricato con successo ({len(response.content)} bytes)")
        
        return template_path
    except Exception as e:
        st.error(f"Errore nel download del template: {e}")
        raise e