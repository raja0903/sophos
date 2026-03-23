import React from 'react';

export default function Sidebar({
  chats,
  activeChatId,
  onNewChat,
  onSwitchChat,
  onDeleteChat,
  isCollapsed,
  onToggleCollapse,
}) {
  const handleDelete = (e, chatId) => {
    e.stopPropagation();
    onDeleteChat(chatId);
  };

  return (
    <div className={`sidebar ${isCollapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header">
        {!isCollapsed && <h3>Chats</h3>}

        <div className="sidebar-actions">
          {/* New chat (full pill when expanded, icon when collapsed) */}
          <button
            className={`new-chat-cta ${isCollapsed ? 'icon-only' : ''}`}
            title="New chat"
            onClick={onNewChat}
          >
            {/* plus-circle icon */}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path d="M12 7v10M7 12h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/>
            </svg>
            {!isCollapsed && <span className="label">New chat</span>}
          </button>

          {/* Collapse/expand with chevron icon */}
          <button
            className="collapse-btn"
            title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={onToggleCollapse}
          >
            {isCollapsed ? (
              // chevron-right
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
                <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            ) : (
              // chevron-left
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
                <path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            )}
          </button>
        </div>
      </div>

      <div className="chat-list">
        {chats.map((chat, index) => (
          <div
            key={chat.id}
            className={`chat-list-item ${activeChatId === chat.id ? 'active' : ''}`}
            onClick={() => onSwitchChat(chat.id)}
            title={isCollapsed ? chat.title : undefined}
          >
            {isCollapsed ? (
              <span className="chat-number-badge">{index + 1}</span>
            ) : (
              <>
                <span className="chat-title">{chat.title}</span>
                <button
                  className="delete-chat-btn"
                  onClick={(e) => handleDelete(e, chat.id)}
                  title="Delete"
                >
                  ×
                </button>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
