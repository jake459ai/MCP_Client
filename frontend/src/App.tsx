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

interface Prompt {
  name: string
  description: string
  parameters: {
    [key: string]: {
      type: string
      description: string
      required?: boolean
      default?: any
    }
  }
}

interface PromptDetails extends Prompt {
  content: string
}

function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [tools, setTools] = useState<Tool[]>([])
  const [prompts, setPrompts] = useState<Prompt[]>([])
  const [selectedPrompt, setSelectedPrompt] = useState<PromptDetails | null>(null)
  const [promptParams, setPromptParams] = useState<Record<string, any>>({})
  const [isConnected, setIsConnected] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [connectionError, setConnectionError] = useState<string>('')
  const [showPromptModal, setShowPromptModal] = useState(false)
  const ws = useRef<WebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const reconnectTimeoutRef = useRef<number | undefined>(undefined)

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
            case 'initialization':
              console.log('Received initialization data:', data.data)
              setTools(data.data.tools)
              setPrompts(data.data.prompts)
              break
            case 'prompt':
              console.log('Received prompt details:', data.data)
              setSelectedPrompt(data.data)
              setShowPromptModal(true)
              setIsLoading(false)
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
          setIsLoading(false)
        }
      }
    } catch (error) {
      console.error('Error creating WebSocket:', error)
      setConnectionError('Failed to create WebSocket connection')
    }
  }

  const handlePromptSelect = async (promptName: string) => {
    if (!ws.current) {
      console.error('WebSocket not connected')
      return
    }
    
    console.log('Handling prompt selection for:', promptName)
    setIsLoading(true)
    
    try {
      ws.current.send(JSON.stringify({
        type: 'get_prompt',
        name: promptName
      }))
    } catch (error) {
      console.error('Error requesting prompt:', error)
      setConnectionError('Failed to request prompt')
      setIsLoading(false)
    }
  }

  const handlePromptSubmit = () => {
    if (!selectedPrompt || !ws.current) return

    try {
      // Create the query with the prompt name and parameters
      const query = {
        type: 'query',
        content: `Use prompt "${selectedPrompt.name}" with parameters: ${
          Object.entries(promptParams)
            .map(([key, value]) => `${key}: ${value}`)
            .join(', ')
        }`
      }

      console.log('Submitting prompt with query:', query)
      
      // Send the query
      ws.current.send(JSON.stringify(query))

      // Add the query to the messages
      setMessages(prev => [...prev, {
        role: 'user',
        content: query.content
      }])

      // Reset prompt state
      setSelectedPrompt(null)
      setPromptParams({})
      setShowPromptModal(false)
    } catch (error) {
      console.error('Error submitting prompt:', error)
      setConnectionError('Failed to submit prompt')
    }
  }

  // Add validation for prompt parameters
  const isPromptValid = () => {
    if (!selectedPrompt) return false
    
    // Check if all required parameters have values
    return Object.entries(selectedPrompt.parameters).every(([key, param]) => {
      if (param.required) {
        return promptParams[key] !== undefined && promptParams[key] !== ''
      }
      return true
    })
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

      <div className="main-content">
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

        <div className="sidebar">
          <div className="prompts-panel">
            <h2>Available Prompts</h2>
            {prompts.length > 0 ? (
              prompts.map((prompt) => (
                <div 
                  key={prompt.name} 
                  className="prompt" 
                  onClick={() => {
                    console.log('Prompt clicked:', prompt.name)
                    handlePromptSelect(prompt.name)
                  }}
                  role="button"
                  tabIndex={0}
                >
                  <h3>{prompt.name}</h3>
                  <p>{prompt.description}</p>
                </div>
              ))
            ) : (
              <div className="no-prompts-message">
                <p>No prompts available for this service.</p>
              </div>
            )}
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
      </div>

      {showPromptModal && selectedPrompt && (
        <div className="prompt-modal">
          <div className="prompt-modal-content">
            <h2>{selectedPrompt.name}</h2>
            <p>{selectedPrompt.description}</p>
            
            <form onSubmit={(e) => {
              e.preventDefault()
              handlePromptSubmit()
            }}>
              {Object.entries(selectedPrompt.parameters).map(([key, param]) => (
                <div key={key} className="prompt-parameter">
                  <label htmlFor={key}>
                    {param.description}
                    {param.required && <span className="required">*</span>}
                  </label>
                  <input
                    id={key}
                    type={param.type === 'number' ? 'number' : 'text'}
                    value={promptParams[key] || ''}
                    onChange={(e) => setPromptParams(prev => ({
                      ...prev,
                      [key]: e.target.value
                    }))}
                    required={param.required}
                    placeholder={param.default}
                  />
                </div>
              ))}
              
              <div className="prompt-modal-actions">
                <button 
                  type="button" 
                  onClick={() => {
                    setShowPromptModal(false)
                    setSelectedPrompt(null)
                    setPromptParams({})
                  }}
                >
                  Cancel
                </button>
                <button 
                  type="submit"
                  disabled={!isPromptValid()}
                >
                  Use Prompt
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default App 