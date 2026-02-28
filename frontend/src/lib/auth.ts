/** AdScope authentication utilities with device fingerprinting. */

const API_BASE = "/api";
const TOKEN_KEY = "adscope_token";
const USER_KEY = "adscope_user";
const FP_KEY = "adscope_device_fp";

export interface AuthUser {
  id: number;
  email: string;
  name: string | null;
  role: string;
  plan?: string;  // "lite", "full", "admin"
  paid?: boolean; // payment_confirmed
  company_name?: string;
  plan_period?: string;
  plan_expires_at?: string;
  trial_started_at?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

/** Set a simple cookie (accessible by Next.js middleware). */
function setCookie(name: string, value: string, days: number) {
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
}

/** Remove a cookie. */
function removeCookie(name: string) {
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Lax`;
}

/**
 * Generate a browser fingerprint based on stable browser characteristics.
 * Used to bind sessions to a specific device (non-admin only).
 */
function generateDeviceFingerprint(): string {
  const cached = localStorage.getItem(FP_KEY);
  if (cached) return cached;

  const components: string[] = [];
  components.push(`${screen.width}x${screen.height}x${screen.colorDepth}`);
  components.push(Intl.DateTimeFormat().resolvedOptions().timeZone);
  components.push(navigator.language);
  components.push(navigator.platform);
  components.push(navigator.userAgent.slice(0, 80));

  try {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (ctx) {
      canvas.width = 200;
      canvas.height = 50;
      ctx.textBaseline = "top";
      ctx.font = "14px Arial";
      ctx.fillStyle = "#f60";
      ctx.fillRect(50, 0, 80, 50);
      ctx.fillStyle = "#069";
      ctx.fillText("AdScope FP", 2, 15);
      ctx.fillStyle = "rgba(102, 204, 0, 0.7)";
      ctx.fillText("AdScope FP", 4, 17);
      components.push(canvas.toDataURL().slice(-50));
    }
  } catch {
    components.push("no-canvas");
  }

  const raw = components.join("|");
  let hash = 0;
  for (let i = 0; i < raw.length; i++) {
    const chr = raw.charCodeAt(i);
    hash = ((hash << 5) - hash) + chr;
    hash |= 0;
  }
  const fp = `fp_${Math.abs(hash).toString(36)}`;
  localStorage.setItem(FP_KEY, fp);
  return fp;
}

/** Get the device fingerprint (for API headers). */
export function getDeviceFingerprint(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(FP_KEY) || null;
}

/**
 * Authenticate with email + password.
 * Sends device fingerprint for session binding (non-admin accounts).
 */
export async function login(email: string, password: string): Promise<LoginResponse> {
  const deviceFingerprint = generateDeviceFingerprint();

  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, device_fingerprint: deviceFingerprint }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const msg = body?.detail || "Login failed";
    throw new Error(msg);
  }

  const data: LoginResponse = await res.json();
  localStorage.setItem(TOKEN_KEY, data.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(data.user));
  setCookie(TOKEN_KEY, data.access_token, 1);
  return data;
}

/** Return the stored JWT, or null if not logged in. */
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

/** Return the stored user info, or null. */
export function getUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

/** Clear stored credentials and redirect to /login. */
export async function logout(): Promise<void> {
  const token = getToken();
  if (token) {
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
      });
    } catch {
      // Ignore - still clear local state
    }
  }

  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  removeCookie(TOKEN_KEY);
  window.location.href = "/login";
}

/** Check whether a token exists in localStorage. */
export function isAuthenticated(): boolean {
  return getToken() !== null;
}

/** Get user's plan. Admin always gets full access. */
export function getUserPlan(): string {
  const user = getUser();
  if (!user) return "lite";
  if (user.role === "admin") return "admin";
  return user.plan || "lite";
}

/** Check if user has access to full features (gallery, social). */
export function hasFullAccess(): boolean {
  const plan = getUserPlan();
  return plan === "full" || plan === "admin";
}

/** Check if user is a paid member (payment_confirmed or admin). */
export function isPaid(): boolean {
  const user = getUser();
  if (!user) return false;
  if (user.role === "admin") return true;
  return !!user.paid;
}

/** Check if user's plan has expired. */
export function isPlanExpired(): boolean {
  const user = getUser();
  if (!user || user.role === "admin") return false;
  if (!user.plan_expires_at) return false;
  return new Date(user.plan_expires_at) < new Date();
}

/** Get days remaining until plan expires. */
export function daysUntilExpiry(): number | null {
  const user = getUser();
  if (!user || !user.plan_expires_at) return null;
  const diff = new Date(user.plan_expires_at).getTime() - Date.now();
  return Math.ceil(diff / (1000 * 60 * 60 * 24));
}
