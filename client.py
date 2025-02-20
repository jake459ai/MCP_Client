import asyncio
import json
import os
from typing import Optional, Union, Dict
from contextlib import AsyncExitStack
from pathlib import Path
import datetime

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()  # load environment variables from .env

class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic()
        self.config: Optional[Dict] = None
        self.conversation_history: list = []  # Store conversation history
        
        # Get current date and time
        current_datetime = datetime.datetime.now()
        formatted_date = current_datetime.strftime("%Y-%m-%d %H:%M:%S")
        
        # System prompt to guide Claude's behavior
        self.system_prompt = f"""You are a sophisticated AI assistant with access to MCP (Model Context Protocol) servers that provide you with powerful tools to help users.

The current date and time is: {formatted_date}

Key responsibilities:
1. Tool Usage:
   - Always carefully review tool descriptions and parameter requirements before making tool calls
   - Verify parameter types and formats match the tool's input schema
   - Use tools precisely and efficiently to accomplish user goals

2. Tool Education:
   - When asked about available tools, provide clear, detailed explanations of:
     * What each tool does
     * Required and optional parameters
     * Example usage scenarios
     * Any limitations or important considerations

3. Conversation Style:
   - Be professional yet approachable
   - Provide clear, structured responses
   - When using tools, explain what you're doing and why
   - If a tool call fails, explain why and suggest alternatives

4. Best Practices:
   - Maintain context across conversation turns
   - Build on previous tool results when relevant
   - Suggest optimal ways to use tools for complex tasks
   - Alert users to any required setup or prerequisites

Remember: You have real-time access to the tools' latest descriptions and schemas. Always check these before making tool calls to ensure accuracy and optimal usage.
NEVER ASSUME YOU KNOW THE DATE OR OTHER REAL TIME INFORMATION. ALWAYS USE THE PROVIDED CURRENT DATE: {formatted_date} AS YOUR REFERENCE POINT.
Also when users ask about a website, always assume they are referring to the website's name, not ID, unless they specifically give you the ID"""

    async def connect_to_server(self, path: str):
        """Connect to an MCP server

        Args:
            path: Either a path to a server script (.py or .js) or a path to a config file (.json)
        """
        if path.endswith('.json'):
            await self._connect_with_config(path)
        else:
            await self._connect_with_script(path)

    async def _connect_with_config(self, config_path: str):
        """Connect to a server using a config file

        Args:
            config_path: Path to the JSON config file
        """
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        if 'mcpServers' not in self.config:
            raise ValueError("Config file must contain 'mcpServers' object")

        # For now, we'll just use the first server in the config
        server_name, server_config = next(iter(self.config['mcpServers'].items()))
        
        # Get environment variables from config if they exist
        env_vars = server_config.get('env', {})
        
        # Try to find uv in common locations
        uv_paths = [
            '/usr/local/bin/uv',
            '/opt/homebrew/bin/uv',
            os.path.expanduser('~/.cargo/bin/uv'),
            'uv'  # fallback to PATH
        ]
        
        command = server_config['command']
        if command == 'uv':
            for uv_path in uv_paths:
                if os.path.exists(uv_path):
                    command = uv_path
                    break
            
        server_params = StdioServerParameters(
            command=command,
            args=server_config['args'],
            env={
                **os.environ,  # Include current environment variables
                **env_vars     # Override with config-specific variables
            }
        )

        print(f"\nStarting server with command: {command} {' '.join(server_config['args'])}")
        
        try:
            # Use the high-level SDK interface with proper context managers
            stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
            self.stdio, self.write = stdio_transport
            self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
            
            # Initialize the session
            await self.session.initialize()
            
            # List available tools
            tools_response = await self.session.list_tools()
            print(f"\nConnected to server '{server_name}' with tools:", [tool.name for tool in tools_response.tools])
            
            # Try to list available prompts
            try:
                prompts_result = await self.session.list_prompts()
                # Access the prompts attribute of the result
                prompts = prompts_result.prompts if hasattr(prompts_result, 'prompts') else []
                print(f"Available prompts: {[getattr(prompt, 'name', str(prompt)) for prompt in prompts]}")
            except Exception as e:
                print(f"Server does not support prompts: {str(e)}")
                
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Could not find the '{command}' executable. Please ensure uv is installed and in your PATH. Common install locations: {', '.join(uv_paths)}") from e
        except Exception as e:
            raise Exception(f"Failed to connect to server: {str(e)}") from e

    async def _connect_with_script(self, server_script_path: str):
        """Connect to a server using a direct script path

        Args:
            server_script_path: Path to the server script (.py or .js)
        """
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        # Use the high-level SDK interface with proper context managers
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        
        # Initialize the session
        await self.session.initialize()
        
        # List available tools
        tools_response = await self.session.list_tools()
        print("\nConnected to server with tools:", [tool.name for tool in tools_response.tools])
        
        # Try to list available prompts
        try:
            prompts_result = await self.session.list_prompts()
            # Access the prompts attribute of the result
            prompts = prompts_result.prompts if hasattr(prompts_result, 'prompts') else []
            print(f"Available prompts: {[getattr(prompt, 'name', str(prompt)) for prompt in prompts]}")
        except Exception as e:
            print(f"Server does not support prompts: {str(e)}")

    async def process_query(self, query: str) -> str:
        """Process a query using Claude and available tools"""
        MAX_RETRIES = 3
        RETRY_DELAY = 1  # seconds

        # Add user's query to conversation history
        self.conversation_history.append({
            "role": "user",
            "content": query
        })

        # Get available tools with retry
        for attempt in range(MAX_RETRIES):
            try:
                response = await self.session.list_tools()
                available_tools = [{
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema
                } for tool in response.tools]
                break
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    raise Exception(f"Failed to get tools after {MAX_RETRIES} attempts: {str(e)}")
                print(f"\nRetrying tool list retrieval (attempt {attempt + 2}/{MAX_RETRIES})...")
                await asyncio.sleep(RETRY_DELAY)

        final_text = []
        step_count = 1

        while True:
            try:
                # Get Claude's next action
                response = self.anthropic.messages.create(
                    model="claude-3-5-sonnet-latest",
                    max_tokens=2000,
                    messages=self.conversation_history,
                    tools=available_tools
                )
            except Exception as e:
                error_msg = f"Error calling Claude API: {str(e)}"
                self.conversation_history.append({
                    "role": "assistant",
                    "content": error_msg
                })
                return error_msg

            # Process the response
            assistant_message_content = []
            has_tool_calls = False

            for content in response.content:
                if content.type == 'text':
                    # Only add text if it's not just a transitional message
                    if not (content.text.strip().lower().startswith(("let me", "i'll", "i will", "now i'll", "next i'll"))):
                        final_text.append(content.text)
                    assistant_message_content.append({"type": "text", "text": content.text})
                elif content.type == 'tool_use':
                    has_tool_calls = True
                    tool_name = content.name
                    tool_args = content.input
                    
                    # Add a step marker for tool calls
                    final_text.append(f"\nStep {step_count}: Using {tool_name}")
                    step_count += 1

                    # Execute tool call with retry
                    for attempt in range(MAX_RETRIES):
                        try:
                            result = await self.session.call_tool(tool_name, tool_args)
                            break
                        except Exception as e:
                            if attempt == MAX_RETRIES - 1:
                                error_msg = f"Tool call failed after {MAX_RETRIES} attempts: {str(e)}"
                                final_text.append(f"  Error: {error_msg}")
                                result = type('ToolResult', (), {'content': error_msg})()
                            else:
                                print(f"\nRetrying tool call (attempt {attempt + 2}/{MAX_RETRIES})...")
                                await asyncio.sleep(RETRY_DELAY)

                    # Add tool call to message content
                    assistant_message_content.append(content)
                    
                    # Add assistant's tool use to conversation history
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": assistant_message_content
                    })

                    # Debug logging for tool result
                    print("\nDEBUG - Raw tool result:")
                    try:
                        # Handle TextContent objects by extracting their text
                        if hasattr(result.content, 'text'):
                            result_content = result.content.text
                        elif isinstance(result.content, list) and all(hasattr(item, 'text') for item in result.content):
                            result_content = "\n".join(item.text for item in result.content)
                        else:
                            result_content = str(result.content)
                        print(json.dumps(result_content, indent=2))
                    except Exception as e:
                        print(f"Debug logging failed: {str(e)}")
                    print("\nDEBUG - Tool result type:", type(result.content))
                    
                    # Add tool result to conversation history with proper text extraction
                    self.conversation_history.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": content.id,
                                "content": result_content  # Now just passing the string directly
                            }
                        ]
                    })

            # If no tool calls were made, we're done
            if not has_tool_calls:
                break

        # Add final assistant response to conversation history
        if not has_tool_calls:
            self.conversation_history.append({
                "role": "assistant",
                "content": response.content
            })

        # Format the final output
        formatted_output = []
        current_step = None
        
        for line in final_text:
            if line.startswith("\nStep "):
                current_step = line.strip()
                formatted_output.append(f"\n{current_step}")
            elif current_step:
                formatted_output.append(f"  {line}")
            else:
                formatted_output.append(line)

        return "\n".join(formatted_output)

    def save_conversation(self, filename: str):
        """Save the current conversation history to a file"""
        save_data = {
            'history': self.conversation_history,
            'timestamp': str(datetime.datetime.now())
        }
        with open(filename, 'w') as f:
            json.dump(save_data, f, indent=2)
        print(f"\nConversation saved to {filename}")

    def load_conversation(self, filename: str):
        """Load a conversation history from a file"""
        with open(filename, 'r') as f:
            save_data = json.load(f)
        self.conversation_history = save_data['history']
        print(f"\nLoaded conversation from {filename} (saved at {save_data['timestamp']})")

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Commands:")
        print("  quit - Exit the client")
        print("  clear - Start a new conversation")
        print("  save <filename> - Save conversation to file")
        print("  load <filename> - Load conversation from file")
        print("  help - Show available tools and commands")

        while True:
            try:
                query = input("\nQuery: ").strip()
                
                # Handle commands
                if query.lower() == 'quit':
                    break
                elif query.lower() == 'clear':
                    self.conversation_history = []
                    print("\nConversation history cleared. Starting new conversation.")
                    continue
                elif query.lower() == 'help':
                    response = await self.session.list_tools()
                    tools = response.tools
                    print("\nAvailable Tools:")
                    for tool in tools:
                        print(f"\n{tool.name}:")
                        print(f"  Description: {tool.description}")
                        print(f"  Parameters: {tool.inputSchema}")
                    print("\nCommands:")
                    print("  quit - Exit the client")
                    print("  clear - Start a new conversation")
                    print("  save <filename> - Save conversation to file")
                    print("  load <filename> - Load conversation from file")
                    print("  help - Show this help message")
                    continue
                elif query.lower().startswith('save '):
                    filename = query[5:].strip()
                    self.save_conversation(filename)
                    continue
                elif query.lower().startswith('load '):
                    filename = query[5:].strip()
                    self.load_conversation(filename)
                    continue

                response = await self.process_query(query)
                print("\n" + response)

            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()

async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script_or_config>")
        sys.exit(1)

    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys
    asyncio.run(main())
