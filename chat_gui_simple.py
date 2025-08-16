import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import asyncio
import websockets
import json
import threading
from datetime import datetime
import base64

class ChatGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AI Moderated Chat")
        self.root.geometry("800x600")
        self.root.configure(bg='#2b2b2b')
        
        self.websocket = None
        self.running = False
        self.connection_status = "Disconnected"
        self.ban_reason = None
        
        self.setup_ui()
        self.loop = None
        
    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TLabel', background='#2b2b2b', foreground='white')
        style.configure('TButton', background='#404040', foreground='white')
        style.configure('TFrame', background='#2b2b2b')
        
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.status_label = ttk.Label(main_frame, text="Status: Disconnected", font=('Arial', 10))
        self.status_label.pack(anchor='w', pady=(0, 5))
        
        self.chat_display = scrolledtext.ScrolledText(
            main_frame, 
            height=20, 
            width=80,
            bg='#1e1e1e',
            fg='white',
            insertbackground='white',
            state=tk.DISABLED,
            font=('Consolas', 10)
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.message_entry = tk.Entry(
            input_frame,
            bg='#404040',
            fg='white',
            insertbackground='white',
            font=('Arial', 11)
        )
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.message_entry.bind('<Return>', self.send_message)
        
        self.send_button = ttk.Button(input_frame, text="Send", command=self.send_message)
        self.send_button.pack(side=tk.RIGHT)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        self.connect_button = ttk.Button(button_frame, text="Connect", command=self.toggle_connection)
        self.connect_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.image_button = ttk.Button(button_frame, text="Send Image", command=self.send_image)
        self.image_button.pack(side=tk.LEFT, padx=(0, 5))
        self.image_button.config(state='disabled')
        
        self.clear_button = ttk.Button(button_frame, text="Clear Chat", command=self.clear_chat)
        self.clear_button.pack(side=tk.RIGHT)
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def add_message(self, message, color='white'):
        self.chat_display.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.chat_display.insert(tk.END, f"[{timestamp}] {message}\n")
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)
    
    def add_image_message(self, sender_ip, image_name, timestamp):
        self.chat_display.config(state=tk.NORMAL)
        ts = datetime.fromisoformat(timestamp).strftime('%H:%M:%S')
        self.chat_display.insert(tk.END, f"[{ts}] {sender_ip} sent image: {image_name}\n")
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)
    
    def update_status(self, status, reason=None):
        self.connection_status = status
        self.ban_reason = reason
        
        if status == "Connected":
            status_text = "Status: Connected ✓"
            self.status_label.configure(foreground='green')
        elif status == "Banned":
            status_text = f"Status: BANNED - {reason}" if reason else "Status: BANNED"
            self.status_label.configure(foreground='red')
        elif status == "Connecting":
            status_text = "Status: Connecting..."
            self.status_label.configure(foreground='yellow')
        else:
            status_text = "Status: Disconnected"
            self.status_label.configure(foreground='gray')
        
        self.status_label.config(text=status_text)
    
    def toggle_connection(self):
        if not self.running:
            self.start_connection()
        else:
            self.stop_connection()
    
    def start_connection(self):
        self.update_status("Connecting")
        self.connect_button.config(text="Disconnect")
        
        def run_async():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.connect_to_server())
        
        self.thread = threading.Thread(target=run_async, daemon=True)
        self.thread.start()
    
    def stop_connection(self):
        self.running = False
        if self.websocket:
            asyncio.run_coroutine_threadsafe(self.websocket.close(), self.loop)
        self.update_status("Disconnected")
        self.connect_button.config(text="Connect")
        self.image_button.config(state='disabled')
    
    async def connect_to_server(self):
        try:
            self.websocket = await websockets.connect("ws://localhost:8765")
            self.running = True
            self.update_status("Connected")
            
            self.root.after(0, lambda: self.image_button.config(state='normal'))
            self.root.after(0, lambda: self.add_message("Connected to chat server!", 'green'))
            
            async for message in self.websocket:
                if not self.running:
                    break
                
                try:
                    data = json.loads(message)
                    self.root.after(0, lambda d=data: self.handle_server_message(d))
                except json.JSONDecodeError:
                    pass
                    
        except websockets.exceptions.ConnectionRefused:
            self.root.after(0, lambda: self.add_message("Error: Could not connect to server", 'red'))
            self.root.after(0, lambda: self.update_status("Disconnected"))
            self.root.after(0, lambda: self.connect_button.config(text="Connect"))
        except websockets.exceptions.ConnectionClosed as e:
            if e.code == 1008:
                self.root.after(0, lambda: self.update_status("Banned", e.reason))
                self.root.after(0, lambda: self.add_message(f"YOU HAVE BEEN BANNED: {e.reason}", 'red'))
            else:
                self.root.after(0, lambda: self.update_status("Disconnected"))
                self.root.after(0, lambda: self.add_message("Connection lost", 'yellow'))
            
            self.root.after(0, lambda: self.connect_button.config(text="Connect"))
            self.root.after(0, lambda: self.image_button.config(state='disabled'))
            self.running = False
        except Exception as e:
            self.root.after(0, lambda: self.add_message(f"Connection error: {e}", 'red'))
            self.root.after(0, lambda: self.update_status("Disconnected"))
            self.root.after(0, lambda: self.connect_button.config(text="Connect"))
            self.running = False
    
    def handle_server_message(self, data):
        msg_type = data.get('type')
        timestamp = datetime.fromisoformat(data.get('timestamp', '')).strftime('%H:%M:%S')
        
        if msg_type == 'message':
            sender_ip = data.get('sender_ip', 'Unknown')
            message = data.get('message', '')
            self.add_message(f"{sender_ip}: {message}")
        
        elif msg_type == 'image':
            sender_ip = data.get('sender_ip', 'Unknown')
            image_name = data.get('image_name', 'image.png')
            timestamp = data.get('timestamp', '')
            self.add_image_message(sender_ip, image_name, timestamp)
        
        elif msg_type == 'user_joined':
            self.add_message(data.get('message', ''), 'green')
        
        elif msg_type == 'user_left':
            self.add_message(data.get('message', ''), 'yellow')
        
        elif msg_type == 'user_banned':
            self.add_message(f"⚠️  {data.get('message', '')}", 'red')
    
    def send_message(self, event=None):
        if not self.running or not self.websocket:
            return
        
        message = self.message_entry.get().strip()
        if not message:
            return
        
        self.message_entry.delete(0, tk.END)
        
        message_data = {'message': message}
        
        asyncio.run_coroutine_threadsafe(
            self.websocket.send(json.dumps(message_data)),
            self.loop
        )
    
    def send_image(self):
        if not self.running or not self.websocket:
            return
        
        file_path = filedialog.askopenfilename(
            title="Select Image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp"),
                ("All files", "*.*")
            ]
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'rb') as f:
                image_data = f.read()
            
            if len(image_data) > 5 * 1024 * 1024:
                messagebox.showerror("Error", "Image too large (max 5MB)")
                return
            
            image_b64 = base64.b64encode(image_data).decode('utf-8')
            image_name = file_path.split('/')[-1]
            
            message_data = {
                'image': image_b64,
                'image_name': image_name
            }
            
            asyncio.run_coroutine_threadsafe(
                self.websocket.send(json.dumps(message_data)),
                self.loop
            )
            
            self.add_message(f"Sending image: {image_name}", 'cyan')
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send image: {e}")
    
    def clear_chat(self):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.delete(1.0, tk.END)
        self.chat_display.config(state=tk.DISABLED)
    
    def on_closing(self):
        if self.running:
            self.stop_connection()
        self.root.destroy()
    
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = ChatGUI()
    app.run()