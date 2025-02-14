import { useState, useEffect, useRef } from 'react'
import './App.css'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface Tool {
  name: string
  description: string
  inputSchema: any
}

function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [tools, setTools] = useState<Tool[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [connectionError, setConnectionError] = useState<string>('')
  const ws = useRef<WebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const reconnectTimeoutRef = useRef<number>()

  // Connect to WebSocket
  const connectWebSocket = () => {
    try {
      console.log('Attempting to connect to WebSocket server')
      
      ws.current = new WebSocket('ws://localhost:8000/ws')

      ws.current.onopen = () => {
        setIsConnected(true)
        setConnectionError('')
        console.log('Connected to server successfully')
      }

      ws.current.onclose = (event) => {
        console.log('WebSocket closed:', event)
        setIsConnected(false)
        setConnectionError('Connection lost. Attempting to reconnect...')
        
        // Attempt to reconnect after 3 seconds
        reconnectTimeoutRef.current = window.setTimeout(() => {
          console.log('Attempting to reconnect...')
          connectWebSocket()
        }, 3000)
      }

      ws.current.onerror = (error) => {
        console.error('WebSocket error:', error)
        setConnectionError('Connection error occurred')
      }

      ws.current.onmessage = (event) => {
        console.log('Received message:', event.data)
        try {
          const data = JSON.parse(event.data)
          
          switch (data.type) {
            case 'tools':
              console.log('Received tools:', data.data)
              setTools(data.data)
              break
            case 'response':
              console.log('Received response:', data.data)
              setMessages(prev => [...prev, { role: 'assistant', content: data.data }])
              setIsLoading(false)
              break
            case 'error':
              console.error('Received error:', data.data)
              setConnectionError(data.data)
              setIsLoading(false)
              break
            default:
              console.warn('Unknown message type:', data.type)
          }
        } catch (error) {
          console.error('Error parsing message:', error)
          setConnectionError('Error processing server message')
        }
      }
    } catch (error) {
      console.error('Error creating WebSocket:', error)
      setConnectionError('Failed to create WebSocket connection')
    }
  }

  // Initialize WebSocket connection
  useEffect(() => {
    console.log('Initializing WebSocket connection')
    connectWebSocket()

    return () => {
      console.log('Cleaning up WebSocket connection')
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (ws.current) {
        ws.current.close()
      }
    }
  }, [])

  // Auto scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || !ws.current) return

    console.log('Sending message:', input)
    
    // Add user message
    setMessages(prev => [...prev, { role: 'user', content: input }])
    setIsLoading(true)

    try {
      // Send to server
      ws.current.send(JSON.stringify({
        type: 'query',
        content: input
      }))
    } catch (error) {
      console.error('Error sending message:', error)
      setConnectionError('Failed to send message')
      setIsLoading(false)
    }

    setInput('')
  }

  const handleClear = () => {
    if (!ws.current) return
    ws.current.send(JSON.stringify({ type: 'clear' }))
    setMessages([])
  }

  return (
    <div className="app-container">
      <header>
        <h1>MCP Chat</h1>
        <div className="status">
          {isConnected ? (
            <span className="connected">Connected</span>
          ) : (
            <span className="disconnected">
              Disconnected
              {connectionError && <p className="error-message">{connectionError}</p>}
            </span>
          )}
        </div>
      </header>

      <div className="chat-container">
        <div className="messages">
          {messages.map((msg, idx) => (
            <div key={idx} className={`message ${msg.role}`}>
              <div className="message-content">
                {msg.role === 'assistant' ? (
                  <pre>{msg.content}</pre>
                ) : (
                  <p>{msg.content}</p>
                )}
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="message assistant">
              <div className="message-content">
                <div className="loading">Thinking...</div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <form onSubmit={handleSubmit} className="input-form">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your message..."
            disabled={!isConnected || isLoading}
          />
          <button type="submit" disabled={!isConnected || isLoading}>
            Send
          </button>
          <button type="button" onClick={handleClear} disabled={!isConnected || isLoading}>
            Clear Chat
          </button>
        </form>
      </div>

      <div className="tools-panel">
        <h2>Available Tools</h2>
        {tools.map((tool) => (
          <div key={tool.name} className="tool">
            <h3>{tool.name}</h3>
            <p>{tool.description}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

export default App 