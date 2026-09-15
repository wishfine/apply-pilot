import type { CandidateProfile, FieldPlan } from "../../../packages/core/src/index";
import type { PageScan } from "./page";

export const DEFAULT_API_ENDPOINT = "http://127.0.0.1:8765";

export function isLoopbackEndpoint(endpoint: string): boolean {
  try {
    const hostname = new URL(endpoint).hostname;
    return ["localhost", "127.0.0.1", "[::1]", "::1"].includes(hostname);
  } catch {
    return false;
  }
}

/** Returns true for vendor model endpoints that cannot serve ApplyPilot's form-plan route. */
export function isModelProviderEndpoint(endpoint: string): boolean {
  try {
    const hostname = new URL(endpoint).hostname.toLowerCase();
    return hostname === "api.deepseek.com" || hostname === "api.openai.com" || hostname.endsWith(".openai.azure.com");
  } catch {
    return false;
  }
}

export function validateApplyPilotEndpoint(endpoint: string, allowRemote = false): string | undefined {
  let parsed: URL;
  try {
    parsed = new URL(endpoint);
  } catch {
    return "ApplyPilot 服务地址必须是有效的 http:// 或 https:// 地址";
  }
  if (!/^https?:$/.test(parsed.protocol)) return "ApplyPilot 服务地址必须使用 http:// 或 https://";
  if (isModelProviderEndpoint(endpoint)) {
    return "这里需要填写 ApplyPilot 服务地址，不是 DeepSeek/OpenAI 模型地址。请填 http://127.0.0.1:8765；模型地址请在 API 服务端配置 APPLYPILOT_LLM_BASE_URL。";
  }
  if (!isLoopbackEndpoint(endpoint) && !allowRemote) return "远程 ApplyPilot 服务默认关闭；如确认服务可信，请勾选远程处理后再保存";
  return undefined;
}

export function normalizeApplyPilotEndpoint(endpoint: string): string {
  const parsed = new URL(endpoint);
  parsed.pathname = parsed.pathname.replace(/\/v1\/?$/, "") || "/";
  return parsed.toString().replace(/\/$/, "");
}

type ApiPlanItem = {
  field_ref: string;
  decision: "fill" | "review" | "skip";
  required: boolean;
  value?: string | null;
  profile_path?: string | null;
  record_id?: string | null;
  confidence: number;
  method: string;
  reason: string;
};

export type ApiPlanResponse = {
  request_id: string;
  mapping_version: string;
  profile_hash: string;
  plan: ApiPlanItem[];
  summary: { fields: number; fill: number; review: number; optional_skipped: number; existing_skipped: number };
  warnings: string[];
};

export async function requestFormPlan(endpoint: string, profile: CandidateProfile, scan: PageScan, token?: string, allowRemote = false): Promise<ApiPlanResponse> {
  const validationError = validateApplyPilotEndpoint(endpoint, allowRemote);
  if (validationError) throw new Error(validationError);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 4000);
  try {
    const response = await fetch(`${normalizeApplyPilotEndpoint(endpoint)}/v1/forms/plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({
        protocol_version: "1.0",
        profile,
        page: {
          url_origin: new URL(scan.url).origin,
          title: scan.title,
          platform_hint: /51job/i.test(scan.url) ? "51job" : /zhiye\.com/i.test(scan.url) ? "zhiye" : "generic",
          active_section: scan.activeSection,
          sections: scan.sections.map((section) => ({ id: section.ref, label: section.label, active: section.active })),
          fields: scan.fields.map((field) => ({ field_ref: `${field.frameId ?? 0}:${field.ref}`, frame_id: field.frameId ?? 0, label: field.label, name: field.name, section: field.section, record_group: field.recordGroup, kind: field.kind, type: field.type, required: field.required, value: field.value, options: field.options })),
        },
        policy: { fill_required_only: true, allow_sensitive_paths: ["identity.id_number", "soe_extended.native_place", "contact.qq"], allow_remote_processing: !isLoopbackEndpoint(endpoint) },
      }),
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`API 返回 ${response.status}`);
    return await response.json() as ApiPlanResponse;
  } finally {
    window.clearTimeout(timeout);
  }
}

export function applyApiPlan(scan: PageScan, response: ApiPlanResponse): FieldPlan[] {
  const fields = new Map(scan.fields.map((field) => [`${field.frameId ?? 0}:${field.ref}`, field]));
  const plan: FieldPlan[] = [];
  response.plan.forEach((item) => {
    const field = fields.get(item.field_ref);
    if (field) plan.push({ field, decision: item.decision, profilePath: item.profile_path || undefined, proposedValue: item.value || undefined, reason: item.reason });
  });
  return plan;
}
