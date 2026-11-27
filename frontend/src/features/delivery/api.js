export async function request(path, method = "GET", body) {
  const response = await fetch(path, {
    method, credentials: "same-origin", cache: "no-store",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body && JSON.stringify(body),
  });
  const value = await response.json();
  if (!response.ok) {
    const detail = value.detail ?? value;
    throw Object.assign(new Error(detail.code ?? "Request failed"), { status: response.status, detail });
  }
  return value;
}
