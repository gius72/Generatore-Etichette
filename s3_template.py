import requests
import tempfile
import os

# URL pubblico del template su Amazon S3 o altro servizio di storage
TEMPLATE_URL = "https://tuo-bucket.s3.amazonaws.com/template.xlsx"

def download_template():
    """
    Scarica il template da S3 e lo salva in un file temporaneo
    
    Returns:
        str: Percorso del file temporaneo contenente il template
    """
    try:
        response = requests.get(TEMPLATE_URL)
        response.raise_for_status()  # Solleva un'eccezione per errori HTTP
        
        # Salva il contenuto in un file temporaneo
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(response.content)
            return tmp.name
    except Exception as e:
        raise Exception(f"Errore nel download del template: {e}")