import asyncio
import websockets
import json
import uuid
import os
from pprint import pprint
from dotenv import load_dotenv

'''Connecting through websockets to the Generative Engine API for streaming responses.'''

# Load environment variables
load_dotenv()

class WebSocketClient:
    def __init__(self, api_key, workspace_id=None):
        self.api_key = api_key
        self.workspace_id = workspace_id
        self.websocket = None
        self.running = False
        self.uri = "wss://ws.generative.engine.capgemini.com/"
        self.full_response = ""  # Store complete response for pprint

    async def connect(self):
        try:
            # For websockets v16.x (your version), use additional_headers
            headers = [("x-api-key", self.api_key)]
            
            self.websocket = await websockets.connect(
                self.uri,
                additional_headers=headers
            )
            self.running = True
            print("WebSocket connection opened\n")
            await self.handle_messages()
        except Exception as e:
            print(f"Connection error: {type(e).__name__}: {e}")

    async def handle_messages(self):
        try:
            while self.running:
                try:
                    message = await self.websocket.recv()
                    parsed_message = json.loads(message)
                    
                    # Handle streaming tokens
                    if parsed_message.get('action') == 'llm_new_token':
                        token = parsed_message['data']['token']['value']
                        self.full_response += token
                        print(token, end='', flush=True)
                    
                    # Handle final response
                    elif parsed_message.get('action') == 'final_response':
                        if 'data' in parsed_message and 'content' in parsed_message['data']:
                            self.full_response = parsed_message['data']['content']
                            print("\n\n=== Complete Response ===")
                            pprint(self.full_response)
                            
                            print("\n=== Response Metadata ===")
                            pprint(parsed_message['data'].get('metadata', {}))
                            
                except asyncio.TimeoutError:
                    pass
        except websockets.exceptions.ConnectionClosed:
            print("\nConnection closed")
        finally:
            self.running = False

    async def send_message(self, message, model_name="amazon.nova-lite-v1:0", 
                          max_tokens=512, temperature=0.6, top_p=0.9):
        if self.websocket and self.running:
            try:
                # Prepare the payload
                payload = {
                    "action": "run",
                    "modelInterface": "multimodal",
                    "adapterInterfaceVersion": "v2",
                    "data": {
                        "mode": "chain",
                        "text": message,
                        "modelName": model_name,
                        "provider": "bedrock",
                        "sessionId": str(uuid.uuid4()),
                        "workspaceId": self.workspace_id,
                        "files": [],
                        "modelKwargs": {
                            "maxTokens": max_tokens,
                            "temperature": temperature,
                            "streaming": True,
                            "topP": top_p
                        }
                    }
                }
                
                await self.websocket.send(json.dumps(payload))
                print(f"Query sent: {message}\n")
                print("=== Streaming Response ===")
            except Exception as e:
                print(f"Send error: {e}")
        else:
            print("WebSocket not connected")

    async def close(self):
        if self.websocket and self.running:
            self.running = False
            await self.websocket.close()
            print("\nWebSocket connection closed")

async def main():
    # Load API key from environment
    API_KEY = os.getenv("LLM_API_KEY")
    WORKSPACE_ID = None  # Optional - add if you have one
    
    if not API_KEY:
        print("Error: LLM_API_KEY not found in .env file")
        return
    
    client = WebSocketClient(API_KEY, WORKSPACE_ID)
    
    try:
        # Start connection in background
        connection_task = asyncio.create_task(client.connect())
        
        # Wait for connection to establish
        await asyncio.sleep(2)
        
        # Send a message
        await client.send_message("Explain the core Data Engineering concepts in simple terms.")
        
        # Wait for responses (adjust time as needed)
        await asyncio.sleep(15)
        
        # Close connection
        await client.close()
        
        # Wait for connection task to complete
        await connection_task
        
    except Exception as e:
        print(f"Error: {e}")

# For running in a standard Python file
if __name__ == "__main__":
    asyncio.run(main())

# For Jupyter notebook, use:
# await main()