import { describe, expect, it } from "vitest";
import { applyApiPlan, isLoopbackEndpoint, isModelProviderEndpoint, normalizeApplyPilotEndpoint, validateApplyPilotEndpoint } from "../runtime/api";
import type { PageScan } from "../runtime/page";

const scan: PageScan = {
  url: "https://example.com/form",
  title: "填写申请",
  fields: [
    { ref: "ap-1", frameId: 0, label: "姓名", name: "name", type: "text", kind: "text", required: true, value: "", options: [] },
    { ref: "ap-2", frameId: 1, label: "单位名称", name: "org", type: "text", kind: "text", required: true, value: "", options: [], section: "实习经历", recordGroup: "实习经历:row-1" },
  ],
  sections: [],
  documentReady: true,
  pageState: "form",
  embeddedFrameCount: 1,
};

describe("local mapping API client", () => {
  it("allows loopback API endpoints and rejects public endpoints by default", () => {
    expect(isLoopbackEndpoint("http://127.0.0.1:8765")).toBe(true);
    expect(isLoopbackEndpoint("http://localhost:8765")).toBe(true);
    expect(isLoopbackEndpoint("https://api.example.com")).toBe(false);
  });

  it("distinguishes a model provider endpoint from the ApplyPilot planning service", () => {
    expect(isModelProviderEndpoint("https://api.deepseek.com/v1")).toBe(true);
    expect(validateApplyPilotEndpoint("https://api.deepseek.com/v1", true)).toMatch(/不是 DeepSeek\/OpenAI 模型地址/);
    expect(validateApplyPilotEndpoint("http://127.0.0.1:8765")).toBeUndefined();
    expect(validateApplyPilotEndpoint("https://applypilot.example.com", false)).toMatch(/远程 ApplyPilot 服务默认关闭/);
    expect(validateApplyPilotEndpoint("https://applypilot.example.com", true)).toBeUndefined();
    expect(normalizeApplyPilotEndpoint("http://127.0.0.1:8765/v1/")).toBe("http://127.0.0.1:8765");
  });

  it("joins API plan items back to frame-aware scanned fields", () => {
    const result = applyApiPlan(scan, {
      request_id: "req_test",
      mapping_version: "rules-test",
      profile_hash: "sha256:test",
      plan: [
        { field_ref: "0:ap-1", decision: "fill", required: true, value: "张三", profile_path: "/identity/name", confidence: 1, method: "rule", reason: "来源" },
        { field_ref: "1:ap-2", decision: "review", required: true, value: "高德地图", profile_path: "/experiences/1/org_name", record_id: "exp_old", confidence: 1, method: "rule", reason: "人工确认" },
      ],
      summary: { fields: 2, fill: 1, review: 1, optional_skipped: 0, existing_skipped: 0 },
      warnings: [],
    });
    expect(result.map((item) => [item.field.frameId, item.field.label, item.proposedValue, item.profilePath])).toEqual([[0, "姓名", "张三", "/identity/name"], [1, "单位名称", "高德地图", "/experiences/1/org_name"]]);
  });

  it("drops stale plan items so the caller can force local fallback", () => {
    const result = applyApiPlan(scan, {
      request_id: "req_stale",
      mapping_version: "rules-test",
      profile_hash: "sha256:test",
      plan: [{ field_ref: "0:missing", decision: "fill", required: true, value: "错误", confidence: 1, method: "rule", reason: "过期" }],
      summary: { fields: 1, fill: 1, review: 0, optional_skipped: 0, existing_skipped: 0 },
      warnings: [],
    });
    expect(result).toEqual([]);
  });
});
