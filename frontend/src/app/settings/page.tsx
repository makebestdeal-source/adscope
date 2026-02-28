"use client";

import { useState, useEffect, useCallback } from "react";
import { getToken, getUser, AuthUser } from "@/lib/auth";
import Link from "next/link";

const API_BASE = "/api";

async function fetchApi<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string>),
  };
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("adscope_token");
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const fp = localStorage.getItem("adscope_device_fp");
    if (fp) headers["X-Device-Fingerprint"] = fp;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `Error ${res.status}`);
  }
  return res.json();
}

interface ProfileData {
  id: number;
  email: string;
  name: string | null;
  role: string;
  company_name: string | null;
  phone: string | null;
  plan: string | null;
  plan_period: string | null;
  plan_started_at: string | null;
  plan_expires_at: string | null;
  created_at: string | null;
}

interface LoginRecord {
  id: number;
  email: string;
  ip_address: string | null;
  success: boolean;
  failure_reason: string | null;
  created_at: string | null;
}

export default function SettingsPage() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loginHistory, setLoginHistory] = useState<LoginRecord[]>([]);

  // Profile form
  const [name, setName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [phone, setPhone] = useState("");
  const [profileMsg, setProfileMsg] = useState("");
  const [profileError, setProfileError] = useState("");
  const [profileLoading, setProfileLoading] = useState(false);

  // Password form
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwMsg, setPwMsg] = useState("");
  const [pwError, setPwError] = useState("");
  const [pwLoading, setPwLoading] = useState(false);

  const loadProfile = useCallback(async () => {
    try {
      const data = await fetchApi<ProfileData>("/auth/profile");
      setProfile(data);
      setName(data.name || "");
      setCompanyName(data.company_name || "");
      setPhone(data.phone || "");
    } catch {
      // ignore
    }
  }, []);

  const loadLoginHistory = useCallback(async () => {
    try {
      const data = await fetchApi<LoginRecord[]>("/auth/my-login-history");
      setLoginHistory(data);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    const u = getUser();
    if (!u) {
      window.location.href = "/login";
      return;
    }
    setUser(u);
    loadProfile();
    loadLoginHistory();
  }, [loadProfile, loadLoginHistory]);

  async function handleProfileSubmit(e: React.FormEvent) {
    e.preventDefault();
    setProfileMsg("");
    setProfileError("");
    setProfileLoading(true);
    try {
      const body: Record<string, string> = {};
      if (name !== (profile?.name || "")) body.name = name;
      if (companyName !== (profile?.company_name || "")) body.company_name = companyName;
      if (phone !== (profile?.phone || "")) body.phone = phone;

      if (Object.keys(body).length === 0) {
        setProfileError("No changes to save");
        setProfileLoading(false);
        return;
      }

      await fetchApi("/auth/profile", {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      setProfileMsg("Profile updated successfully");
      // Update local storage user info
      const stored = getUser();
      if (stored) {
        if (body.name !== undefined) stored.name = body.name;
        if (body.company_name !== undefined) stored.company_name = body.company_name;
        localStorage.setItem("adscope_user", JSON.stringify(stored));
      }
      await loadProfile();
    } catch (err: unknown) {
      setProfileError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setProfileLoading(false);
    }
  }

  async function handlePasswordSubmit(e: React.FormEvent) {
    e.preventDefault();
    setPwMsg("");
    setPwError("");

    if (newPassword !== confirmPassword) {
      setPwError("New passwords do not match");
      return;
    }
    if (newPassword.length < 8) {
      setPwError("Password must be at least 8 characters");
      return;
    }
    if (!/[a-zA-Z]/.test(newPassword) || !/[0-9]/.test(newPassword)) {
      setPwError("Password must contain both letters and digits");
      return;
    }

    setPwLoading(true);
    try {
      await fetchApi("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      setPwMsg("Password changed successfully");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: unknown) {
      setPwError(err instanceof Error ? err.message : "Password change failed");
    } finally {
      setPwLoading(false);
    }
  }

  if (!user) return null;

  const planLabel =
    user.role === "admin" ? "Admin" : profile?.plan === "full" ? "Full" : "Lite";
  const periodLabel =
    profile?.plan_period === "yearly" ? "Annual" : "Monthly";

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
        <p className="text-sm text-slate-500 mt-1">Manage your profile and account settings</p>
      </div>

      {/* Profile Section */}
      <section className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
        <h2 className="text-lg font-semibold text-slate-800 mb-4">Profile Information</h2>

        {profileMsg && (
          <div className="mb-4 p-3 rounded-lg bg-green-50 border border-green-200 text-sm text-green-700">
            {profileMsg}
          </div>
        )}
        {profileError && (
          <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
            {profileError}
          </div>
        )}

        <form onSubmit={handleProfileSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
            <input
              type="email"
              value={profile?.email || ""}
              disabled
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-slate-50 text-slate-500"
            />
          </div>

          <div>
            <label htmlFor="settings-name" className="block text-sm font-medium text-slate-700 mb-1">
              Name
            </label>
            <input
              id="settings-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-adscope-500"
            />
          </div>

          <div>
            <label htmlFor="settings-company" className="block text-sm font-medium text-slate-700 mb-1">
              Company
            </label>
            <input
              id="settings-company"
              type="text"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-adscope-500"
            />
          </div>

          <div>
            <label htmlFor="settings-phone" className="block text-sm font-medium text-slate-700 mb-1">
              Phone
            </label>
            <input
              id="settings-phone"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-adscope-500"
              placeholder="010-0000-0000"
            />
          </div>

          <button
            type="submit"
            disabled={profileLoading}
            className="px-4 py-2 bg-adscope-600 hover:bg-adscope-700 disabled:bg-adscope-400 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {profileLoading ? "Saving..." : "Save Changes"}
          </button>
        </form>
      </section>

      {/* Password Section */}
      <section className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
        <h2 className="text-lg font-semibold text-slate-800 mb-4">Change Password</h2>

        {pwMsg && (
          <div className="mb-4 p-3 rounded-lg bg-green-50 border border-green-200 text-sm text-green-700">
            {pwMsg}
          </div>
        )}
        {pwError && (
          <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
            {pwError}
          </div>
        )}

        <form onSubmit={handlePasswordSubmit} className="space-y-4">
          <div>
            <label htmlFor="current-pw" className="block text-sm font-medium text-slate-700 mb-1">
              Current Password
            </label>
            <input
              id="current-pw"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-adscope-500"
            />
          </div>

          <div>
            <label htmlFor="new-pw" className="block text-sm font-medium text-slate-700 mb-1">
              New Password
            </label>
            <input
              id="new-pw"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-adscope-500"
              placeholder="8+ characters, letters and digits"
            />
          </div>

          <div>
            <label htmlFor="confirm-pw" className="block text-sm font-medium text-slate-700 mb-1">
              Confirm New Password
            </label>
            <input
              id="confirm-pw"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-adscope-500"
            />
          </div>

          <button
            type="submit"
            disabled={pwLoading}
            className="px-4 py-2 bg-adscope-600 hover:bg-adscope-700 disabled:bg-adscope-400 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {pwLoading ? "Changing..." : "Change Password"}
          </button>
        </form>
      </section>

      {/* Plan Info Section */}
      <section className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
        <h2 className="text-lg font-semibold text-slate-800 mb-4">Plan Information</h2>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-slate-500 mb-1">Current Plan</p>
            <span className={`inline-block text-sm font-semibold px-2 py-1 rounded ${
              user.role === "admin"
                ? "bg-amber-100 text-amber-800"
                : profile?.plan === "full"
                ? "bg-green-100 text-green-800"
                : "bg-slate-100 text-slate-700"
            }`}>
              {planLabel}
            </span>
          </div>
          <div>
            <p className="text-xs text-slate-500 mb-1">Billing Period</p>
            <p className="text-sm text-slate-800 font-medium">
              {user.role === "admin" ? "-" : periodLabel}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500 mb-1">Member Since</p>
            <p className="text-sm text-slate-800">
              {profile?.created_at
                ? new Date(profile.created_at).toLocaleDateString("ko-KR")
                : "-"}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500 mb-1">Plan Expires</p>
            <p className="text-sm text-slate-800">
              {profile?.plan_expires_at
                ? new Date(profile.plan_expires_at).toLocaleDateString("ko-KR")
                : user.role === "admin" ? "-" : "N/A"}
            </p>
          </div>
        </div>

        {user.role !== "admin" && (
          <div className="mt-4 pt-4 border-t border-slate-100">
            <Link
              href="/pricing"
              className="text-sm text-adscope-600 hover:text-adscope-700 font-medium"
            >
              View Plans & Upgrade
            </Link>
          </div>
        )}
      </section>

      {/* Login History Section */}
      <section className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
        <h2 className="text-lg font-semibold text-slate-800 mb-4">Login History</h2>

        {loginHistory.length === 0 ? (
          <p className="text-sm text-slate-500">No login history available.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="text-left py-2 px-2 text-slate-600 font-medium">Date</th>
                  <th className="text-left py-2 px-2 text-slate-600 font-medium">IP Address</th>
                  <th className="text-left py-2 px-2 text-slate-600 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {loginHistory.slice(0, 20).map((record) => (
                  <tr key={record.id} className="border-b border-slate-100">
                    <td className="py-2 px-2 text-slate-700">
                      {record.created_at
                        ? new Date(record.created_at).toLocaleString("ko-KR", {
                            timeZone: "Asia/Seoul",
                          })
                        : "-"}
                    </td>
                    <td className="py-2 px-2 text-slate-600 font-mono text-xs">
                      {record.ip_address || "-"}
                    </td>
                    <td className="py-2 px-2">
                      {record.success ? (
                        <span className="inline-block text-xs font-medium px-1.5 py-0.5 rounded bg-green-100 text-green-700">
                          Success
                        </span>
                      ) : (
                        <span className="inline-block text-xs font-medium px-1.5 py-0.5 rounded bg-red-100 text-red-700">
                          {record.failure_reason || "Failed"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
