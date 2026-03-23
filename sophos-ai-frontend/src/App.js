import React, { useState, useEffect } from 'react';
import Login from './components/Login';
import Chat from './components/Chat';
import Sidebar from './components/Sidebar';
import './App.css';

function App() {
  const [user, setUser] = useState(null);
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  const toggleSidebar = () => setIsSidebarCollapsed(v => !v);

  // Load chats from localStorage on mount
  useEffect(() => {
    const savedChats = localStorage.getItem('sophos_ai_chats');
    if (savedChats) {
      try {
        setChats(JSON.parse(savedChats));
      } catch (err) {
        console.error('Failed to load chats from localStorage:', err);
      }
    }
  }, []);

  // Save chats to localStorage whenever they change
  useEffect(() => {
    if (chats.length > 0) {
      localStorage.setItem('sophos_ai_chats', JSON.stringify(chats));
    }
  }, [chats]);

  // Get exact username used at login (falls back to 'User')
  const getLoginUsername = (u) =>
    (typeof u?.username === 'string' && u.username.trim()) ? u.username.trim() : 'User';

  // Create a new chat with a greeting
  const handleNewChat = (displayName) => {
    const id = Date.now().toString();
    const name = (typeof displayName === 'string' && displayName.trim())
      ? displayName.trim()
      : getLoginUsername(user);

    const newChat = {
      id,
      title: 'New Chat',
      messages: [
        { role: 'assistant', content: `Hello, ${name}! How can I assist you today?` }
      ],
    };
    setChats(prev => [newChat, ...prev]);
    setActiveChatId(id);
  };

  const handleLoginSuccess = (userData) => {
    setUser(userData);
    // We no longer call handleNewChat here; the effect below will bootstrap exactly once if needed.
  };

  const handleSwitchChat = (chatId) => setActiveChatId(chatId);

  // Delete a chat
  const handleDeleteChat = (chatId) => {
    setChats(prev => {
      const next = prev.filter(c => c.id !== chatId);
      // Update active selection if we deleted the active one
      if (activeChatId === chatId) {
        setActiveChatId(next.length ? next[0].id : null);
      }
      return next;
    });
  };

  // Single source of truth: if user is logged in and there are zero chats,
  // create exactly ONE welcome chat. This prevents double-creation.
  useEffect(() => {
    if (user && chats.length === 0) {
      handleNewChat(getLoginUsername(user));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, chats.length]);

  const updateMessages = (newMessages, chatId) => {
    setChats(prev => prev.map(chat => {
      if (chat.id !== chatId) return chat;

      // Auto-rename title to first user question
      const firstUser = newMessages.find(m => m.role === 'user' && m.content?.trim());
      let nextTitle = chat.title;

      if (firstUser) {
        const firstLine = firstUser.content.trim().split('\n')[0];
        const trimmed = firstLine.length > 40 ? firstLine.slice(0, 40) + '…' : firstLine;
        if (!chat.title || chat.title === 'New Chat' || chat.title.startsWith('Untitled')) {
          nextTitle = trimmed || 'New Chat';
        }
      }

      return { ...chat, messages: newMessages, title: nextTitle };
    }));
  };

  const handleLogout = () => {
    setUser(null);
    setChats([]);
    setActiveChatId(null);
  };

  const activeChat = chats.find(c => c.id === activeChatId) || null;

  return (
    <div className={`main-app-container ${!user ? 'auth' : ''}`}>
      {!user ? (
        <Login onLoginSuccess={handleLoginSuccess} />
      ) : (
        <>
          <Sidebar
            chats={chats}
            activeChatId={activeChatId}
            onNewChat={() => handleNewChat(getLoginUsername(user))}
            onSwitchChat={handleSwitchChat}
            onDeleteChat={handleDeleteChat}
            isCollapsed={isSidebarCollapsed}
            onToggleCollapse={toggleSidebar}
          />

          <div className="chat-main">
            {activeChat && (
              <Chat
                key={activeChat.id}
                user={user}
                chatSession={activeChat}
                onMessagesUpdate={updateMessages}
                onLogout={handleLogout}
              />
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default App;