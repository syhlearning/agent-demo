const ACCESS_TOKEN_KEY = "accessToken";
const REFRESH_TOKEN_KEY = "refreshToken";
const ACCESS_EXPIRES_AT_KEY = "accessTokenExpiresAt";
const REFRESH_EXPIRES_AT_KEY = "refreshTokenExpiresAt";
const REFRESH_SKEW_MS = 30_000;

export const AUTH_EXPIRED_EVENT = "auth:expired";

type TokenResponse = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  refresh_expires_in: number;
};

let refreshPromise: Promise<boolean> | null = null;

export function getAccessToken() {
  return sessionStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken() {
  return sessionStorage.getItem(REFRESH_TOKEN_KEY);
}

export function saveAuthTokens(
  accessToken: string,
  refreshToken: string,
  expiresIn: number,
  refreshExpiresIn: number
) {
  const now = Date.now();
  sessionStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  sessionStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  sessionStorage.setItem(ACCESS_EXPIRES_AT_KEY, String(now + expiresIn * 1000));
  sessionStorage.setItem(REFRESH_EXPIRES_AT_KEY, String(now + refreshExpiresIn * 1000));
}

export function clearAuthTokens() {
  sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  sessionStorage.removeItem(REFRESH_TOKEN_KEY);
  sessionStorage.removeItem(ACCESS_EXPIRES_AT_KEY);
  sessionStorage.removeItem(REFRESH_EXPIRES_AT_KEY);
}

function notifyAuthExpired() {
  window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
}

function shouldRefreshAccessToken() {
  const accessToken = getAccessToken();
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  if (!accessToken) return true;

  const expiresAt = Number(sessionStorage.getItem(ACCESS_EXPIRES_AT_KEY) || 0);
  return Boolean(expiresAt && Date.now() >= expiresAt - REFRESH_SKEW_MS);
}

export async function refreshAccessToken() {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) return false;

    const response = await fetch("/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) {
      clearAuthTokens();
      notifyAuthExpired();
      return false;
    }

    const data = await response.json() as TokenResponse;
    saveAuthTokens(
      data.access_token,
      data.refresh_token,
      data.expires_in,
      data.refresh_expires_in
    );
    return true;
  })().finally(() => {
    refreshPromise = null;
  });

  return refreshPromise;
}

export async function ensureFreshAccessToken() {
  if (!shouldRefreshAccessToken()) return Boolean(getAccessToken());
  return refreshAccessToken();
}

async function fetchWithAuth(input: RequestInfo | URL, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  const accessToken = getAccessToken();
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  return fetch(input, { ...init, headers });
}

export async function authFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  await ensureFreshAccessToken();

  let response = await fetchWithAuth(input, init);
  if (response.status !== 401) return response;

  const refreshed = await refreshAccessToken();
  if (!refreshed) return response;

  response = await fetchWithAuth(input, init);
  return response;
}
