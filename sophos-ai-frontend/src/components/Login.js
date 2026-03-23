import React, { useState } from 'react';

const API_BASE_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

export default function Login({ onLoginSuccess }) {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    const handleLogin = async (e) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);

        try {
            const response = await fetch(`${API_BASE_URL}/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });

            if (!response.ok) {
                throw new Error('Invalid username or password');
            }

            const userData = await response.json();
            onLoginSuccess(userData);

        } catch (err) {
            setError(err.message);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="gemini-login-container">
            <form onSubmit={handleLogin} className="gemini-login-form">
                <div className="gemini-logo">
                    <img src="/favicon.svg" alt="Sophos AI" />
                </div>    
                <h2>Welcome to Sophos AI</h2>
                <p>Please sign in to continue</p>
                <div className="form-group">
                    <input
                        type="text"
                        placeholder="Username"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        required
                    />
                </div>
                <div className="form-group">
                    <input
                        type="password"
                        placeholder="Password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                    />
                </div>
                <button type="submit" disabled={isLoading}>
                    {isLoading ? 'Signing in...' : 'Sign In'}
                </button>
                {error && <p className="error-message">{error}</p>}
            </form>
        </div>
    );
}
