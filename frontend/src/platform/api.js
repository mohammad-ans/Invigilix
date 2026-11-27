export async function api(path, method = "GET", body, csv = false) {
  let response;
  try {
    response = await fetch("/api" + path, {
      method, credentials: "same-origin", cache: "no-store",
      headers: { Accept: "application/json", ...(body === undefined ? {} : { "Content-Type": csv ? "text/csv" : "application/json" }) },
      body: body === undefined ? undefined : csv ? body : JSON.stringify(body),
    });
  } catch {
    throw Object.assign(new Error("The examination office could not be reached. Check your connection and retry."), { offline: true });
  }
  if (response.status === 204) return;
  const data = await response.json().catch(() => null);
  if (!response.ok || data === null) {
    const message = data?.error?.message || (typeof data?.detail === "string" && data.detail) || "The office could not complete this request.";
    throw Object.assign(new Error(message), { status: response.status, issues: data?.error?.issues });
  }
  return data;
}
