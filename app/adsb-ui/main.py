import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI(title="ADS-B OSINT Tracker")

# Mount a 'static' directory to serve the frontend HTML/CSS/JS
app.mount("/static", StaticFiles(directory="static"), name="static")

def get_db_connection():
    # Grabs the DSN from the environment variables, injected via Kubernetes secret
    dsn = os.getenv("DB_DSN")
    if not dsn:
        raise ValueError("DB_DSN environment variable is missing.")
    return psycopg2.connect(dsn, cursor_factory=RealDictCursor)

@app.get("/")
def read_root():
    # Serve the main frontend page
    return FileResponse("static/index.html")

@app.get("/api/osint")
def get_osint_data():
    """Fetches OSINT aircraft data joined with their most recent position."""
    query = """
        SELECT a.*, p.lat, p.lon, p.altitude, p.timestamp
        FROM aircraft a
        LEFT JOIN (
            -- PostgreSQL specific syntax to get the most recent row per hex
            SELECT DISTINCT ON (hex) hex, lat, lon, altitude, timestamp
            FROM position
            ORDER BY hex, timestamp DESC
        ) p ON a.hex = p.hex;
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(query)
        records = cur.fetchall()
        cur.close()
        conn.close()
        return {"status": "success", "data": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/local")
def get_local_data():
    """Placeholder for local readsb/tar1090 data."""
    # Returning a dummy payload for now as requested
    return {
        "status": "success", 
        "data": [
            {"hex": "PLACEHOLDER1", "flight": "TEST1", "lat": 56.1612, "lon": 15.5869, "altitude": 35000},
            {"hex": "PLACEHOLDER2", "flight": "TEST2", "lat": 56.1712, "lon": 15.5969, "altitude": 24000}
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
