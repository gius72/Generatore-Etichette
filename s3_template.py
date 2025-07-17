import requests
import tempfile
import os
import streamlit as st

def get_template_from_url():
    """
    Scarica il template da un URL pubblico (Dropbox, S3, ecc.)
    e lo restituisce come file temporaneo.
    """
    # URL del template su Dropbox (sostituire con il tuo URL pubblico)
    # Nota: per Dropbox, usa un link condiviso e sostituisci 'www.dropbox.com' con 'dl.dropboxusercontent.com'
    # e rimuovi '?dl=0' alla fine
    template_url = "https://www.dropbox.com/scl/fi/ekml0jntrd2bcbz9kyrbg/template.xlsx?dl=1"
    
    try:
        # Scarica il file
        response = requests.get(template_url, timeout=10)
        response.raise_for_status()  # Solleva un'eccezione per errori HTTP
        
        # Crea un file temporaneo
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            template_path = tmp.name
            tmp.write(response.content)
        
        return template_path
    except Exception as e:
        st.error(f"Errore nel download del template: {e}")
        raise e