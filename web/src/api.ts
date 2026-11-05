let csrf = "";
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.method && options.method !== "GET"
        ? { "X-CSRF-Token": csrf }
        : {}),
      ...options.headers,
    },
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      data.error?.message || data.detail || "Unable to complete this request.",
    );
  return data as T;
}

export function setCsrf(value: string) {
  csrf = value;
}
