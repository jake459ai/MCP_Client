# MCP Client

## Overview

MCP Client is a desktop application that implements the Model Context Protocol (MCP) to enhance AI capabilities. The client connects to MCP servers that provide specialized tools and services, allowing AI assistants like Claude to access real-time data, perform complex operations, and interact with external systems.

This application consists of:
- A backend Python server (`server.py`) that manages WebSocket connections and bridges the frontend with MCP services
- A frontend UI (`frontend/`) built with React/TypeScript that provides a chat interface
- A client module (`client.py`) that implements the MCP protocol and communicates with external MCP servers

## Features

- Connect to various MCP servers through configuration files
- Chat with Claude AI with tool augmentation capabilities
- Support for various tools provided by MCP servers (analytics, search, etc.)
- Real-time sampling status updates
- Save and load conversation history

## Prerequisites

- Python 3.9+
- Node.js and npm
- [uv](https://github.com/astral-sh/uv) - Python package installer
- Anthropic API key

## Setup Instructions

### 1. Install Python Dependencies

```bash
uv venv
source .venv/bin/activate  # On Windows, use: .venv\Scripts\activate
uv install -e .
```

### 2. Set Up Frontend

```bash
cd frontend
npm install
```

### 3. Configure Claude Desktop

Create a `claude_desktop_config.json` file in the root directory with the following structure:

```json
{
  "mcpServers": {
    "server-name": {
      "command": "command-to-run-server",
      "args": [
        "arg1",
        "arg2",
        "..."
      ],
      "env": {
        "ENV_VAR1": "value1",
        "ENV_VAR2": "value2"
      }
    }
  }
}
```

Example for analytics server:
```json
{
  "mcpServers": {
    "analytics": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/analytics_service",
        "run",
        "analytics-service"
      ],
      "env": {
        "UMAMI_API_URL": "http://localhost:3000",
        "UMAMI_USERNAME": "your-username",
        "UMAMI_PASSWORD": "your-password",
        "UMAMI_TEAM_ID": "your-team-id"
      }
    }
  }
}
```

### 4. Set Environment Variables

Create a `.env` file in the root directory with your Anthropic API key:

```
ANTHROPIC_API_KEY=your-api-key-here
```

## Running the Application

### Start the Backend Server

```bash
uv run server.py
```

### Start the Frontend Development Server

```bash
cd frontend
npm run dev
```

The application should now be accessible at http://localhost:5173 (or the port specified by the frontend dev server).

## Available MCP Servers

The client currently supports the following MCP servers:

1. **Analytics Server** - Provides access to analytics data via Umami analytics platform
2. **Brave Search** - Enables web search capabilities via the Brave Search API

You can add additional MCP servers to your configuration as needed.

## Development

### Project Structure

- `client.py` - Core MCP client implementation
- `server.py` - FastAPI WebSocket server
- `frontend/` - React/TypeScript frontend application
- `claude_desktop_config.json` - Configuration for MCP servers (not in version control)
- `pyproject.toml` - Python package configuration

### Adding New MCP Servers

To add a new MCP server:

1. Add the server configuration to your `claude_desktop_config.json` file
2. Install any required dependencies for the new server
3. Restart the application

## Troubleshooting

- If you get errors connecting to MCP servers, ensure the server is running and accessible
- Verify that all required environment variables are set correctly
- Check that `uv` is installed and accessible in your PATH
- For WebSocket connection issues, check browser console for detailed error messages

## Security Note

The `claude_desktop_config.json` file contains sensitive information and should never be committed to version control. It has been added to the `.gitignore` file to prevent accidental commits.