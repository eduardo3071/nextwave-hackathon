export const backendUrl = (
  (import.meta.env["VITE_BACKEND_URL"] as string | undefined) ||
  (import.meta.env["BACKEND_URL"] as string | undefined)
)?.replace(/\/$/, "");
