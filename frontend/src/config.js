const host = window.location.hostname;
export const API_URL = host.endsWith("buyndermarket.com") ? "https://api.buyndermarket.com" : `http://${host}:5050`;
export function apiFetch(path, options = {}) {
  return fetch(`${API_URL}${path}`, {
    ...options,
    credentials: "include"
  });
}
