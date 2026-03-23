import React, { useState, useEffect, useRef } from 'react';

export default function UserProfile({ user, onLogout }) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const profileRef = useRef(null);

  // Effect to handle clicks outside the component to close the menu
  useEffect(() => {
    function handleClickOutside(event) {
      if (profileRef.current && !profileRef.current.contains(event.target)) {
        setIsMenuOpen(false);
      }
    }
    // Add event listener when the menu is open
    if (isMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    // Cleanup the event listener
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isMenuOpen]);


  return (
    <div className="user-profile" ref={profileRef} onClick={() => setIsMenuOpen(!isMenuOpen)}>
      <span>{user.username}</span>
      <div className="user-initial">{user.username.charAt(0).toUpperCase()}</div>
      
      {isMenuOpen && (
        <div className="profile-menu">
            <button onClick={onLogout}>Logout</button>
        </div>
      )}
    </div>
  );
}