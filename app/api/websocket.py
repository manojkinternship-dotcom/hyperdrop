from fastapi import WebSocket, WebSocketDisconnect
from typing import List, Dict, Any
import json
import logging

logger = logging.getLogger("hyperdrop.websocket")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Dashboard client connected. Active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Dashboard client disconnected. Active: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        if not self.active_connections:
            return
        data_str = json.dumps(message)
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(data_str)
            except Exception as e:
                logger.warning(f"Error sending to websocket client: {e}")
                dead_connections.append(connection)
        
        for dead in dead_connections:
            self.disconnect(dead)

ws_manager = ConnectionManager()
