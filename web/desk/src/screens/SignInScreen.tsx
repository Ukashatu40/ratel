// SignInScreen.tsx

import React, { useState } from 'react';
import { ApiError } from '../lib/api';
import './SignInScreen.css';

interface SignInScreenProps {
  onSignIn: (email: string, password: string) => Promise<void>;
}

export const SignInScreen: React.FC<SignInScreenProps> = ({ onSignIn }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) {
      setError('Please enter your staff email address');
      return;
    }
    if (!password) {
      setError('Please enter your password');
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      await onSignIn(email.trim(), password);
    } catch (err) {
      // The API gives one answer for every refusal (wrong email, wrong password, disabled or locked account), so we do too.
      setError(
        err instanceof ApiError && err.status === 401
          ? 'Email or password is not right.'
          : err instanceof ApiError && err.status === 429
            ? 'Too many attempts. Wait a few minutes and try again.'
            : 'Could not sign in. Check your connection and try again.',
      );
      setPassword('');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="signin-container">
      {/* LEFT BLUE HERO PANEL */}
      <div className="signin-hero">
        <div className="signin-hero-content">
          <div className="signin-hero-tag">
            RatelDesk for Ratelplus staff
          </div>

          <h1 className="signin-hero-title">
            Serve every customer faster.
          </h1>

          <p className="signin-hero-subtitle">
            Sell SIMs, check identities, top up lines and keep the books right, all from one place.
          </p>

          <div className="signin-features-list">
            <div className="signin-feature-item">
              <span className="signin-feature-badge">✓</span>
              <span className="signin-feature-text">
                Find any line by number, ICCID or IMSI in seconds
              </span>
            </div>

            <div className="signin-feature-item">
              <span className="signin-feature-badge">✓</span>
              <span className="signin-feature-text">
                Lines activate only after KYC is verified
              </span>
            </div>

            <div className="signin-feature-item">
              <span className="signin-feature-badge">✓</span>
              <span className="signin-feature-text">
                Every change is recorded in the audit log
              </span>
            </div>
          </div>
        </div>

        {/* Responsive Brand Signal Arcs SVG (Positioned genuinely under the writing) */}
        <div className="signin-hero-arcs-wrapper">
          <svg
            className="signin-hero-arcs-svg"
            viewBox="0 0 1000 600"
            fill="none"
            preserveAspectRatio="xMaxYMax meet"
            xmlns="http://www.w3.org/2000/svg"
          >
            {/* Outer Soft Blue Arc */}
            <path
              d="M 380 600 A 500 500 0 0 1 870 120"
              stroke="#5880E8"
              strokeWidth="22"
              strokeLinecap="round"
            />

            {/* Faint Ambient Ghost Guide Track */}
            <path
              d="M 440 602 A 440 440 0 0 1 872 180"
              stroke="rgba(255, 255, 255, 0.08)"
              strokeWidth="24"
              strokeLinecap="round"
            />

            {/* Transparent Under-Layer beneath Yellow Curve */}
            <path
              d="M 505 605 A 375 375 0 0 1 874 245"
              stroke="rgba(255, 255, 255, 0.2)"
              strokeWidth="36"
              strokeLinecap="round"
            />

            {/* Golden Yellow Arc (Layered over transparent track) */}
            <path
              d="M 505 605 A 375 375 0 0 1 874 245"
              stroke="#FDB813"
              strokeWidth="20"
              strokeLinecap="round"
            />

            {/* Transparent Under-Layer beneath Red Curve */}
            <path
              d="M 630 610 A 250 250 0 0 1 877 370"
              stroke="rgba(255, 255, 255, 0.2)"
              strokeWidth="36"
              strokeLinecap="round"
            />

            {/* Inner Red Arc (Layered over transparent track) */}
            <path
              d="M 630 610 A 250 250 0 0 1 877 370"
              stroke="#E61C38"
              strokeWidth="20"
              strokeLinecap="round"
            />
          </svg>
        </div>
      </div>

      {/* RIGHT WHITE LOGIN PANEL */}
      <div className="signin-form-panel">
        <div className="signin-form-card">
          {/* Ratel Logo Inside Elevated Shadowed Box */}
          <div className="signin-logo-box">
            <img
              src="/ratel_logo.png"
              alt="Ratel - Power to Connect"
              className="signin-logo-img"
            />
          </div>

          {/* Heading */}
          <div className="signin-heading-box">
            <h2 className="signin-heading">Welcome back</h2>
            <p className="signin-subheading">Sign in with your Ratelplus staff account.</p>
          </div>

          {error && (
            <div style={{
              padding: '10px 14px',
              backgroundColor: '#fef2f2',
              color: '#b91c1c',
              border: '1px solid #fecaca',
              borderRadius: '6px',
              fontSize: '13px',
              marginBottom: '1rem',
              width: '100%',
              boxSizing: 'border-box'
            }}>
              {error}
            </div>
          )}

          {/* Sign In Form */}
          <form onSubmit={handleSubmit} className="signin-form">
            <div className="signin-field">
              <label htmlFor="staff-email" className="signin-label">Email</label>
              <div className="signin-input-wrapper">
                <input
                  id="staff-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="amina.yusuf@ratelplus.example"
                  className="signin-input"
                  required
                />
              </div>
            </div>

            <div className="signin-field">
              <div className="signin-field-header">
                <label htmlFor="staff-password" className="signin-label">Password</label>
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="signin-show-toggle"
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
              <div className="signin-input-wrapper">
                <input
                  id="staff-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="signin-input"
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="signin-submit-btn"
            >
              {isLoading ? 'Verifying...' : 'Sign in to RatelDesk'}
            </button>
          </form>

          <p className="signin-vpn-notice">
            Accessible only from the office network or VPN.
          </p>
        </div>

        {import.meta.env.VITE_USE_MOCK === 'true' && (
          <div className="signin-watermark">
            Mockup with sample data.
          </div>
        )}
      </div>
    </div>
  );
};