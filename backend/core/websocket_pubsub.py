import asyncio
import json
import logging
from typing import Dict

from backend.core.cache import redis_cache
from backend.api.websocket import websocket_manager

logger = logging.getLogger(__name__)


class WebSocketPubSub:
    def __init__(self):
        self.pubsub = None
        self.running = False

    async def start(self):
        """Start the pub/sub listener"""
        self.pubsub = redis_cache.redis_client.pubsub()
        # Subscribe to job status channels
        await self.pubsub.subscribe("job_status_updates")
        
        self.running = True
        logger.info("WebSocket pub/sub listener started")
        
        try:
            while self.running:
                message = await self.pubsub.get_message(
                    ignore_subscribe_messages=True, 
                    timeout=1.0
                )
                if message:
                    await self.handle_message(message)
        except Exception as e:
            logger.error(f"Pub/sub listener error: {e}")
        finally:
            await self.pubsub.close()

    async def handle_message(self, message: dict):
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

    async def stop(self):
        """Stop the pub/sub listener"""
        self.running = False
        if self.pubsub:
            await self.pubsub.close()
        logger.info("WebSocket pub/sub listener stopped")

# Create singleton instance
websocket_pubsub = WebSocketPubSub()