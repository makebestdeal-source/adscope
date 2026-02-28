"use client";

import { useState } from "react";
import Link from "next/link";

const API_BASE = "/api";

export default function ForgotPasswordPage() {
  // Step 1: request token, Step 2: reset password
  const [step, setStep] = useState<1 | 2>(1);
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function handleRequestToken(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Request failed");
      }

      setMessage("Reset token has been generated. Please check your email or enter the token below.");
      // In dev mode, auto-fill the token if returned
      if (data.reset_token) {
        setToken(data.reset_token);
      }
      setStep(2);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleResetPassword(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setMessage("");

    if (newPassword !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    if (!/[a-zA-Z]/.test(newPassword) || !/[0-9]/.test(newPassword)) {
      setError("Password must contain both letters and digits");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: newPassword }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Reset failed");
      }

      setMessage("Password has been reset successfully. You can now log in with your new password.");
      setNewPassword("");
      setConfirmPassword("");
      setToken("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="w-full max-w-sm mx-4">
        {/* Logo / Title */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">
            AdScope
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Password Recovery
          </p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
          {step === 1 ? (
            <>
              <h2 className="text-lg font-semibold text-slate-800 mb-2">
                Forgot Password
              </h2>
              <p className="text-sm text-slate-500 mb-6">
                Enter your email address and we will send you a reset token.
              </p>

              {error && (
                <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
                  {error}
                </div>
              )}

              <form onSubmit={handleRequestToken} className="space-y-4">
                <div>
                  <label htmlFor="fp-email" className="block text-sm font-medium text-slate-700 mb-1">
                    Email
                  </label>
                  <input
                    id="fp-email"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm
                               focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-adscope-500
                               placeholder-slate-400"
                    placeholder="your@email.com"
                  />
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full py-2.5 px-4 bg-adscope-600 hover:bg-adscope-700 disabled:bg-adscope-400
                             text-white text-sm font-medium rounded-lg transition-colors
                             focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:ring-offset-2"
                >
                  {loading ? "Sending..." : "Send Reset Token"}
                </button>
              </form>
            </>
          ) : (
            <>
              <h2 className="text-lg font-semibold text-slate-800 mb-2">
                Reset Password
              </h2>
              <p className="text-sm text-slate-500 mb-6">
                Enter the reset token and your new password.
              </p>

              {message && (
                <div className="mb-4 p-3 rounded-lg bg-green-50 border border-green-200 text-sm text-green-700">
                  {message}
                </div>
              )}
              {error && (
                <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
                  {error}
                </div>
              )}

              <form onSubmit={handleResetPassword} className="space-y-4">
                <div>
                  <label htmlFor="fp-token" className="block text-sm font-medium text-slate-700 mb-1">
                    Reset Token
                  </label>
                  <input
                    id="fp-token"
                    type="text"
                    required
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono
                               focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-adscope-500
                               placeholder-slate-400"
                    placeholder="Paste your reset token"
                  />
                </div>

                <div>
                  <label htmlFor="fp-new-pw" className="block text-sm font-medium text-slate-700 mb-1">
                    New Password
                  </label>
                  <input
                    id="fp-new-pw"
                    type="password"
                    required
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm
                               focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-adscope-500
                               placeholder-slate-400"
                    placeholder="8+ characters, letters and digits"
                  />
                </div>

                <div>
                  <label htmlFor="fp-confirm-pw" className="block text-sm font-medium text-slate-700 mb-1">
                    Confirm Password
                  </label>
                  <input
                    id="fp-confirm-pw"
                    type="password"
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm
                               focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-adscope-500"
                  />
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full py-2.5 px-4 bg-adscope-600 hover:bg-adscope-700 disabled:bg-adscope-400
                             text-white text-sm font-medium rounded-lg transition-colors
                             focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:ring-offset-2"
                >
                  {loading ? "Resetting..." : "Reset Password"}
                </button>
              </form>

              <button
                onClick={() => { setStep(1); setError(""); setMessage(""); }}
                className="mt-3 w-full text-center text-sm text-slate-500 hover:text-slate-700"
              >
                Back to email input
              </button>
            </>
          )}
        </div>

        <div className="text-center mt-6 space-y-2">
          <Link
            href="/login"
            className="text-sm text-indigo-600 hover:text-indigo-800 font-medium"
          >
            Back to Sign In
          </Link>
          <p className="text-xs text-slate-400">AdScope v0.2.0</p>
        </div>
      </div>
    </div>
  );
}
