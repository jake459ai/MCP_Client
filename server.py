from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState
import json
import asyncio
import logging
from client import MCPClient

# Configure logging with more detail
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Enable CORS with logging
origins = ["*"]  # In production, replace with your frontend URL
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active client sessions
clients = {}

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming {request.method} request to {request.url}")
    response = await call_next(request)
    logger.info(f"Returning response with status code {response.status_code}")
    return response

@app.get("/")
async def root():
    logger.info("Health check endpoint called")
    return {"message": "WebSocket server is running"}

@app.websocket("/ws")  # Simplified WebSocket endpoint
async def websocket_endpoint(websocket: WebSocket):
    client_id = str(id(websocket))  # Use the websocket object's id as the client identifier
    logger.info(f"New WebSocket connection request from client: {client_id}")
    logger.debug(f"Client headers: {websocket.headers}")
    
    try:
        await websocket.accept()
        logger.info(f"WebSocket connection accepted for client: {client_id}")
        
        try:
            # Initialize MCP client
            logger.debug(f"Initializing MCP client for {client_id}")
            mcp_client = MCPClient()
            await mcp_client.connect_to_server("claude_desktop_config.json")
            clients[client_id] = mcp_client
            logger.info(f"MCP client initialized for client: {client_id}")

            # Send initial tools list
            logger.debug(f"Fetching tools list for {client_id}")
            response = await mcp_client.session.list_tools()
            tools = [{
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema
            } for tool in response.tools]
            await websocket.send_json({
                "type": "tools",
                "data": tools
            })
            logger.info(f"Sent tools list to client: {client_id}")

            while True:
                try:
                    # Check if the connection is still alive
                    if websocket.client_state == WebSocketState.DISCONNECTED:
                        logger.warning(f"Client disconnected: {client_id}")
                        break

                    # Receive message from client
                    logger.debug(f"Waiting for message from {client_id}")
                    data = await websocket.receive_text()
                    message = json.loads(data)
                    logger.info(f"Received message from client {client_id}: {message['type']}")

                    if message["type"] == "query":
                        # Process query
                        logger.debug(f"Processing query from {client_id}: {message['content']}")
                        response = await mcp_client.process_query(message["content"])
                        await websocket.send_json({
                            "type": "response",
                            "data": response
                        })
                        logger.info(f"Sent query response to {client_id}")
                    elif message["type"] == "clear":
                        # Clear conversation history
                        logger.debug(f"Clearing conversation history for {client_id}")
                        mcp_client.conversation_history = []
                        await websocket.send_json({
                            "type": "cleared"
                        })
                        logger.info(f"Cleared conversation history for {client_id}")
                    elif message["type"] == "save":
                        # Save conversation
                        logger.debug(f"Saving conversation for {client_id} to {message['filename']}")
                        mcp_client.save_conversation(message["filename"])
                        await websocket.send_json({
                            "type": "saved",
                            "filename": message["filename"]
                        })
                        logger.info(f"Saved conversation for {client_id}")
                    elif message["type"] == "load":
                        # Load conversation
                        logger.debug(f"Loading conversation for {client_id} from {message['filename']}")
                        mcp_client.load_conversation(message["filename"])
                        await websocket.send_json({
                            "type": "loaded",
                            "filename": message["filename"]
                        })
                        logger.info(f"Loaded conversation for {client_id}")
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from client {client_id}: {str(e)}")
                    await websocket.send_json({
                        "type": "error",
                        "data": "Invalid message format"
                    })
                except WebSocketDisconnect:
                    logger.info(f"WebSocket disconnected for client: {client_id}")
                    break
                except Exception as e:
                    logger.error(f"Error processing message from {client_id}: {str(e)}", exc_info=True)
                    await websocket.send_json({
                        "type": "error",
                        "data": f"Error processing message: {str(e)}"
                    })

        except Exception as e:
            logger.error(f"Error initializing client {client_id}: {str(e)}", exc_info=True)
            await websocket.send_json({
                "type": "error",
                "data": f"Error initializing client: {str(e)}"
            })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected during setup for client: {client_id}")
    except Exception as e:
        logger.error(f"Error in WebSocket connection for client {client_id}: {str(e)}", exc_info=True)
        try:
            if websocket.client_state != WebSocketState.DISCONNECTED:
                await websocket.send_json({
                    "type": "error",
                    "data": str(e)
                })
        except:
            logger.error("Failed to send error message to client", exc_info=True)
    finally:
        if client_id in clients:
            try:
                await clients[client_id].cleanup()
                del clients[client_id]
                logger.info(f"Cleaned up client: {client_id}")
            except Exception as e:
                logger.error(f"Error cleaning up client {client_id}: {str(e)}", exc_info=True)

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting FastAPI server")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="debug",
        ws="wsproto"  # Explicitly use wsproto as the WebSocket backend
    ) 