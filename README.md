# AI-Moderated Chat System

A Python chat application with Gemini AI content moderation for child safety.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set your Gemini API key:
```bash
export GEMINI_API_KEY="your_gemini_api_key_here"
```

## Usage

1. Start the server:
```bash
python chat_server.py
```

2. Connect clients:
   - Console client: `python chat_client.py`
   - GUI client: `python chat_gui.py`

## Features

- Multi-user chat support
- Real-time AI content moderation using Gemini 2.5 Flash
- **Image upload with AI vision moderation**
- **Tkinter GUI client with image display**
- **Ban/disconnect status detection**
- Automatic IP banning for harmful content
- WebSocket-based real-time communication
- Child safety protection

## Security

The system automatically detects and bans users who send content related to:
- Child exploitation or abuse
- Inappropriate content involving minors
- Pedophilia
- Violence against children

Banned IPs are immediately disconnected and blocked from reconnecting.