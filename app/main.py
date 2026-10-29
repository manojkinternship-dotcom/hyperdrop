from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.api.routes import router as api_router
from app.api.websocket import ws_manager

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables created
    init_db()
    yield
    # Shutdown

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="HyperDrop: AI Voice Agent for Last-Mile Delivery Exceptions",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(api_router)

# Mount Dashboard static assets if directory exists
if DASHBOARD_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR)), name="static")

@app.get("/", include_in_schema=False)
async def serve_dashboard():
    index_file = DASHBOARD_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "HyperDrop API is running. Dashboard not found."}

@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, listen for any client messages/pings
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
