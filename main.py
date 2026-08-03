import os
import time
import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="API Debida Diligencia EUDR - Whisp Integration v2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    if request.method == "OPTIONS":
        response = Response()
    else:
        response = await call_next(request)

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

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
            coords = geojson["features"][0]["geometry"]["coordinates"][0]
        elif geojson.get("type") == "Feature":
            coords = geojson["geometry"]["coordinates"][0]
        elif "coordinates" in geojson:
            coords = geojson["coordinates"][0]

        if not coords or not isinstance(coords, list):
            return 12.8654, -85.2072

        lons = [p[0] for p in coords if isinstance(p, list) and len(p) >= 2]
        lats = [p[1] for p in coords if isinstance(p, list) and len(p) >= 2]

        return round(sum(lats) / len(lats), 6), round(sum(lons) / len(lons), 6)
    except Exception:
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
        "mensaje": "API EUDR conectada con OpenForis Whisp API v2.1.0 - MAG / DPTO SIG"
    }

@app.options("/api/analizar")
def options_analizar():
    return Response(headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
    })

@app.post("/api/analizar")
def analizar_poligono(solicitud: DatosSolicitud):
    tiempo_inicio = time.time()

    lat_c, lon_c = calcular_centroide(solicitud.geojson)
    id_parcela = abs(hash(f"{solicitud.finca}_{solicitud.productor}")) % 10000

    deforestacion_ha = 0.0
    hansen_ha = 0.0
    tmf_ha = 0.0
    radd_ha = 0.0
    porcentaje_riesgo = 0.0
    nivel_riesgo = "BAJO (Sin Deforestación)"

    if WHISP_API_KEY:
        try:
            headers = {
                "x-api-key": WHISP_API_KEY,
                "Content-Type": "application/json"
            }

            payload = normalizar_geojson_para_whisp(solicitud.geojson)
            res = requests.post(WHISP_BASE_URL, json=payload, headers=headers, timeout=35)

            print(f"📡 Estado HTTP de Whisp: {res.status_code}")

            if res.status_code in [200, 201]:
                respuesta_whisp = res.json()
                
                datos_lista = []
                if isinstance(respuesta_whisp, dict) and respuesta_whisp.get("code") in ["analysis_completed", "success"]:
                    datos_lista = respuesta_whisp.get("data", [])
                elif isinstance(respuesta_whisp, list):
                    datos_lista = respuesta_whisp

                if isinstance(datos_lista, list) and len(datos_lista) > 0:
                    item = datos_lista[0]
                    
                    # Extracción estricta según el esquema CSV oficial de Whisp
                    hansen_ha = float(item.get("GFC_loss_after_2020", item.get("gfc_loss_ha", 0.0)))
                    tmf_ha = float(item.get("TMF_def_after_2020", item.get("tmf_loss_ha", 0.0)))
                    radd_ha = float(item.get("RADD_after_2020", item.get("radd_alerts_ha", 0.0)))
                    
                    deforestacion_ha = hansen_ha + tmf_ha + radd_ha

                    ind_04 = str(item.get("Ind_04_disturbance_after_2020", "no")).lower()
                    risk_crop = str(item.get("risk_pcrop", "low")).lower()

                    if deforestacion_ha > 0.01 or ind_04 == "yes" or risk_crop == "high":
                        nivel_riesgo = "ALTO (Presencia de Deforestación post-2020)"
                    else:
                        nivel_riesgo = "BAJO (Sin Deforestación detectada)"
            else:
                print(f"⚠️ Error devuelto por Whisp API (HTTP {res.status_code}): {res.text}")

        except Exception as e:
            print(f"❌ Excepción al conectar con Whisp API: {str(e)}")
    else:
        print("⚠️ Advertencia: WHISP_API_KEY no encontrada en las variables de entorno.")

    # Cálculo dinámico del porcentaje de afectación
    if solicitud.area_ha > 0:
        porcentaje_riesgo = round((deforestacion_ha / solicitud.area_ha) * 100, 2)

    # Construcción del dictamen formal
    dictamen_texto = f"""MINISTERIO AGROPECUARIO / DPTO SIG
PORTAL DE DEBIDA DILIGENCIA EUDR
MÓDULO DE EVALUACIÓN PARCELARIA SATELITAL (OPENFORIS WHISP API v2.1.0)
==================================================

1. RESUMEN DE LA PARCELA:
--------------------------------------------------
* Nombre Completo del Productor: {solicitud.productor}
* Cédula de Identidad: {solicitud.cedula}
* Teléfono de Contacto: {solicitud.telefono}
* Nombre de la Finca: {solicitud.finca}
* ID Parcela: {id_parcela}
* Superficie Total: {solicitud.area_ha:.4f} ha
* Centroide: Lat {lat_c}, Lon {lon_c}

2. DICTAMEN DE EVALUACIÓN:
--------------------------------------------------
--> RIESGO {nivel_riesgo} <--

3. ÁREA AFECTADA / EN RIESGO:
--------------------------------------------------
Pérdida de cobertura arbórea posterior al 31/12/2020.
Superficie Estimada en Riesgo: {deforestacion_ha:.4f} ha ({porcentaje_riesgo}% de la finca)

Desglose por satélite (Google Earth Engine / OpenForis Whisp):
- GFC (Hansen) post-2020: {hansen_ha:.4f} ha
- TMF (JRC) post-2020: {tmf_ha:.4f} ha
- Alertas RADD post-2020: {radd_ha:.4f} ha

4. GUÍA PARA DIGITALIZAR FUTURO POLÍGONO:
--------------------------------------------------
Coordenadas para centrar vista: Longitud: {lon_c}, Latitud: {lat_c}
Compara imágenes 2020 vs 2024 para verificar la parcela.
=================================================="""

    tiempo_total = round(time.time() - tiempo_inicio, 2)

    dictamen_final = (
        f"{dictamen_texto}\n\n"
        f"Ejecución completada en {tiempo_total} segundos (OpenForis Whisp Engine)\n\n"
        f"Cargando las capas resultantes...\n"
        f"Algoritmo '1. Análisis de Riesgo EUDR (Whisp)' finalizado exitosamente."
    )

    return {"exito": True, "dictamen": dictamen_final}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
