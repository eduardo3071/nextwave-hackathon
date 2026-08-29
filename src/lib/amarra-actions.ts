import { toast } from "sonner";
import { backendUrl } from "./backend";

/**
 * POSTs to the Amarra FastAPI backend. Never swallows a failure: the response
 * body is shown verbatim, because the backend always answers with a readable
 * sentence (409 = a phase guard refused, which is expected).
 */
export async function callBackend(
  path: string,
  body?: unknown,
  okMessage?: string,
): Promise<boolean> {
  if (!backendUrl) {
    toast.error("VITE_BACKEND_URL não está configurado");
    return false;
  }
  try {
    const res = await fetch(`${backendUrl}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const text = await res.text();
    if (!res.ok) {
      let reason = text;
      try {
        const parsed = JSON.parse(text) as Record<string, unknown>;
        const detail = parsed["detail"] ?? parsed["reason"] ?? parsed["error"];
        if (detail) reason = typeof detail === "string" ? detail : JSON.stringify(detail);
      } catch {
        /* body was not JSON; show it raw */
      }
      toast.error(`${res.status} · ${reason || "sem corpo na resposta"}`);
      return false;
    }
    if (okMessage) toast.success(okMessage);
    return true;
  } catch (e) {
    toast.error(`Backend inacessível: ${String(e)}`);
    return false;
  }
}
