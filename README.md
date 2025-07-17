# Generatore Etichette

Applicazione web per generare etichette da file SAP e DPE.

## Funzionalità

- Caricamento file SAP (Excel)
- Caricamento file DPE (Excel o CSV)
- Filtri per area, rimorchio, tipo ingaggio e tipo gestione
- Generazione etichette in formato Excel
- Download del file generato

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
├── template/
│   └── template.xlsx
├── webapp/
│   └── app.py
└── requirements.txt
```

## Requisiti

- Python 3.9+
- Streamlit
- Pandas
- Openpyxl