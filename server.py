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

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    client_id = str(id(websocket))
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
            tools_response = await mcp_client.session.list_tools()
            tools = [{
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema
            } for tool in tools_response.tools]

            # Fetch available prompts
            logger.debug(f"Fetching prompts list for {client_id}")
            try:
                prompts_result = await mcp_client.session.list_prompts()
                logger.debug(f"Raw prompts result: {prompts_result}")
                
                prompts_list = []
                for prompt in prompts_result.prompts:
                    try:
                        # Get the name from the prompt
                        prompt_name = getattr(prompt, 'name', str(prompt))
                        logger.debug(f"Processing prompt: {prompt_name}")
                        
                        # Create basic prompt info for the list
                        prompt_dict = {
                            "name": prompt_name,
                            "description": getattr(prompt, 'description', ''),
                            "parameters": {}  # Parameters will be fetched when prompt is selected
                        }
                        prompts_list.append(prompt_dict)
                    except Exception as e:
                        logger.error(f"Error processing prompt {prompt}: {str(e)}")
                        continue
                        
                logger.info(f"Found {len(prompts_list)} prompts")
                logger.debug(f"Final prompts list: {prompts_list}")
            except Exception as e:
                logger.warning(f"Failed to fetch prompts: {str(e)}")
                prompts_list = []

            # Send initial data
            await websocket.send_json({
                "type": "initialization",
                "data": {
                    "tools": tools,
                    "prompts": prompts_list
                }
            })
            logger.info(f"Sent initialization data to client: {client_id}")

            while True:
                try:
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
                    elif message["type"] == "get_prompt":
                        # Get prompt details
                        prompt_name = message['name']
                        logger.debug(f"Fetching prompt {prompt_name} for {client_id}")
                        try:
                            # First get the prompt structure to get the parameters
                            prompts_result = await mcp_client.session.list_prompts()
                            selected_prompt = None
                            for prompt in prompts_result.prompts:
                                if getattr(prompt, 'name', str(prompt)) == prompt_name:
                                    selected_prompt = prompt
                                    break
                            
                            if not selected_prompt:
                                raise ValueError(f"Prompt {prompt_name} not found")
                            
                            # Extract parameters from the prompt arguments
                            parameters = {}
                            if hasattr(selected_prompt, 'arguments'):
                                for arg in selected_prompt.arguments:
                                    parameters[arg.name] = {
                                        "type": "string",
                                        "description": arg.description,
                                        "required": arg.required
                                    }
                            
                            # Create prompt details without trying to get content yet
                            prompt_details = {
                                "name": prompt_name,
                                "description": getattr(selected_prompt, 'description', ''),
                                "content": "Please provide the required parameters: " + 
                                         ", ".join(parameters.keys()),
                                "parameters": parameters
                            }
                            
                            logger.debug(f"Sending prompt details to frontend: {prompt_details}")
                            await websocket.send_json({
                                "type": "prompt",
                                "data": prompt_details
                            })
                            logger.info(f"Sent prompt details to {client_id}")
                        except Exception as e:
                            error_msg = f"Error fetching prompt: {str(e)}"
                            logger.error(error_msg, exc_info=True)
                            if websocket.client_state != WebSocketState.DISCONNECTED:
                                await websocket.send_json({
                                    "type": "error",
                                    "data": error_msg
                                })
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