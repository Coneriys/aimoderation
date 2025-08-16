import asyncio
import websockets
import json
import logging
from datetime import datetime
import google.generativeai as genai
import os
from typing import Set, Dict, Any
import ipaddress
import base64
from PIL import Image
import io
import argparse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatServer:
    def __init__(self, verbose=False):
        self.clients: Dict[websockets.WebSocketServerProtocol, Dict[str, Any]] = {}
        self.banned_ips: Set[str] = set()
        self.user_contexts: Dict[str, list] = {}
        self.verbose = verbose
        self.setup_gemini()
    
    def setup_gemini(self):
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
    
    async def moderate_content(self, message: str, user_ip: str) -> bool:
        if user_ip not in self.user_contexts:
            self.user_contexts[user_ip] = []
        
        self.user_contexts[user_ip].append(message)
        
        if len(self.user_contexts[user_ip]) > 10:
            self.user_contexts[user_ip] = self.user_contexts[user_ip][-10:]
        
        context_messages = "\n".join(self.user_contexts[user_ip])
        
        moderation_prompt = f"""
        Analyze this conversation for content that could harm minors.

        Current message: "{message}"
        Full conversation: {context_messages}

        DECODING INSTRUCTIONS:
        Try Caesar cipher with ALL shifts (1-25), not just ROT13:
        - Shift 1: A→B, B→C, etc.  
        - Shift 7: A→H, B→I, etc.
        - Shift 13: A→N, B→O, etc. (ROT13)
        - Continue through all 25 shifts

        LOOK FOR after decoding:
        - Age gaps: minor (under 18) + adult 
        - Phrases like "love young", "prefer minors", age preferences
        - Grooming language
        - Explicit content involving children

        CRITICAL: If ANY Caesar shift reveals harmful content about minors, respond "BAN".

        Examples that should be BAN:
        - Two ages found: 14 and 45 
        - "I love girls younger than 14"
        - Any preference for minors

        Respond only: BAN or SAFE"""
        
        try:
            if self.verbose:
                logger.info(f"Sending to AI: {message}")
                logger.info(f"Full context sent: {context_messages}")
            
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH", 
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE"
                }
            ]
            
            response = self.model.generate_content(
                moderation_prompt,
                safety_settings=safety_settings
            )
            result = response.text.strip().upper()
            
            if self.verbose:
                logger.info(f"AI Response: {result}")
            
            return "BAN" in result
        except Exception as e:
            logger.error(f"Moderation error: {e}")
            return True
    
    async def moderate_image(self, image_data: bytes) -> bool:
        moderation_prompt = """
        Analyze this image for any content related to:
        - Child exploitation, abuse, or inappropriate content involving minors
        - Nudity or sexual content involving children
        - Child grooming behavior
        - Violence against children
        - Any harmful content targeting minors
        - MAP pride flags or symbols
        - Inappropriate symbols related to minors
        
        Respond with only "BAN" if any of these are present, otherwise respond with "SAFE".
        """
        
        try:
            image = Image.open(io.BytesIO(image_data))
            
            if self.verbose:
                logger.info("Sending image to AI for analysis")
            
            response = self.model.generate_content([moderation_prompt, image])
            result = response.text.strip().upper()
            
            if self.verbose:
                logger.info(f"AI Image Response: {result}")
            
            return "BAN" in result
        except Exception as e:
            logger.error(f"Image moderation error: {e}")
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
            client_ip = self.clients[websocket]['ip']
            
            if 'message' in data:
                message_content = data.get('message', '').strip()
                
                if not message_content:
                    return
                
                should_ban = await self.moderate_content(message_content, client_ip)
                
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
            
            elif 'image' in data:
                image_b64 = data.get('image')
                image_name = data.get('image_name', 'image.png')
                
                try:
                    should_ban_name = await self.moderate_content(image_name, client_ip)
                    if should_ban_name:
                        logger.critical(f"HARMFUL IMAGE NAME DETECTED from {client_ip}: {image_name}")
                        await self.ban_client(websocket, "Harmful image name detected")
                        return
                    
                    image_data = base64.b64decode(image_b64)
                    
                    should_ban = await self.moderate_image(image_data)
                    
                    if should_ban:
                        logger.critical(f"HARMFUL IMAGE DETECTED from {client_ip}")
                        await self.ban_client(websocket, "Harmful image detected")
                        return
                    
                    broadcast_data = {
                        'type': 'image',
                        'sender_ip': client_ip,
                        'image': image_b64,
                        'image_name': image_name,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    await self.broadcast_message(broadcast_data)
                    logger.info(f"Image from {client_ip}: {image_name}")
                    
                except Exception as e:
                    logger.error(f"Error processing image: {e}")
            
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
    parser = argparse.ArgumentParser(description='AI Moderated Chat Server')
    parser.add_argument('-v', '--verbose', action='store_true', 
                       help='Enable verbose logging of AI responses')
    args = parser.parse_args()
    
    chat_server = ChatServer(verbose=args.verbose)
    
    if args.verbose:
        logger.info("Verbose mode enabled - AI responses will be logged")
    
    logger.info("Starting chat server with AI moderation on localhost:8765")
    
    async with websockets.serve(chat_server.handle_client, "localhost", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())