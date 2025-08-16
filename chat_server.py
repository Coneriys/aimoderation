import asyncio
import websockets
import json
import logging
from datetime import datetime
import google.generativeai as genai
import os
from typing import Set, Dict, Any
import ipaddress

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatServer:
    def __init__(self):
        self.clients: Dict[websockets.WebSocketServerProtocol, Dict[str, Any]] = {}
        self.banned_ips: Set[str] = set()
        self.setup_gemini()
    
    def setup_gemini(self):
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
    
    async def moderate_content(self, message: str) -> bool:
        moderation_prompt = f"""
        Analyze this message for any content related to:
        - Child exploitation, abuse, or inappropriate content involving minors
        - Pedophilia or sexual content involving children
        - Child grooming behavior
        - Violence against children
        
        Respond with only "BAN" if any of these topics are present, otherwise respond with "SAFE".
        
        Message to analyze: "{message}"
        """
        
        try:
            response = self.model.generate_content(moderation_prompt)
            result = response.text.strip().upper()
            return result == "BAN"
        except Exception as e:
            logger.error(f"Moderation error: {e}")
            return True
    
    def get_client_ip(self, websocket):
        return websocket.remote_address[0]
    
    async def register_client(self, websocket, path):
        client_ip = self.get_client_ip(websocket)
        
        if client_ip in self.banned_ips:
            await websocket.close(code=1008, reason="IP banned")
            return
        
        self.clients[websocket] = {
            'ip': client_ip,
            'joined_at': datetime.now()
        }
        
        logger.info(f"Client connected from {client_ip}")
        await self.broadcast_message({
            'type': 'user_joined',
            'message': f'User from {client_ip} joined the chat',
            'timestamp': datetime.now().isoformat()
        }, exclude=websocket)
    
    async def unregister_client(self, websocket):
        if websocket in self.clients:
            client_info = self.clients[websocket]
            del self.clients[websocket]
            
            await self.broadcast_message({
                'type': 'user_left',
                'message': f'User from {client_info["ip"]} left the chat',
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info(f"Client {client_info['ip']} disconnected")
    
    async def ban_client(self, websocket, reason="Content violation"):
        if websocket in self.clients:
            client_ip = self.clients[websocket]['ip']
            self.banned_ips.add(client_ip)
            
            logger.warning(f"BANNED IP {client_ip}: {reason}")
            
            await websocket.close(code=1008, reason=f"Banned: {reason}")
            
            await self.broadcast_message({
                'type': 'user_banned',
                'message': f'User from {client_ip} was banned for policy violation',
                'timestamp': datetime.now().isoformat()
            })
    
    async def broadcast_message(self, message_data, exclude=None):
        if not self.clients:
            return
        
        message = json.dumps(message_data)
        disconnected_clients = []
        
        for client in self.clients:
            if client != exclude:
                try:
                    await client.send(message)
                except websockets.exceptions.ConnectionClosed:
                    disconnected_clients.append(client)
        
        for client in disconnected_clients:
            await self.unregister_client(client)
    
    async def handle_message(self, websocket, message_data):
        try:
            data = json.loads(message_data)
            message_content = data.get('message', '').strip()
            
            if not message_content:
                return
            
            client_ip = self.clients[websocket]['ip']
            
            should_ban = await self.moderate_content(message_content)
            
            if should_ban:
                logger.critical(f"HARMFUL CONTENT DETECTED from {client_ip}: {message_content}")
                await self.ban_client(websocket, "Harmful content detected")
                return
            
            broadcast_data = {
                'type': 'message',
                'sender_ip': client_ip,
                'message': message_content,
                'timestamp': datetime.now().isoformat()
            }
            
            await self.broadcast_message(broadcast_data)
            logger.info(f"Message from {client_ip}: {message_content}")
            
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def handle_client(self, websocket, path):
        await self.register_client(websocket, path)
        
        try:
            async for message in websocket:
                await self.handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"Error in client handler: {e}")
        finally:
            await self.unregister_client(websocket)

async def main():
    chat_server = ChatServer()
    
    logger.info("Starting chat server with AI moderation on localhost:8765")
    
    async with websockets.serve(chat_server.handle_client, "localhost", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())