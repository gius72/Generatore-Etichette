# Generatore Etichette WebApp

Questa è la versione web del Generatore Etichette, realizzata con Streamlit.

## Come eseguire localmente

1. Installa le dipendenze:
   ```bash
   pip install -r requirements.txt
   ```
2. Avvia la web app:
   ```bash
   streamlit run app.py
   ```

## Deploy su Render.com

- Carica questa cartella su GitHub.
- Su Render.com, crea un nuovo servizio Web e collega il repository.
- Imposta il comando di avvio: `streamlit run app.py --server.port $PORT`.

## Funzionalità
- Caricamento file SAP, DPE e template etichette
- Selezione filtri
- Generazione etichette (in sviluppo)
