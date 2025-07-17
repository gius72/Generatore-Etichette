# Generatore Etichette

Applicazione web per generare etichette da file SAP e DPE.

## Funzionalità

- Caricamento file SAP (Excel)
- Caricamento file DPE (Excel o CSV) con rilevamento automatico del formato
- Filtri per area, rimorchio, tipo ingaggio e tipo gestione
- Generazione etichette in formato Excel
- Download del file generato
- Template incorporato nel codice

## Deploy su Render.com

1. Crea un account su [Render.com](https://render.com)
2. Collega il tuo repository GitHub
3. Crea un nuovo Web Service
4. Configura il deploy:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `streamlit run webapp/app.py --server.port=$PORT --server.address=0.0.0.0`
   - **Environment**: Python 3

## Struttura del progetto

```
Generatore Etichette/
├── webapp/
│   ├── app.py
│   └── template_embedded.py
└── requirements.txt
```

## Requisiti

- Python 3.9+
- Streamlit
- Pandas
- Openpyxl

## Note sul template

L'applicazione può utilizzare il template in due modi diversi:

1. **Template da Dropbox**: L'applicazione scarica il template da un link Dropbox pubblico. Questo permette di utilizzare un template formattato esattamente come desiderato.

2. **Template caricato dall'utente**: È possibile caricare un template personalizzato direttamente nell'interfaccia web.

### Configurazione del template Dropbox

1. Carica il file `template.xlsx` su Dropbox
2. Crea un link di condivisione pubblico
3. Modifica il link sostituendo `www.dropbox.com` con `dl.dropboxusercontent.com` e rimuovendo `?dl=0` alla fine
4. Inserisci il link nel file `webapp/s3_template.py`