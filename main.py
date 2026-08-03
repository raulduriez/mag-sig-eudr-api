import os
import time
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="API Debida Diligencia EUDR - Whisp Integration")

# Configuración CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WHISP_API_KEY = os.getenv("WHISP_API_KEY")
WHISP_BASE_URL = os.getenv("WHISP_ENDPOINT", "https://whisp.openforis.org/submit/geojson")

class DatosSolicitud(BaseModel):
    productor: str
    cedula: str
    telefono: str
    finca: str
    area_ha: float
    geojson: dict

@app.get("/")
def home():
    return {
        "estado": "Servidor Activo",
        "mensaje": "API EUDR conectada con OpenForis Whisp API",
        "whisp_configured": bool(WHISP_API_KEY)
    }

@app.post("/api/analizar")
def analizar_poligono(solicitud: DatosSolicitud):
    # Simulación para pruebas si no hay WHISP_API_KEY
    if not WHISP_API_KEY:
        return {
            "exito": True,
            "dictamen": f"""
MINISTERIO AGROPECUARIO / DPTO SIG
PORTAL DE DEBIDA DILIGENCIA EUDR
MÓDULO DE EVALUACIÓN PARCELARIA SATELITAL

1. RESUMEN DE LA PARCELA:
- Productor: {solicitud.productor}
- Finca: {solicitud.finca}
- Área: {solicitud.area_ha:.4f} ha

2. DICTAMEN:
RIESGO BAJO (Sin Deforestación detectada - MODO DEMO)

3. NOTA: WHISP_API_KEY no configurada. 
   Los resultados son simulados para pruebas.
"""
        }
    
    # Aquí va tu código real con Whisp
    try:
        # ... tu código existente ...
        pass
    except Exception as e:
        return {"exito": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
