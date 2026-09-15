import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parse as parseYaml } from "yaml";
import { mapFields, parseCandidateProfile, type PageField } from "../../../packages/core/src/index";

const profile = parseCandidateProfile({
  profile_id: "candidate-test",
  identity: { name: "张三", gender: "男" },
  contact: { mobile: "13800000000", email: "z@example.com" },
  education: [
    { id: "edu_bachelor", school_name: "本科大学", education_level: "bachelor", major: "计算机科学", start_date: { year: 2018 }, end_date: { year: 2022 } },
    { id: "edu_master", school_name: "硕士大学", education_level: "master", major: "软件工程", start_date: { year: 2022 }, end_date: { year: 2025 } },
  ],
});

function field(label: string, value = ""): PageField {
  return { ref: `ref-${label}`, label, name: label, kind: "text", required: true, value, options: [] };
}

describe("extension field planning", () => {
  it("maps Chinese labels and chooses the highest education record", () => {
    const plan = mapFields([field("姓名"), field("手机号码"), field("毕业院校"), field("专业")], profile);
    expect(plan.map((item) => item.proposedValue)).toEqual(["张三", "13800000000", "硕士大学", "软件工程"]);
    expect(plan.every((item) => item.decision === "fill")).toBe(true);
  });

  it("maps common personal labels used by enterprise recruitment forms", () => {
    const detailedProfile = { ...profile, identity: { ...profile.identity, id_number: "110101200001010011", nationality: "中国" }, contact: { ...profile.contact, current_city: "武汉市", qq: "10001", wechat: "zhangsan" }, soe_extended: { native_place: "湖北省武汉市", household_registration: "湖北省武汉市" } };
    const plan = mapFields([field("证件号码"), field("国籍/地区"), field("籍贯"), field("现居住地"), field("QQ"), field("微信号")], detailedProfile);
    expect(plan.map((item) => item.proposedValue)).toEqual(["110101200001010011", "中国", "湖北省武汉市", "武汉市", "10001", "zhangsan"]);
    expect(plan.every((item) => item.decision === "fill")).toBe(true);
  });

  it("never overwrites an existing value and explains missing mappings", () => {
    const plan = mapFields([field("姓名", "用户已填写"), field("自定义问题")], profile);
    expect(plan[0]).toMatchObject({ decision: "skip", reason: "已有内容，已保留" });
    expect(plan[1]).toMatchObject({ decision: "review" });
  });

  it("does not guess radio or checkbox state", () => {
    const choice = { ...field("性别"), kind: "choice" };
    expect(mapFields([choice], profile)[0]).toMatchObject({ decision: "review", reason: "选择控件需要确认具体选项" });
  });

  it("maps the active internship section to the most recent internship", () => {
    const experienceProfile = { ...profile, experiences: [{ id: "old", experience_type: "internship", org_name: "旧公司", title: "实习生", start_date: "2024-01", end_date: "2024-06", description_bullets: ["旧经历"] }, { id: "new", experience_type: "internship", org_name: "新东方教育科技集团", title: "AI 算法实习生", start_date: "2026-05", end_date: "2026-09", description_bullets: ["算法建模"] }] };
    const plan = mapFields([field("公司名称"), field("职位"), field("工作内容")], experienceProfile, "实习经历");
    expect(plan.map((item) => item.proposedValue)).toEqual(["新东方教育科技集团", "AI 算法实习生", "算法建模"]);
    expect(plan.every((item) => item.decision === "fill")).toBe(true);
  });

  it("rejects malformed profile data before writing it to storage", () => {
    expect(() => parseCandidateProfile({ identity: {} })).toThrow("profile_id");
    expect(() => parseCandidateProfile({ profile_id: "x", education: {} })).toThrow("education");
    expect(() => parseCandidateProfile({ profile_id: "x", education: ["bad"] })).toThrow("每一项");
  });

  it("accepts the repository profile example as an import", () => {
    const path = fileURLToPath(new URL("../../../examples/profile.example.yaml", import.meta.url));
    const imported = parseCandidateProfile(parseYaml(readFileSync(path, "utf8")));
    expect(imported.profile_id).toBe("cand_zhangsan_2026");
    expect(imported.education?.length).toBeGreaterThan(0);
  });
});
