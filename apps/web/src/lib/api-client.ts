// Placeholder fetch wrapper. Base URL config to be wired from env later.
const BASE_URL = "";

export async function apiClient(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${BASE_URL}${path}`, init);
}
