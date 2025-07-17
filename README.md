# Modulo Webapp

Questo modulo contiene l'applicazione web Streamlit per il generatore di etichette.

## File principali

- `app.py`: Applicazione principale Streamlit
- `template_embedded.py`: Template Excel incorporato come base64

## Funzionamento

L'applicazione utilizza un template Excel incorporato direttamente nel codice come stringa base64, 
eliminando la necessità di file esterni e garantendo il funzionamento su qualsiasi ambiente, 
incluso Render.com.

## Utilizzo

Per avviare l'applicazione in locale:

```bash
streamlit run app.py
```

Per il deploy su Render.com, seguire le istruzioni nel README principale.