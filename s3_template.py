import os
import tempfile

import requests
import streamlit as st

# Template scaricato da GitHub solo come fallback (file assente nel repository)
TEMPLATE_URL_FALLBACK = (
    "https://raw.githubusercontent.com/gius72/Generatore-Etichette/main/template/template.xlsx"
)


def get_template_path():
    """
    Restituisce il percorso del template da usare per generare le etichette.

    Ogni ambiente usa il template del PROPRIO branch: il file e' incluso nel
    repository (template/template.xlsx), quindi il deploy su main usa il template
    di main e quello su test usa il template di test, senza modifiche al codice.

    Se il file non fosse presente nel deploy (repo clonato parzialmente), si
    scarica il template di main da GitHub come fallback (comportamento storico).
    """
    percorso_locale = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "template", "template.xlsx"
    )
    if os.path.isfile(percorso_locale):
        return percorso_locale

    st.warning(
        "Template non trovato nel repository: uso quello scaricato da GitHub (branch main)."
    )
    try:
        risposta = requests.get(TEMPLATE_URL_FALLBACK, timeout=15)
        risposta.raise_for_status()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            percorso_temp = tmp.name
            tmp.write(risposta.content)

        return percorso_temp
    except Exception as e:
        st.error(f"Errore nel download del template: {e}")
        raise e


# Nome storico mantenuto per compatibilita' con eventuali import esterni
get_template_from_url = get_template_path
