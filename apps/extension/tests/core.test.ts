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

function optionalField(label: string): PageField {
  return { ...field(label), required: false };
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

  it("maps abbreviated education and internship labels even when one page contains several sections", () => {
    const detailedProfile = { ...profile, identity: { ...profile.identity, id_number: "110101200001010011" }, education: [{ id: "edu", school_name: "北京大学", department: "计算机学院", education_level: "master", major: "计算机" , start_date: "2023-09", end_date: "2026-06" }], experiences: [{ id: "exp", experience_type: "internship", org_name: "字节跳动", title: "算法实习生", start_date: "2025-06", end_date: "2025-09" }] };
    const plan = mapFields([field("身份证"), field("学院名称"), field("结束时间"), field("单位名称"), field("职位名称")], detailedProfile);
    expect(plan.map((item) => item.proposedValue)).toEqual(["110101200001010011", "计算机学院", "2026-06", "字节跳动", "算法实习生"]);
    expect(plan.every((item) => item.decision === "fill")).toBe(true);
  });

  it("maps project fields from the latest project record", () => {
    const projectProfile = { ...profile, projects: [{ id: "old", project_name: "旧项目", role: "开发者", start_date: "2024-01", end_date: "2024-06", summary: "旧简介", description_bullets: ["旧内容"] }, { id: "new", project_name: "ApplyPilot", role: "核心开发者", start_date: "2026-01", end_date: "2026-06", summary: "网申助手", description_bullets: ["设计字段映射", "实现浏览器插件"] }] };
    const plan = mapFields([field("项目名称"), field("项目角色"), field("项目简介"), field("项目描述"), field("开始日期"), field("结束日期")], projectProfile, "项目经历");
    expect(plan.map((item) => item.proposedValue)).toEqual(["ApplyPilot", "核心开发者", "网申助手", "设计字段映射\n实现浏览器插件", "2026-01", "2026-06"]);
    expect(plan.every((item) => item.decision === "fill")).toBe(true);
  });

  it("never overwrites an existing value and explains missing mappings", () => {
    const plan = mapFields([field("姓名", "用户已填写"), field("自定义问题")], profile);
    expect(plan[0]).toMatchObject({ decision: "skip", reason: "已有内容，已保留" });
    expect(plan[1]).toMatchObject({ decision: "review" });
  });

  it("leaves empty optional fields untouched", () => {
    expect(mapFields([optionalField("姓名")], profile)[0]).toMatchObject({ decision: "skip", reason: "选填项，按要求留空" });
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

  it("assigns successive blank internship rows to successive profile records", () => {
    const experienceProfile = { ...profile, experiences: [{ id: "new", experience_type: "internship", org_name: "新东方", title: "AI 算法实习生", start_date: "2026-05", end_date: "2026-09", description_bullets: ["新经历"] }, { id: "old", experience_type: "internship", org_name: "高德地图", title: "应用算法实习生", start_date: "2025-10", end_date: "2026-02", description_bullets: ["旧经历"] }] };
    const plan = mapFields([field("单位名称"), field("职位名称"), field("实习内容"), field("单位名称"), field("职位名称"), field("实习内容")], experienceProfile, "个人信息");
    expect(plan.map((item) => item.proposedValue)).toEqual(["新东方", "AI 算法实习生", "新经历", "高德地图", "应用算法实习生", "旧经历"]);
    expect(plan.map((item) => item.profilePath)).toEqual(["experiences[0].org_name", "experiences[0].title", "experiences[0].description_bullets", "experiences[1].org_name", "experiences[1].title", "experiences[1].description_bullets"]);
  });

  it("does not repeat an internship already present in an existing row", () => {
    const experienceProfile = { ...profile, experiences: [{ id: "new", experience_type: "internship", org_name: "新东方", title: "AI 算法实习生", start_date: "2026-05", end_date: "2026-09" }, { id: "old", experience_type: "internship", org_name: "高德地图", title: "应用算法实习生", start_date: "2025-10", end_date: "2026-02" }] };
    const plan = mapFields([field("单位名称", "新东方"), field("职位名称", "AI 算法实习生"), field("单位名称"), field("职位名称")], experienceProfile, "个人信息");
    expect(plan.slice(2).map((item) => item.proposedValue)).toEqual(["高德地图", "应用算法实习生"]);
    expect(plan[2].profilePath).toBe("experiences[1].org_name");
  });

  it("leaves a new internship row for manual entry when every profile record is already used", () => {
    const experienceProfile = { ...profile, experiences: [{ id: "new", experience_type: "internship", org_name: "新东方", title: "AI 算法实习生", start_date: "2026-05", end_date: "2026-09" }] };
    const plan = mapFields([field("单位名称", "新东方"), field("单位名称")], experienceProfile, "个人信息");
    expect(plan[1]).toMatchObject({ decision: "review", profilePath: "experiences[1].org_name" });
  });

  it("maps awards and publication fields from structured profile arrays", () => {
    const structuredProfile = { ...profile, awards: [{ id: "a1", name: "一等学业奖学金", date: "2025-2026", description: "硕士阶段" }, { id: "a2", name: "国家励志奖学金", date: "2022-2024" }], publications: [{ id: "p1", title: "NAS 2026", venue: "CCF-C", status: "已录用", description: "NAS 2026（CCF-C，已录用）" }] };
    const awards = mapFields([field("获奖项"), field("获奖描述")], structuredProfile, "获奖情况");
    const publications = mapFields([field("名称"), field("成果描述"), field("发表刊物")], structuredProfile, "论文/专著");
    expect(awards.map((item) => item.proposedValue)).toEqual(["一等学业奖学金", "硕士阶段"]);
    expect(publications.map((item) => item.proposedValue)).toEqual(["NAS 2026", "NAS 2026（CCF-C，已录用）", "CCF-C"]);
    expect([...awards, ...publications].every((item) => item.decision === "fill")).toBe(true);
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

  it("maps newly added SOE extended fields and custom_fields", () => {
    const soeProfile = {
      ...profile,
      identity: { ...profile.identity, birth_place: "北京市海淀区", id_expiry_date: "2035-10-01" },
      contact: { ...profile.contact, postal_code: "100084", home_phone: "010-12345678" },
      soe_extended: {
        height_cm: 180,
        household_type: "城镇居民",
        driving_license: "C1",
        personal_statement: "踏实认真，学习能力强",
        can_relocate: "yes",
        custom_fields: {
          "是否近视": "否",
          "期望职级": "中级",
        },
      },
    };
    const plan = mapFields([
      field("出生地"),
      field("证件有效期"),
      field("邮编"),
      field("家庭电话"),
      field("身高"),
      field("户口类型"),
      field("驾照类型"),
      field("自我评价"),
      field("是否服从分配"),
      field("是否近视"),
      field("期望职级"),
    ], soeProfile);

    expect(plan.map((item) => item.proposedValue)).toEqual([
      "北京市海淀区",
      "2035-10-01",
      "100084",
      "010-12345678",
      "180",
      "城镇居民",
      "C1",
      "踏实认真，学习能力强",
      "yes",
      "否",
      "中级",
    ]);
    expect(plan.every((item) => item.decision === "fill")).toBe(true);
  });

  it("strictly isolates emergency contact name from candidate identity name", () => {
    const candidateProfile = {
      ...profile,
      identity: { ...profile.identity, name: "金泽凯" },
      contact: {
        ...profile.contact,
        mobile: "13800138000",
        emergency_contact_name: "张父",
        emergency_contact_phone: "13900139000",
        emergency_contact_relation: "父亲",
      },
    };

    const plan = mapFields([
      field("姓名"),
      field("紧急联系人姓名"),
      field("紧急联系方式"),
      field("紧急联系人电话"),
      field("紧急联系电话"),
      field("紧急联系人关系"),
      field("与本人关系"),
    ], candidateProfile);

    expect(plan[0].proposedValue).toBe("金泽凯");
    expect(plan[0].profilePath).toBe("identity.name");

    // Must NEVER be candidate's name!
    expect(plan[1].proposedValue).toBe("张父");
    expect(plan[1].profilePath).toBe("contact.emergency_contact_name");

    expect(plan[2].proposedValue).toBe("13900139000");
    expect(plan[2].profilePath).toBe("contact.emergency_contact_phone");

    expect(plan[3].proposedValue).toBe("13900139000");
    expect(plan[3].profilePath).toBe("contact.emergency_contact_phone");

    expect(plan[4].proposedValue).toBe("13900139000");
    expect(plan[4].profilePath).toBe("contact.emergency_contact_phone");

    expect(plan[5].proposedValue).toBe("父亲");
    expect(plan[5].profilePath).toBe("contact.emergency_contact_relation");

    expect(plan[6].proposedValue).toBe("父亲");
    expect(plan[6].profilePath).toBe("contact.emergency_contact_relation");
  });

  it("matches political status dropdown options to full names when available", () => {
    const candidateProfile = {
      ...profile,
      soe_extended: {
        political_status: "共青团员",
      },
    };

    const selectField: PageField = {
      ref: "political-select",
      label: "政治面貌",
      name: "politicalStatus",
      kind: "select",
      required: true,
      value: "",
      options: [
        "--请选择--",
        "中国共产党党员",
        "中国共产党预备党员",
        "中国共产主义青年团团员",
        "群众",
      ],
    };

    const plan = mapFields([selectField], candidateProfile);
    expect(plan[0].decision).toBe("fill");
    expect(plan[0].proposedValue).toBe("中国共产主义青年团团员");
  });

  it("handles compound fields for ID number and mobile country code", () => {
    const candidateProfile = {
      ...profile,
      identity: {
        ...profile.identity,
        id_type: "身份证",
        id_number: "110101199003072345",
      },
      contact: {
        ...profile.contact,
        mobile: "13800138000",
      },
    };

    const idTypeSelect: PageField = {
      ref: "id-type",
      label: "身份证号",
      name: "idType",
      kind: "select",
      required: true,
      value: "",
      options: ["国内身份证或护照（含港澳台）", "国外身份证"],
    };
    const idNumberText: PageField = {
      ref: "id-number",
      label: "身份证号",
      name: "idNumber",
      kind: "text",
      required: true,
      value: "",
      options: [],
    };
    const countryCodeSelect: PageField = {
      ref: "country-code",
      label: "手机号码",
      name: "countryCode",
      kind: "select",
      required: true,
      value: "",
      options: ["中国大陆（+86）", "其他地区手机号"],
    };
    const mobileText: PageField = {
      ref: "mobile-input",
      label: "手机号码",
      name: "mobile",
      kind: "text",
      required: true,
      value: "",
      options: [],
    };

    const plan = mapFields([idTypeSelect, idNumberText, countryCodeSelect, mobileText], candidateProfile);
    expect(plan.map((item) => item.proposedValue)).toEqual([
      "国内身份证或护照（含港澳台）",
      "110101199003072345",
      "中国大陆（+86）",
      "13800138000",
    ]);
  });

  it("maps cascading selects for native place location", () => {
    const candidateProfile = {
      ...profile,
      soe_extended: {
        native_place: "北京市东城区",
      },
    };

    const provSelect: PageField = {
      ref: "prov",
      label: "籍贯",
      name: "prov",
      kind: "select",
      required: true,
      value: "",
      options: ["北京", "天津", "河北", "湖北"],
    };
    const citySelect: PageField = {
      ref: "city",
      label: "籍贯",
      name: "city",
      kind: "select",
      required: true,
      value: "",
      options: ["北京市东城区", "北京市西城区", "北京市海淀区"],
    };

    const plan = mapFields([provSelect, citySelect], candidateProfile);
    expect(plan.map((item) => item.proposedValue)).toEqual([
      "北京",
      "北京市东城区",
    ]);
  });

  it("maps split date of birth dropdowns to birth year and month, strictly avoiding graduation year", () => {
    const candidateProfile = {
      ...profile,
      identity: {
        ...profile.identity,
        birth_date: "2001-05-15",
      },
      campus_context: {
        graduation_year: 2028,
        graduation_month: 1,
      },
    };

    const birthYearSelect: PageField = {
      ref: "byear",
      label: "出生年份",
      name: "birthYear",
      kind: "select",
      required: true,
      value: "",
      options: ["2028年", "2027年", "2001年", "2000年"],
    };
    const birthMonthSelect: PageField = {
      ref: "bmonth",
      label: "出生月份",
      name: "birthMonth",
      kind: "select",
      required: true,
      value: "",
      options: ["01月", "02月", "05月", "12月"],
    };

    const plan = mapFields([birthYearSelect, birthMonthSelect], candidateProfile);
    expect(plan.map((item) => item.proposedValue)).toEqual([
      "2001年",
      "05月",
    ]);
    expect(plan.every((item) => item.decision === "fill")).toBe(true);
  });

  it("cascades birth date across multiple selects when label is general 出生日期", () => {
    const candidateProfile = {
      ...profile,
      identity: {
        ...profile.identity,
        birth_date: "2001-05-15",
      },
      campus_context: {
        graduation_year: 2028,
      },
    };

    const select1: PageField = {
      ref: "s1",
      label: "出生日期",
      name: "year",
      kind: "select",
      required: true,
      value: "",
      options: ["2028", "2001", "2000"],
    };
    const select2: PageField = {
      ref: "s2",
      label: "出生日期",
      name: "month",
      kind: "select",
      required: true,
      value: "",
      options: ["01", "05", "12"],
    };

    const plan = mapFields([select1, select2], candidateProfile);
    expect(plan.map((item) => item.proposedValue)).toEqual([
      "2001",
      "05",
    ]);
  });
});
