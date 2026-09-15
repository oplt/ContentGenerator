from typing import Any
from fastapi import WebSocket

class WebSocketManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self.job_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, job_id: str) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        if job_id not in self.job_connections:
            self.job_connections[job_id] = []
        self.job_connections[job_id].append(websocket)

    def disconnect(self, websocket: WebSocket, job_id: str) -> None:
        self.active_connections.remove(websocket)
        if job_id in self.job_connections:
            self.job_connections[job_id].remove(websocket)
            if len(self.job_connections[job_id]) == 0:
                del self.job_connections[job_id]

    async def broadcast_job_update(self, job_id: str, update_data: dict[str, Any]) -> None:
        if job_id in self.job_connections:
            for connection in self.job_connections[job_id]:
                await connection.send_json(update_data)

    async def broadcast_all(self, update_data: dict[str, Any]) -> None:
        for connection in self.active_connections:
            await connection.send_json(update_data)

# Create singleton instance
websocket_manager = WebSocketManager()