import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI(title="ADS-B OSINT Tracker")
HTML_DIR = os.getenv("STATIC_HTML_DIR", "/app/adsb-ui/static")

# Mount a 'static' directory to serve the frontend HTML/CSS/JS
app.mount("/app/static", StaticFiles(directory=HTML_DIR), name="static")

def get_db_connection():
    # Grabs the DSN from the environment variables, injected via Kubernetes secret
    dsn = os.getenv("DB_DSN")
    if not dsn:
        raise ValueError("DB_DSN environment variable is missing.")
    return psycopg2.connect(dsn, cursor_factory=RealDictCursor)

@app.get("/")
def read_root():
    # Serve the main frontend page
    return FileResponse(f"{HTML_DIR}/index.html")

@app.get("/api/osint")
def get_osint_data():
    """Fetches OSINT aircraft data joined with their most recent position."""
    query = """
        SELECT 
            a.*, 
            p.lat, 
            p.lon, 
            p.alt_baro, 
            p.alt_geom, 
            p.gs, 
            p.track, 
            p.squawk, 
            p.timestamp
        FROM aircraft a
        LEFT JOIN (
            -- PostgreSQL specific syntax to get the most recent row per hex
            SELECT DISTINCT ON (hex) 
                hex, lat, lon, alt_baro, alt_geom, gs, track, squawk, timestamp
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
    """Fetches locally decoded aircraft (in-situ) data joined with their most recent position."""
    query = """
        SELECT 
            a.*, 
            p.lat, 
            p.lon, 
            p.alt_baro, 
            p.alt_geom, 
            p.gs, 
            p.track, 
            p.squawk, 
            p.timestamp
        FROM aircraft a
        LEFT JOIN (
            SELECT DISTINCT ON (hex) 
                hex, lat, lon, alt_baro, alt_geom, gs, track, squawk, timestamp
            FROM position
            ORDER BY hex, timestamp DESC
        ) p ON a.hex = p.hex
        WHERE a.filter = 'in-situ';
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
