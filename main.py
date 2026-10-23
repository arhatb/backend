import os
from datetime import datetime, timezone

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from decision_engine import make_decision
from database import create_database, save_sensor_data, get_sensor_data, get_latest_sensor_data
from sentinel_service import get_sentinel_data
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI(
    title="Backend API",
    version="1.0.0"
)
# Ek adresler Render panelinden CORS_ORIGINS=https://site1.com,https://site2.com ile verilebilir.
_extra = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://arhatb.github.io",
        "https://arhatbasut.com",
        "https://www.arhatbasut.com",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        *_extra,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
create_database()
@app.get("/")
def home():
    return {
        "status": "online",
        "message": "Backend API calisiyor"
    }
@app.get("/api/weather")
def get_weather(latitude: float, longitude: float):

    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "precipitation,"
            "wind_speed_10m"
        ),
        "timezone": "auto"
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        response.raise_for_status()
        weather = response.json()["current"]

        return {
            "status": "success",
            "location": {
                "latitude": latitude,
                "longitude": longitude
            },
            "weather": {
                "temperature": weather["temperature_2m"],
                "humidity": weather["relative_humidity_2m"],
                "precipitation": weather["precipitation"],
                "wind_speed": weather["wind_speed_10m"],
                "time": weather["time"]
            }
        }

    except Exception as error:
        return {
            "status": "error",
            "message": str(error)
        }
class SensorData(BaseModel):
    device_id: str
    temperature: float
    humidity: float
    soil_moisture: float


@app.post("/api/sensors")
def receive_sensor_data(data: SensorData):

    save_sensor_data(
        data.device_id,
        data.temperature,
        data.humidity,
        data.soil_moisture
    )

    return {
        "status": "success",
        "message": "Sensor verisi veritabanina kaydedildi",
        "data": data
    }
@app.get("/api/sensors")
def read_sensor_data():
    data = get_sensor_data()

    return {
        "status": "success",
        "count": len(data),
        "data": data
    }
STALE_AFTER_MINUTES = 15


@app.get("/api/decision")
def get_decision(device_id: str | None = None):
    latest = get_latest_sensor_data(device_id)

    if not latest:
        raise HTTPException(status_code=404, detail="Sensor verisi bulunamadi")

    decision = make_decision(
        latest["temperature"],
        latest["humidity"],
        latest["soil_moisture"]
    )

    # created_at SQLite'ta UTC olarak "YYYY-MM-DD HH:MM:SS" biçiminde tutulur.
    age_minutes = None
    try:
        created = datetime.strptime(latest["created_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        age_minutes = max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 60)
    except (TypeError, ValueError):
        pass

    return {
        "status": "success",
        "sensor_data": latest,
        "age_minutes": age_minutes,
        "stale": age_minutes is None or age_minutes > STALE_AFTER_MINUTES,
        "decision": decision
    }


@app.get("/api/sentinel")
def sentinel_data(latitude: float, longitude: float):
    try:
        result = get_sentinel_data(latitude, longitude)
    except requests.RequestException as error:
        raise HTTPException(status_code=502, detail=f"Copernicus servisine ulasilamadi: {error}")

    if result is None:
        raise HTTPException(status_code=404, detail="Son 30 gunde bulutsuz Sentinel-2 goruntusu bulunamadi")
    return result
