import json
import logging
from typing import Any

from backend.core.cache import redis_cache
from backend.api.websocket import websocket_manager

logger = logging.getLogger(__name__)


class WebSocketPubSub:
    def __init__(self) -> None:
        self.pubsub: Any = None
        self.running = False

    async def start(self) -> None:
        """Start the pub/sub listener"""
        self.pubsub = redis_cache.redis_client.pubsub()
        pubsub = self.pubsub
        if pubsub is None:
            return
        # Subscribe to job status channels
        await pubsub.subscribe("job_status_updates")
        
        self.running = True
        logger.info("WebSocket pub/sub listener started")
        
        try:
            while self.running:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, 
                    timeout=1.0
                )
                if message:
                    await self.handle_message(message)
        except Exception as e:
            logger.error(f"Pub/sub listener error: {e}")
        finally:
            await pubsub.close()

    async def handle_message(self, message: dict[str, Any]) -> None:
        """Handle incoming pub/sub messages"""
        try:
            data = json.loads(message["data"])
            job_id = data.get("job_id")
            update_type = data.get("type")
            
            if job_id and update_type:
                # Broadcast to all WebSocket clients connected to this job
                await websocket_manager.broadcast_job_update(job_id, data)
                logger.debug(f"Broadcasted job update for {job_id}: {update_type}")
        except Exception as e:
            logger.error(f"Error handling pub/sub message: {e}")

    async def stop(self) -> None:
        """Stop the pub/sub listener"""
        self.running = False
        if self.pubsub:
            await self.pubsub.close()
        logger.info("WebSocket pub/sub listener stopped")

# Create singleton instance
websocket_pubsub = WebSocketPubSub()