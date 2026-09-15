from typing import List, Dict
from fastapi import WebSocket

class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.job_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, job_id: str):
        await websocket.accept()
        self.active_connections.append(websocket)
        if job_id not in self.job_connections:
            self.job_connections[job_id] = []
        self.job_connections[job_id].append(websocket)

    def disconnect(self, websocket: WebSocket, job_id: str):
        self.active_connections.remove(websocket)
        if job_id in self.job_connections:
            self.job_connections[job_id].remove(websocket)
            if len(self.job_connections[job_id]) == 0:
                del self.job_connections[job_id]

    async def broadcast_job_update(self, job_id: str, update_data: dict):
        if job_id in self.job_connections:
            for connection in self.job_connections[job_id]:
                await connection.send_json(update_data)

    async def broadcast_all(self, update_data: dict):
        for connection in self.active_connections:
            await connection.send_json(update_data)

# Create singleton instance
websocket_manager = WebSocketManager()