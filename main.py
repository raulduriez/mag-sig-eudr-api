import os
import time
import requests
import logging
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="API Debida Diligencia EUDR - Whisp Integration v2.1.0")

# Configuración CORS mejorada
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

def calcular_centroide(geojson: dict):
    try:
        coords = []
        if geojson.get("type") == "FeatureCollection":
            if geojson["features"] and len(geojson["features"]) > 0:
                coords = geojson["features"][0]["geometry"]["coordinates"][0]
        elif geojson.get("type") == "Feature":
            coords = geojson["geometry"]["coordinates"][0]
        elif "coordinates" in geojson:
            coords = geojson["coordinates"][0]

        if not coords or not isinstance(coords, list):
            return 12.8654, -85.2072

        lons = [p[0] for p in coords if isinstance(p, list) and len(p) >= 2]
        lats = [p[1] for p in coords if isinstance(p, list) and len(p) >= 2]

        if lats and lons:
            return round(sum(lats) / len(lats), 6), round(sum(lons) / len(lons), 6)
        return 12.8654, -85.2072
    except Exception as e:
        logger.error(f"Error calculando centroide: {e}")
        return 12.8654, -85.2072

def normalizar_geojson_para_whisp(geojson_in: dict):
    """Garantiza que el GeoJSON tenga la estructura FeatureCollection requerida por Whisp."""
    if geojson_in.get("type") == "FeatureCollection":
        return geojson_in
    elif geojson_in.get("type") == "Feature":
        return {
            "type": "FeatureCollection",
            "features": [geojson_in]
        }
    else:
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": geojson_in
                }
            ]
        }

@app.get("/")
def home():
    return {
        "estado": "Servidor Activo",
        "mensaje": "API EUDR conectada con OpenForis Whisp API",
        "version": "2.1.0",
        "whisp_configured": bool(WHISP_API_KEY),
        "status": "online"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "whisp_api": "configured" if WHISP_API_KEY else "missing"}

@app.post("/api/analizar")
def analizar_poligono(solicitud: DatosSolicitud):
    tiempo_inicio = time.time()
    logger.info(f"Analizando polígono para: {solicitud.productor} - {solicitud.finca}")

    lat_c, lon_c = calcular_centroide(solicitud.geojson)
    id_parcela = abs(hash(f"{solicitud.finca}_{solicitud.productor}")) % 10000

    # Valores por defecto
    deforestacion_ha = 0.0
    hansen_ha = 0.0
    tmf_ha = 0.0
    radd_ha = 0.0
    nivel_riesgo = "BAJO (Sin Deforestación)"
    whisp_exitoso = False

    # Intentar conectar con Whisp
    if WHISP_API_KEY and WHISP_API_KEY != "tu_clave_aqui":
        try:
            headers = {
                "x-api-key": WHISP_API_KEY,
                "Content-Type": "application/json"
            }

            payload = normalizar_geojson_para_whisp(solicitud.geojson)
            
            logger.info(f"Enviando solicitud a Whisp: {WHISP_BASE_URL}")
            res = requests.post(WHISP_BASE_URL, json=payload, headers=headers, timeout=35)
            
            logger.info(f"Respuesta de Whisp: {res.status_code}")

            if res.status_code in [200, 201]:
                respuesta_whisp = res.json()
                whisp_exitoso = True
                
                # Procesar respuesta...
                datos_lista = []
                if isinstance(respuesta_whisp, dict) and respuesta_whisp.get("code") in ["analysis_completed", "success"]:
                    datos_lista = respuesta_whisp.get("data", [])
                elif isinstance(respuesta_whisp, list):
                    datos_lista = respuesta_whisp

                if datos_lista and len(datos_lista) > 0:
                    item = datos_lista[0]
                    hansen_ha = float(item.get("GFC_loss_after_2020", item.get("gfc_loss_ha", 0.0)))
                    tmf_ha = float(item.get("TMF_def_after_2020", item.get("tmf_loss_ha", 0.0)))
                    radd_ha = float(item.get("RADD_after_2020", item.get("radd_alerts_ha", 0.0)))
                    deforestacion_ha = hansen_ha + tmf_ha + radd_ha

                    if deforestacion_ha > 0.01:
                        nivel_riesgo = "ALTO (Presencia de Deforestación post-2020)"
                    else:
                        nivel_riesgo = "BAJO (Sin Deforestación detectada)"
            else:
                logger.warning(f"Error en Whisp: {res.status_code} - {res.text}")

        except Exception as e:
            logger.error(f"Error conectando con Whisp: {str(e)}")
    else:
        logger.warning("WHISP_API_KEY no configurada correctamente")

    # Cálculo del porcentaje de afectación
    porcentaje_riesgo = round((deforestacion_ha / solicitud.area_ha) * 100, 2) if solicitud.area_ha > 0 else 0

    # Construcción del dictamen
    dictamen_texto = f"""MINISTERIO AGROPECUARIO / DPTO SIG
PORTAL DE DEBIDA DILIGENCIA EUDR
MÓDULO DE EVALUACIÓN PARCELARIA SATELITAL

==================================================
1. RESUMEN DE LA PARCELA:
--------------------------------------------------
* Productor: {solicitud.productor}
* Cédula: {solicitud.cedula}
* Teléfono: {solicitud.telefono}
* Finca: {solicitud.finca}
* ID Parcela: {id_parcela}
* Superficie Total: {solicitud.area_ha:.4f} ha
* Centroide: Lat {lat_c}, Lon {lon_c}

2. DICTAMEN DE EVALUACIÓN:
--------------------------------------------------
--> RIESGO {nivel_riesgo} <--

3. ÁREA AFECTADA / EN RIESGO:
--------------------------------------------------
Superficie Estimada en Riesgo: {deforestacion_ha:.4f} ha ({porcentaje_riesgo}% de la finca)

Desglose por satélite:
- GFC (Hansen) post-2020: {hansen_ha:.4f} ha
- TMF (JRC) post-2020: {tmf_ha:.4f} ha
- Alertas RADD post-2020: {radd_ha:.4f} ha
=================================================="""

    if not whisp_exitoso:
        dictamen_texto += "\n\n⚠️ NOTA: Análisis sin datos de Whisp (modo de simulación)."

    tiempo_total = round(time.time() - tiempo_inicio, 2)
    
    return {
        "exito": True, 
        "dictamen": dictamen_texto,
        "metadata": {
            "tiempo_procesamiento": tiempo_total,
            "whisp_utilizado": whisp_exitoso,
            "area_ha": solicitud.area_ha,
            "deforestacion_ha": deforestacion_ha
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
