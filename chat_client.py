import asyncio
import websockets
import json
import threading
from datetime import datetime

class ChatClient:
    def __init__(self, uri="ws://localhost:8765"):
        self.uri = uri
        self.websocket = None
        self.running = False
    
    async def connect(self):
        try:
            self.websocket = await websockets.connect(self.uri)
            self.running = True
            print("Connected to chat server!")
            print("Type your messages and press Enter. Type 'quit' to exit.")
            print("-" * 50)
            
            receive_task = asyncio.create_task(self.receive_messages())
            send_task = asyncio.create_task(self.send_messages())
            
            await asyncio.gather(receive_task, send_task)
            
        except websockets.exceptions.ConnectionRefused:
            print("Error: Could not connect to chat server. Make sure the server is running.")
        except Exception as e:
            print(f"Connection error: {e}")
    
    async def receive_messages(self):
        try:
            async for message in self.websocket:
                data = json.loads(message)
                self.display_message(data)
        except websockets.exceptions.ConnectionClosed:
            print("\nConnection to server lost.")
            self.running = False
        except Exception as e:
            print(f"Error receiving messages: {e}")
            self.running = False
    
    def display_message(self, data):
        msg_type = data.get('type')
        timestamp = datetime.fromisoformat(data.get('timestamp', '')).strftime('%H:%M:%S')
        
        if msg_type == 'message':
            sender_ip = data.get('sender_ip', 'Unknown')
            message = data.get('message', '')
            print(f"[{timestamp}] {sender_ip}: {message}")
        
        elif msg_type == 'user_joined':
            print(f"[{timestamp}] {data.get('message', '')}")
        
        elif msg_type == 'user_left':
            print(f"[{timestamp}] {data.get('message', '')}")
        
        elif msg_type == 'user_banned':
            print(f"[{timestamp}] ⚠️  {data.get('message', '')}")
    
    async def send_messages(self):
        while self.running:
            try:
                message = await asyncio.get_event_loop().run_in_executor(
                    None, input, ""
                )
                
                if message.lower() == 'quit':
                    self.running = False
                    break
                
                if message.strip():
                    message_data = {
                        'message': message
                    }
                    await self.websocket.send(json.dumps(message_data))
                    
            except (EOFError, KeyboardInterrupt):
                self.running = False
                break
            except websockets.exceptions.ConnectionClosed:
                print("\nConnection closed by server.")
                self.running = False
                break
            except Exception as e:
                print(f"Error sending message: {e}")
                break
    
    async def disconnect(self):
        if self.websocket:
            await self.websocket.close()

async def main():
    client = ChatClient()
    
    try:
        await client.connect()
    except KeyboardInterrupt:
        print("\nDisconnecting...")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    print("Chat Client")
    print("=" * 20)
    asyncio.run(main())