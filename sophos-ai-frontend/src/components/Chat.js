import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import UserProfile from './UserProfile';

const API_BASE_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

// Toast notification component
function Toast({ message, type, onClose }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 5000);
    return () => clearTimeout(timer);
  }, [onClose]);

  const bgColors = {
    error: 'linear-gradient(135deg, #ff8a80 0%, #ff5252 100%)',
    warning: 'linear-gradient(135deg, #ffb74d 0%, #ff9800 100%)',
    info: 'linear-gradient(135deg, #89b3f8 0%, #a789f8 100%)',
    success: 'linear-gradient(135deg, #81c784 0%, #66bb6a 100%)'
  };

  return (
    <div className="toast-container">
      <div 
        className="toast toast-enter"
        style={{ background: bgColors[type] || bgColors.info }}
      >
        <span className="toast-message">{message}</span>
        <button className="toast-close" onClick={onClose}>×</button>
      </div>
    </div>
  );
}

export default function Chat({ user, chatSession, onMessagesUpdate, onLogout }) {
  const [messages, setMessages] = useState(chatSession.messages);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isRetrieving, setIsRetrieving] = useState(false);
  const [tick, setTick] = useState(0);
  const [reportState, setReportState] = useState({});
  const [toasts, setToasts] = useState([]);
  const messagesEndRef = useRef(null);

  const addToast = (message, type = 'info') => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message, type }]);
  };

  const removeToast = (id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  useEffect(() => {
    onMessagesUpdate(messages, chatSession.id);
  }, [messages, onMessagesUpdate, chatSession.id]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };
  useEffect(scrollToBottom, [messages, isLoading]);

  useEffect(scrollToBottom, [messages, isLoading]);

  // Re-render while loading to update the timer text
  useEffect(() => {
    if (!isLoading) return;
    const id = setInterval(() => setTick(t => t + 1), 200);
    return () => clearInterval(id);
  }, [isLoading]);

  // Split visible text from <think> blocks
  const splitThink = (text = "") => {
    const matches = [...text.matchAll(/<think>([\s\S]*?)<\/think>/g)];
    const think = matches.map(m => (m[1] || "").trim()).join("\n\n").trim();
    const visible = text.replace(/<think>[\s\S]*?<\/think>/g, '').trim();
    return { visible, think };
  };

  const sendMessage = (messageContent) => {
    if (!messageContent.trim()) return;

    const userMessage = { role: 'user', content: messageContent, timestamp: Date.now() };
    setMessages(prev => [...prev, userMessage]);
    setIsRetrieving(true);
    setIsLoading(true);

    // Placeholder for streaming assistant response
    const assistantMessagePlaceholder = { 
      role: 'assistant', 
      content: '', 
      sources: [], 
      _startedAt: Date.now(),
      _retrievalStarted: Date.now()
    };
    setMessages(prev => [...prev, assistantMessagePlaceholder]);

    const es = new EventSource(`${API_BASE_URL}/query?question=${encodeURIComponent(messageContent)}`);

    es.addEventListener('sources', (e) => {
      setIsRetrieving(false);
      try {
        const data = JSON.parse(e.data);
        setMessages(prev => prev.map((msg, index) =>
          index === prev.length - 1 ? { 
            ...msg, 
            sources: data.sources || [],
            confidenceScore: data.confidence_score,
            retrievalTimeMs: data.retrieval_time_ms,
            numSources: data.num_sources
          } : msg
        ));
      } catch (err) {
        console.error('Error parsing sources:', err);
        addToast('Failed to load sources', 'error');
      }
    });

    es.addEventListener('token', (e) => {
      const tokenData = JSON.parse(e.data);
      setMessages(prev => prev.map((msg, index) =>
        index === prev.length - 1 ? { ...msg, content: msg.content + tokenData.token } : msg
      ));
    });

    es.addEventListener('end', (e) => {
      setIsLoading(false);
      try {
        const data = JSON.parse(e.data);
        setMessages(prev => prev.map((msg, index) => {
          if (index !== prev.length - 1) return msg;
          const thoughtMs = msg._startedAt ? Date.now() - msg._startedAt : undefined;
          const { _startedAt, _retrievalStarted, ...rest } = msg;
          return { 
            ...rest, 
            thoughtMs,
            totalTimeMs: data.total_time_ms,
            thoughtTimeMs: data.thought_time_ms
          };
        }));
      } catch (err) {
        console.error('Error parsing end event:', err);
        setMessages(prev => prev.map((msg, index) => {
          if (index !== prev.length - 1) return msg;
          const thoughtMs = msg._startedAt ? Date.now() - msg._startedAt : undefined;
          const { _startedAt, _retrievalStarted, ...rest } = msg;
          return { ...rest, thoughtMs };
        }));
      }
      es.close();
    });

    es.onerror = () => {
      addToast('Connection lost. Please try again.', 'error');
      setMessages(prev => prev.map((msg, index) =>
        index === prev.length - 1 ? { 
          ...msg, 
          content: 'Sorry, an error occurred while streaming. Please try again.',
          error: true 
        } : msg
      ));
      setIsLoading(false);
      setIsRetrieving(false);
      es.close();
    };
  };

  const handleFormSubmit = (e) => {
    e.preventDefault();
    sendMessage(input);
    setInput('');
  };

  const handleCardClick = (prompt) => {
    setInput(prompt);
    sendMessage(prompt);
    setInput('');
  };

  const isWelcomeScreen = messages.length === 1;

  // compute live elapsed for the in-progress assistant message
  const lastMsg = messages[messages.length - 1];
  const liveElapsedMs = (isLoading && lastMsg && lastMsg._startedAt)
    ? Math.max(0, Date.now() - lastMsg._startedAt + tick * 0)
    : 0;

  // ---- Reporting ----
  const handleReport = async (msg, index) => {
    const state = reportState[index];
    if (state === 'sending' || state === 'done') return;

    setReportState(prev => ({ ...prev, [index]: 'sending' }));
    try {
      const payload = {
        message: msg.content,
        role: msg.role,
        index,
        chatId: chatSession.id,
        user: (typeof user?.username === 'string' && user.username.trim()) ? user.username.trim() : 'anonymous',
        sources: msg.sources || null,
        thoughtMs: msg.thoughtMs ?? null,
      };

      const res = await fetch(`${API_BASE_URL}/report-incorrect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw new Error('Failed to report');
      setReportState(prev => ({ ...prev, [index]: 'done' }));
    } catch (err) {
      console.error('Report failed:', err);
      setReportState(prev => ({ ...prev, [index]: 'error' }));
    }
  };

  // Only show Report if there’s at least one prior user message
  const hasPriorUserMessage = (idx) =>
    messages.slice(0, idx).some(m => m.role === 'user');

  return (
    <div className="gemini-chat-container">
      {toasts.map(toast => (
        <Toast 
          key={toast.id} 
          message={toast.message} 
          type={toast.type} 
          onClose={() => removeToast(toast.id)} 
        />
      ))}

      <header className="gemini-chat-header pro-header">
        <div className="brand pro">
          <div className="brand-mark pro" aria-hidden>
            <svg width="28" height="28" viewBox="0 0 24 24">
              <defs>
                <linearGradient id="sx-grad" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stopColor="#89b3f8"/><stop offset="100%" stopColor="#a789f8"/>
                </linearGradient>
                <radialGradient id="sx-glow" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="#a789f8" stopOpacity="0.35"/>
                  <stop offset="100%" stopColor="transparent"/>
                </radialGradient>
              </defs>
              <path d="M12 2.5l7 3.6v7.8l-7 7.6-7-7.6V6.1z" fill="url(#sx-grad)"/>
              <circle cx="12" cy="11.5" r="5.2" fill="none" stroke="rgba(19,19,20,.6)" strokeWidth="1.4"/>
              <path d="M12 7.2v4.3l3 3" fill="none" stroke="#131314" strokeWidth="1.6" strokeLinecap="round"/>
            </svg>
            <span className="brand-glow" />
          </div>

          <div className="brand-copy">
            <span className="brand-title">Sophos AI</span>
            <span className="brand-tagline">Secure Transport Expert</span>
          </div>

          <span className="brand-badge">beta</span>
        </div>

        <UserProfile user={user} onLogout={onLogout} />
      </header>

      <div className="gemini-messages-list">
        {isWelcomeScreen ? (
          <div className="welcome-screen">
            <div className="welcome-greeting">
              <span className="gradient-text">
                Hello, {(typeof user?.username === 'string' && user.username.trim()) ? user.username.trim() : 'User'}.
              </span>
              <span className="welcome-subtext">How can I help you today?</span>
            </div>
            <div className="suggestion-cards">
              <div className="card" onClick={() => handleCardClick('How do I install Axway Secure Transport?')}>
                <span className="card-icon" aria-hidden>📄</span>
                <p>Explain how to install Axway Secure Transport</p>
              </div>
              <div className="card" onClick={() => handleCardClick('Troubleshoot a failed file transfer.')}>
                <span className="card-icon" aria-hidden>🔧</span>
                <p>Troubleshoot a failed file transfer</p>
              </div>
              <div className="card" onClick={() => handleCardClick('What are the default ports for ST?')}>
                <span className="card-icon" aria-hidden>🔌</span>
                <p>List the default ports for Secure Transport</p>
              </div>
              <div className="card" onClick={() => handleCardClick('How to configure a new transfer site?')}>
                <span className="card-icon" aria-hidden>⚙️</span>
                <p>Configure a new transfer site</p>
              </div>
            </div>
          </div>
        ) : (
          messages.map((msg, index) => {
            const isAssistant = msg.role === 'assistant';
            const { visible, think } = splitThink(msg.content);
            const rState = reportState[index] || 'idle';
            const isReporting = rState === 'sending';
            const isReported = rState === 'done';

            const showReport = isAssistant && hasPriorUserMessage(index);

            return (
              <div 
                key={index} 
                className={`message-row ${isAssistant ? 'assistant' : 'user'}`}
                style={{ animationDelay: `${index * 0.05}s` }}
              >
                <div className={`chat-bubble ${isAssistant ? 'assistant' : 'user'}`}>
                  <div className="message-content">
                    <ReactMarkdown>{visible}</ReactMarkdown>
                  </div>

                  {isAssistant && think && (
                    <details className="think-details">
                      <summary>
                        <span className="dot-pulse" aria-hidden /> Show reasoning
                        {typeof msg.thoughtMs === 'number' && (
                          <span className="think-duration"> · {(msg.thoughtMs / 1000).toFixed(1)}s</span>
                        )}
                      </summary>
                      <pre className="think-block">{think}</pre>
                    </details>
                  )}

                  {isAssistant && msg.sources && msg.sources.length > 0 && (
                    <details className="source-details">
                      <summary>Show Sources ({msg.sources.length})</summary>
                      <div className="sources-container">
                        {msg.sources.map((source, s_index) => (
                          <div key={s_index} className="source-document">
                            <strong>Source {s_index + 1}: {source.metadata?.source_file || 'N/A'}</strong>
                            <pre>{(source.page_content || '').substring(0, 300)}...</pre>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}

                  {showReport && (
                    <div className="report-row">
                      {isReported ? (
                        <span className="report-status" aria-live="polite">Reported ✔</span>
                      ) : (
                        <button
                          className="report-link"
                          type="button"
                          onClick={() => handleReport(msg, index)}
                          disabled={isReporting}
                          aria-label="Report incorrect answer"
                        >
                          {isReporting ? 'Reporting…' : 'Report'}
                        </button>
                      )}
                      {rState === 'error' && (
                        <span className="report-error">Error. Try again.</span>
                      )}
                    </div>
                  )}

                  {isAssistant && typeof msg.thoughtMs === 'number' && (
                    <div className="meta-line">🧠 Thought for {(msg.thoughtMs / 1000).toFixed(1)}s</div>
                  )}

                  {isAssistant && (msg.retrievalTimeMs || msg.thoughtTimeMs || msg.totalTimeMs) && (
                    <div className="meta-info">
                      {msg.retrievalTimeMs && (
                        <span className="meta-info-item">
                          <strong>⚡ Retrieval:</strong> {msg.retrievalTimeMs}ms
                        </span>
                      )}
                      {msg.thoughtTimeMs && (
                        <span className="meta-info-item">
                          <strong>🧠 Thought:</strong> {(msg.thoughtTimeMs / 1000).toFixed(1)}s
                        </span>
                      )}
                      {msg.totalTimeMs && (
                        <span className="meta-info-item">
                          <strong>📊 Total:</strong> {(msg.totalTimeMs / 1000).toFixed(1)}s
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}

        {isRetrieving && (
          <div className="message-row assistant">
            <div className="chat-bubble assistant">
              <div className="retrieving-indicator">
                <span className="dot-pulse" aria-hidden />
                Searching knowledge base...
              </div>
            </div>
          </div>
        )}

        {isLoading && !isRetrieving && (
          <div className="message-row assistant">
            <div className="chat-bubble assistant">
              <div className="thinking-line">
                <span className="dot-pulse" aria-hidden />
                Thinking… {(liveElapsedMs / 1000).toFixed(1)}s
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="gemini-input-area">
        <form onSubmit={handleFormSubmit} className="gemini-input-form">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Enter a prompt here"
            disabled={isLoading}
          />
        <button type="submit" disabled={!input.trim() || isLoading}>
            <svg xmlns="http://www.w3.org/2000/svg" height="24px" viewBox="0 0 24 24" width="24px" fill="#FFFFFF">
              <path d="M0 0h24v24H0V0z" fill="none"/>
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2 .01 7z"/>
            </svg>
          </button>
        </form>
        <p className="footer-text">Sophos AI can make mistakes. Consider checking important information.</p>
      </div>
    </div>
  );
}