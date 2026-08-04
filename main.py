import os
import time
import requests
import json
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

WHISP_API_KEY = os.getenv("WHISP_API_KEY", "")
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
        "mensaje": "API EUDR - Versión Simplificada",
        "whisp_configured": bool(WHISP_API_KEY and WHISP_API_KEY != "tu_clave_aqui")
    }

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/api/analizar")
def analizar_poligono(solicitud: DatosSolicitud):
    # Datos de ejemplo si no hay Whisp
    if not WHISP_API_KEY or WHISP_API_KEY == "tu_clave_aqui":
        return generar_respuesta_simulada(solicitud)
    
    try:
        # Intentar con Whisp
        headers = {
            "x-api-key": WHISP_API_KEY,
            "Content-Type": "application/json"
        }
        
        # Preparar GeoJSON
        geojson_data = solicitud.geojson
        if geojson_data.get("type") != "FeatureCollection":
            geojson_data = {
                "type": "FeatureCollection",
                "features": [geojson_data] if geojson_data.get("type") == "Feature" else [
                    {"type": "Feature", "geometry": geojson_data, "properties": {}}
                ]
            }
        
        response = requests.post(WHISP_BASE_URL, json=geojson_data, headers=headers, timeout=30)
        
        if response.status_code in [200, 201]:
            data = response.json()
            return procesar_respuesta_whisp(data, solicitud)
        else:
            return generar_respuesta_simulada(solicitud, error="Whisp no disponible")
            
    except Exception as e:
        return generar_respuesta_simulada(solicitud, error=str(e))

def generar_respuesta_simulada(solicitud, error=None):
    dictamen = f"""MINISTERIO AGROPECUARIO / DPTO SIG
PORTAL DE DEBIDA DILIGENCIA EUDR

1. DATOS DE LA PARCELA:
- Productor: {solicitud.productor}
- Cédula: {solicitud.cedula}
- Teléfono: {solicitud.telefono}
- Finca: {solicitud.finca}
- Área: {solicitud.area_ha:.4f} ha

2. DICTAMEN:
✅ RIESGO BAJO (Análisis Simulado)

3. NOTA IMPORTANTE:
Este es un resultado de demostración.
Para análisis real, configura WHISP_API_KEY.
"""
    if error:
        dictamen += f"\n\n⚠️ Error: {error}"
    
    return {"exito": True, "dictamen": dictamen}

def procesar_respuesta_whisp(data, solicitud):
    # Procesar datos reales de Whisp
    try:
        if isinstance(data, dict) and "data" in data and data["data"]:
            item = data["data"][0] if isinstance(data["data"], list) else data["data"]
            
            hansen = float(item.get("GFC_loss_after_2020", 0))
            tmf = float(item.get("TMF_def_after_2020", 0))
            radd = float(item.get("RADD_after_2020", 0))
            total = hansen + tmf + radd
            
            riesgo = "ALTO" if total > 0.01 else "BAJO"
            
            dictamen = f"""MINISTERIO AGROPECUARIO / DPTO SIG
PORTAL DE DEBIDA DILIGENCIA EUDR

1. DATOS DE LA PARCELA:
- Productor: {solicitud.productor}
- Finca: {solicitud.finca}
- Área: {solicitud.area_ha:.4f} ha

2. DICTAMEN:
{'🔴 RIESGO ALTO' if riesgo == 'ALTO' else '🟢 RIESGO BAJO'}

3. ANÁLISIS SATELITAL:
- GFC (Hansen): {hansen:.4f} ha
- TMF (JRC): {tmf:.4f} ha
- RADD: {radd:.4f} ha
- Total deforestado: {total:.4f} ha
"""
            return {"exito": True, "dictamen": dictamen}
        else:
            return generar_respuesta_simulada(solicitud, error="Respuesta de Whisp inválida")
    except Exception as e:
        return generar_respuesta_simulada(solicitud, error=f"Error procesando: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
