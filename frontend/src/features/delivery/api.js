export async function request(path, method = "GET", body) {
  const response = await fetch(path, {
    signal: AbortSignal.timeout(12000),
    method, credentials: "same-origin", cache: "no-store",
    headers: body ? { Accept: "application/json", "Content-Type": "application/json" } : { Accept: "application/json" },
    body: body && JSON.stringify(body),
  });
  const value = await response.json().catch(() => {
    throw Object.assign(new Error("Invalid server response"), { status: response.status });
  });
  if (!response.ok) {
    const detail = value.detail ?? value;
    throw Object.assign(new Error(detail.code ?? "Request failed"), { status: response.status, detail });
  }
  return value;
}
