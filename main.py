import os
import requests
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configurar logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializar app
app = FastAPI(title="API EUDR - Whisp Integration")

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Variables de entorno
WHISP_API_KEY = os.getenv("WHISP_API_KEY", "")
WHISP_ENDPOINT = os.getenv("WHISP_ENDPOINT", "https://whisp.openforis.org/submit/geojson")

# Logs de inicio
logger.info("=" * 50)
logger.info("🚀 Servidor iniciado")
logger.info(f"🔑 WHISP_API_KEY configurada: {'Sí' if WHISP_API_KEY else 'NO'}")
logger.info(f"📝 Longitud de la clave: {len(WHISP_API_KEY) if WHISP_API_KEY else 0} caracteres")
logger.info(f"🌐 WHISP_ENDPOINT: {WHISP_ENDPOINT}")
logger.info("=" * 50)

# Modelo de datos
class DatosSolicitud(BaseModel):
    productor: str
    cedula: str
    telefono: str
    finca: str
    area_ha: float
    geojson: dict

# Endpoint de prueba
@app.get("/")
def home():
    return {
        "estado": "Servidor Activo",
        "mensaje": "API EUDR - Whisp Integration",
        "whisp_configured": bool(WHISP_API_KEY),
        "whisp_endpoint": WHISP_ENDPOINT
    }

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "whisp_configured": bool(WHISP_API_KEY),
        "whisp_key_length": len(WHISP_API_KEY) if WHISP_API_KEY else 0
    }

# Endpoint principal
@app.post("/api/analizar")
def analizar_poligono(solicitud: DatosSolicitud):
    logger.info("=" * 50)
    logger.info("📥 NUEVA SOLICITUD RECIBIDA")
    logger.info(f"👤 Productor: {solicitud.productor}")
    logger.info(f"📍 Finca: {solicitud.finca}")
    logger.info(f"📐 Área: {solicitud.area_ha} ha")
    
    # 1. VERIFICAR CLAVE
    if not WHISP_API_KEY:
        logger.error("❌ WHISP_API_KEY no está configurada.")
        return {
            "exito": False,
            "dictamen": "❌ ERROR: La clave de Whisp no está configurada en el servidor.\n\nPor favor, configura la variable WHISP_API_KEY en Render."
        }
    
    logger.info(f"🔑 Clave presente (longitud: {len(WHISP_API_KEY)})")
    
    # 2. PREPARAR GEOJSON
    try:
        geojson_data = solicitud.geojson
        logger.info(f"📊 Tipo de GeoJSON recibido: {geojson_data.get('type')}")
        
        # Normalizar a FeatureCollection
        if geojson_data.get("type") != "FeatureCollection":
            if geojson_data.get("type") == "Feature":
                geojson_data = {
                    "type": "FeatureCollection",
                    "features": [geojson_data]
                }
            else:
                geojson_data = {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": geojson_data,
                            "properties": {}
                        }
                    ]
                }
            logger.info("🔄 GeoJSON normalizado a FeatureCollection")
        
        logger.info(f"📦 Número de features: {len(geojson_data.get('features', []))}")
        
    except Exception as e:
        logger.error(f"❌ Error preparando GeoJSON: {str(e)}")
        return {
            "exito": False,
            "dictamen": f"❌ Error en el formato del GeoJSON: {str(e)}"
        }
    
    # 3. CONECTAR CON WHISP
    try:
        logger.info(f"🌐 Enviando petición a: {WHISP_ENDPOINT}")
        
        headers = {
            "x-api-key": WHISP_API_KEY,
            "Content-Type": "application/json"
        }
        
        # Log del payload (primeros 200 caracteres)
        import json
        payload_str = json.dumps(geojson_data)
        logger.info(f"📤 Tamaño del payload: {len(payload_str)} bytes")
        
        response = requests.post(
            WHISP_ENDPOINT,
            json=geojson_data,
            headers=headers,
            timeout=35
        )
        
        logger.info(f"📥 Código de respuesta de Whisp: {response.status_code}")
        
        # 4. PROCESAR RESPUESTA
        if response.status_code == 200:
            data = response.json()
            logger.info("✅ Conexión con Whisp EXITOSA")
            logger.info(f"📄 Respuesta recibida: {json.dumps(data, indent=2)[:500]}...")
            
            # Extraer datos
            try:
                if isinstance(data, dict) and "data" in data and data["data"]:
                    items = data["data"] if isinstance(data["data"], list) else [data["data"]]
                    
                    if items and len(items) > 0:
                        item = items[0]
                        
                        # Extraer valores
                        hansen = float(item.get("GFC_loss_after_2020", item.get("gfc_loss_ha", 0)))
                        tmf = float(item.get("TMF_def_after_2020", item.get("tmf_loss_ha", 0)))
                        radd = float(item.get("RADD_after_2020", item.get("radd_alerts_ha", 0)))
                        total = hansen + tmf + radd
                        
                        logger.info(f"📊 Resultados: Hansen={hansen}, TMF={tmf}, RADD={radd}, Total={total}")
                        
                        # Determinar riesgo
                        if total > 0.01:
                            nivel_riesgo = "🔴 RIESGO ALTO"
                            emoji = "🔴"
                        else:
                            nivel_riesgo = "🟢 RIESGO BAJO"
                            emoji = "🟢"
                        
                        # Generar dictamen
                        dictamen = f"""
MINISTERIO AGROPECUARIO / DPTO SIG
PORTAL DE DEBIDA DILIGENCIA EUDR

1. DATOS DE LA PARCELA:
- Productor: {solicitud.productor}
- Cédula: {solicitud.cedula}
- Teléfono: {solicitud.telefono}
- Finca: {solicitud.finca}
- Área: {solicitud.area_ha:.4f} ha

2. DICTAMEN DE EVALUACIÓN:
--> {nivel_riesgo} <--

3. ANÁLISIS SATELITAL (DATOS REALES):
- GFC (Hansen) post-2020: {hansen:.4f} ha
- TMF (JRC) post-2020: {tmf:.4f} ha
- RADD post-2020: {radd:.4f} ha
- Total deforestado: {total:.4f} ha

4. PORCENTAJE DE AFECTACIÓN:
{((total / solicitud.area_ha) * 100) if solicitud.area_ha > 0 else 0:.2f}% de la finca

{"⚠️ Se requiere verificación en campo." if total > 0.01 else "✅ Parcela apta para exportación EUDR."}
"""
                        return {"exito": True, "dictamen": dictamen}
                    else:
                        logger.warning("⚠️ No hay datos en la respuesta de Whisp")
                        return {
                            "exito": False,
                            "dictamen": "⚠️ Whisp respondió pero no devolvió datos.\n\n" + json.dumps(data, indent=2)
                        }
                else:
                    logger.warning("⚠️ Respuesta de Whisp sin datos")
                    return {
                        "exito": False,
                        "dictamen": "⚠️ La respuesta de Whisp no contiene datos.\n\n" + json.dumps(data, indent=2)
                    }
                    
            except Exception as e:
                logger.error(f"❌ Error procesando datos: {str(e)}")
                return {
                    "exito": False,
                    "dictamen": f"❌ Error procesando la respuesta de Whisp: {str(e)}"
                }
        
        elif response.status_code == 401:
            logger.error("❌ Error 401: Clave de Whisp INVÁLIDA")
            return {
                "exito": False,
                "dictamen": """❌ ERROR DE AUTENTICACIÓN

La clave de Whisp es inválida o ha expirado.

SOLUCIÓN:
1. Ve a la plataforma de Whisp
2. Genera una nueva clave API
3. Actualiza WHISP_API_KEY en Render
4. Reinicia el servicio"""
            }
        else:
            logger.error(f"❌ Whisp respondió con error {response.status_code}")
            logger.error(f"❌ Respuesta: {response.text[:500]}")
            return {
                "exito": False,
                "dictamen": f"""❌ Whisp respondió con error {response.status_code}

Detalles: {response.text[:200]}

Revisa los logs de Render para más información."""
            }
            
    except requests.exceptions.Timeout:
        logger.error("⏰ Timeout al conectar con Whisp")
        return {
            "exito": False,
            "dictamen": """⏰ ERROR: Tiempo de espera agotado

Whisp no respondió dentro del tiempo límite (35 segundos).

Posibles causas:
- La API de Whisp está lenta o caída
- El polígono es muy grande
- Problemas de red

Intenta nuevamente o reduce el tamaño del polígono."""
        }
        
    except requests.exceptions.ConnectionError:
        logger.error("🔌 Error de conexión con Whisp")
        return {
            "exito": False,
            "dictamen": """🔌 ERROR DE CONEXIÓN

No se pudo conectar con el servidor de Whisp.

Verifica:
1. Tu conexión a internet
2. Que el endpoint sea correcto
3. Que el servicio de Whisp esté activo"""
        }
        
    except Exception as e:
        logger.error(f"💥 Error inesperado: {str(e)}")
        return {
            "exito": False,
            "dictamen": f"""💥 ERROR INESPERADO

{str(e)}

Revisa los logs de Render para más detalles."""
        }

# Punto de entrada para ejecución local
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
