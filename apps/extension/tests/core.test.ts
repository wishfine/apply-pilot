import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parse as parseYaml } from "yaml";
import { applyHarvestedFields, formatDateWithFieldClues, harvestPageFields, mapFields, parseCandidateProfile, type PageField } from "../../../packages/core/src/index";

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

  describe("multi-format and custom variant adaptation", () => {
    it("adapts date formats dynamically according to field types and placeholders", () => {
      // YYYY-MM input with YYYY-MM-DD in profile
      const monthField: PageField = {
        ref: "m1",
        label: "毕业时间",
        name: "gradMonth",
        kind: "text",
        type: "month",
        required: true,
        value: "",
        options: [],
      };
      expect(formatDateWithFieldClues("2024-06-30", monthField)).toBe("2024-06");

      // HTML5 date input with YYYY-MM in profile
      const dateField: PageField = {
        ref: "d1",
        label: "出生日期",
        name: "birthDate",
        kind: "text",
        type: "date",
        required: true,
        value: "",
        options: [],
      };
      expect(formatDateWithFieldClues("2001-05", dateField)).toBe("2001-05-01");

      // Slash placeholder
      const slashField: PageField = {
        ref: "s1",
        label: "入学时间",
        name: "startDate",
        kind: "text",
        type: "text",
        required: true,
        value: "",
        options: [],
      };
      expect(formatDateWithFieldClues("2020-09-01", { ...slashField, name: "YYYY/MM" })).toBe("2020/09");
      expect(formatDateWithFieldClues("2020-09-01", { ...slashField, label: "入学年月(YYYY.MM)" })).toBe("2020.09");
      expect(formatDateWithFieldClues("2020-09-01", { ...slashField, label: "入学年月(YYYY年MM月)" })).toBe("2020年09月");
    });

    it("matches custom variants configured by candidate in profile", () => {
      const variantProfile = {
        ...profile,
        soe_extended: {
          political_status: "团员",
        },
        custom_variants: {
          political_status: ["共青团员", "中国共产主义青年团团员", "共青团"],
        },
      };

      const selectField: PageField = {
        ref: "pol-1",
        label: "政治面貌",
        name: "politicalStatus",
        kind: "select",
        required: true,
        value: "",
        options: ["请选择", "中国共产主义青年团团员", "群众"],
      };

      const plan = mapFields([selectField], variantProfile);
      expect(plan[0].decision).toBe("fill");
      expect(plan[0].proposedValue).toBe("中国共产主义青年团团员");
    });
  });

  describe("reverse harvesting and profile enrichment", () => {
    it("harvests standard and custom fields from scanned page", () => {
      const scannedFields: PageField[] = [
        {
          ref: "f1",
          label: "姓名",
          name: "name",
          kind: "text",
          type: "text",
          required: true,
          value: "张三",
          options: [],
        },
        {
          ref: "f2",
          label: "紧急联系人电话",
          name: "emergencyPhone",
          kind: "text",
          type: "text",
          required: true,
          value: "13900139000",
          options: [],
        },
        {
          ref: "f3",
          label: "期望薪资",
          name: "salary",
          kind: "text",
          type: "text",
          required: true,
          value: "15000-20000",
          options: [],
        },
        {
          ref: "f4",
          label: "特殊体貌特征",
          name: "appearance",
          kind: "text",
          type: "text",
          required: false,
          value: "无",
          options: [],
        },
      ];

      const harvested = harvestPageFields(scannedFields, profile);
      // '姓名' is already in profile ("张三"), so it's not a new/updated field and skipped
      expect(harvested.some((h) => h.label === "姓名")).toBe(false);

      // '紧急联系人电话' should be recognized as standard field
      const emergencyItem = harvested.find((h) => h.label === "紧急联系人电话");
      expect(emergencyItem).toBeDefined();
      expect(emergencyItem?.category).toBe("standard");
      expect(emergencyItem?.inferredPath).toBe("contact.emergency_contact_phone");
      expect(emergencyItem?.value).toBe("13900139000");

      // '期望薪资' should be recognized as standard soe_extended field
      const salaryItem = harvested.find((h) => h.label === "期望薪资");
      expect(salaryItem).toBeDefined();
      expect(salaryItem?.inferredPath).toBe("soe_extended.expected_salary");

      // '特殊体貌特征' is not in standard schema, so it goes to custom_fields
      const customItem = harvested.find((h) => h.label === "特殊体貌特征");
      expect(customItem).toBeDefined();
      expect(customItem?.category).toBe("custom");
      expect(customItem?.inferredPath).toBe('soe_extended.custom_fields["特殊体貌特征"]');
      expect(customItem?.value).toBe("无");
    });

    it("applies harvested fields to enrich profile without mutating original", () => {
      const scannedFields: PageField[] = [
        {
          ref: "f2",
          label: "紧急联系人电话",
          name: "emergencyPhone",
          kind: "text",
          type: "text",
          required: true,
          value: "13900139000",
          options: [],
        },
        {
          ref: "f4",
          label: "特殊体貌特征",
          name: "appearance",
          kind: "text",
          type: "text",
          required: false,
          value: "无",
          options: [],
        },
      ];

      const harvested = harvestPageFields(scannedFields, profile);
      const updated = applyHarvestedFields(profile, harvested);

      // Verify immutability
      expect(profile.contact?.emergency_contact_phone).toBeUndefined();

      // Verify updated profile has new fields
      expect(updated.contact?.emergency_contact_phone).toBe("13900139000");
      expect((updated.soe_extended?.custom_fields as Record<string, unknown>)?.[`特殊体貌特征`]).toBe("无");
    });

    it("does not skip fields whose initial value is placeholder dashes or text like '----' or '--'", () => {
      const candidateProfile = {
        ...profile,
        identity: {
          ...profile.identity,
          birth_date: "2001-05-15",
        },
      };

      const fields: PageField[] = [
        {
          ref: "byear",
          label: "出生年份",
          name: "birthYear",
          kind: "select",
          type: "select",
          required: true,
          value: "----",
          options: ["----", "2002", "2001", "2000"],
        },
        {
          ref: "bmonth",
          label: "出生月份",
          name: "birthMonth",
          kind: "select",
          type: "select",
          required: true,
          value: "--",
          options: ["--", "04", "05", "06"],
        },
      ];

      const plan = mapFields(fields, candidateProfile);
      expect(plan[0].decision).toBe("fill");
      expect(plan[0].proposedValue).toBe("2001");
      expect(plan[1].decision).toBe("fill");
      expect(plan[1].proposedValue).toBe("05");
    });

    it("correctly maps level-specific education fields for bachelor and high school", () => {
      const candidateProfile = {
        ...profile,
        education: [
          {
            id: "edu-master",
            school_name: "清华大学",
            education_level: "master",
            academic_degree: "硕士",
            major: "计算机科学与技术",
            department: "计算机系",
            start_date: "2023-09",
            end_date: "2026-06",
          },
          {
            id: "edu-bachelor",
            school_name: "北京大学",
            education_level: "bachelor",
            academic_degree: "学士",
            major: "软件工程",
            department: "信息工程学院",
            start_date: "2019-09",
            end_date: "2023-06",
          },
          {
            id: "edu-hs",
            school_name: "衡水中学",
            education_level: "high_school",
            start_date: "2016-09",
            end_date: "2019-06",
          },
        ],
      };

      const fields: PageField[] = [
        { ref: "f1", label: "本科学校名称", name: "bSchool", kind: "text", type: "text", required: true, value: "", options: [] },
        { ref: "f2", label: "本科专业", name: "bMajor", kind: "text", type: "text", required: true, value: "", options: [] },
        { ref: "f3", label: "本科入学时间", name: "bStart", kind: "text", type: "text", required: true, value: "", options: [] },
        { ref: "f4", label: "本科毕业时间", name: "bEnd", kind: "text", type: "text", required: true, value: "", options: [] },
        { ref: "f5", label: "高中毕业学校", name: "hSchool", kind: "text", type: "text", required: true, value: "", options: [] },
        { ref: "f6", label: "高中开始时间", name: "hStart", kind: "text", type: "text", required: true, value: "", options: [] },
      ];

      const plan = mapFields(fields, candidateProfile);
      expect(plan[0].proposedValue).toBe("北京大学");
      expect(plan[1].proposedValue).toBe("软件工程");
      expect(plan[2].proposedValue).toBe("2019-09");
      expect(plan[3].proposedValue).toBe("2023-06");
      expect(plan[4].proposedValue).toBe("衡水中学");
      expect(plan[5].proposedValue).toBe("2016-09");
      expect(plan.every((item) => item.decision === "fill")).toBe(true);
    });

    it("auto-migrates rogue education[bachelor] root keys into profile.education array", () => {
      const legacyRaw = {
        profile_id: "test-legacy",
        education: [
          { id: "edu_master", school_name: "清华大学", education_level: "master", major: "自动化" },
        ],
        "education[bachelor]": {
          school_name: "北京工业大学",
          major: "计算机科学与技术",
          start_date: "2020-09-01",
          end_date: "2024-07-01",
        },
        "education[high_school]": {
          school_name: "密云二中",
          start_date: "2017-09-01",
          end_date: "2020-07-01",
        },
      };

      const parsed = parseCandidateProfile(legacyRaw);
      expect(parsed.education).toHaveLength(3);
      const bachelor = parsed.education!.find((e) => e.education_level === "bachelor");
      expect(bachelor).toBeDefined();
      expect(bachelor?.school_name).toBe("北京工业大学");
      expect(bachelor?.major).toBe("计算机科学与技术");
      expect(bachelor?.start_date).toBe("2020-09-01");
      expect((parsed as any)["education[bachelor]"]).toBeUndefined();
    });

    it("matches dropdown options via custom_variants when direct value does not match", () => {
      const candidateProfile: any = {
        ...profile,
        education: [
          {
            id: "edu_bachelor",
            school_name: "北京工业大学",
            education_level: "bachelor",
            major: "计算机科学与技术",
          },
        ],
        custom_variants: {
          major: ["计算机科学与技术", "计算机类/计算机科学与技术"],
          school_name: ["北京工业大学", "北京/北京工业大学"],
        },
      };

      const fields: PageField[] = [
        {
          ref: "major_select",
          label: "本科专业",
          name: "major",
          kind: "select",
          required: true,
          value: "",
          options: ["--请选择--", "软件工程", "网络空间安全", "计算机类/计算机科学与技术", "电子信息工程"],
        },
        {
          ref: "school_select",
          label: "毕业院校",
          name: "school",
          kind: "select",
          required: true,
          value: "",
          options: ["--请选择--", "北京/北京大学", "北京/清华大学", "北京/北京工业大学"],
        },
      ];

      const plan = mapFields(fields, candidateProfile);
      expect(plan[0].decision).toBe("fill");
      expect(plan[0].proposedValue).toBe("计算机类/计算机科学与技术");
      expect(plan[1].decision).toBe("fill");
      expect(plan[1].proposedValue).toBe("北京/北京工业大学");
    });

    it("defaults recruitment date inputs to YYYY-MM-DD", () => {
      const dateField: PageField = {
        ref: "d1",
        label: "入学日期",
        name: "startDate",
        kind: "text",
        type: "date",
        required: true,
        value: "",
        options: [],
      };

      expect(formatDateWithFieldClues("2024-09", dateField)).toBe("2024-09-01");
      expect(formatDateWithFieldClues("2024-09-01", { ...dateField, type: "text" })).toBe("2024-09-01");
      expect(formatDateWithFieldClues("2024-09-15", { ...dateField, type: "text" })).toBe("2024-09-15");

      const monthOnlyField: PageField = {
        ...dateField,
        type: "text",
        label: "入学年月 (YYYY-MM)",
      };
      expect(formatDateWithFieldClues("2024-09-01", monthOnlyField)).toBe("2024-09");
      expect(formatDateWithFieldClues("2024-09", monthOnlyField)).toBe("2024-09");
    });

    it("does not let incomplete draft date YYYY-MM block filling full date YYYY-MM-DD", () => {
      const candidateProfile: any = {
        ...profile,
        education: [
          {
            id: "edu_bachelor",
            school_name: "北京工业大学",
            education_level: "bachelor",
            major: "计算机科学与技术",
            start_date: "2020-09-01",
          },
        ],
      };

      const field: PageField = {
        ref: "d1",
        label: "本科入学时间",
        name: "bStart",
        kind: "text",
        type: "text",
        required: true,
        value: "2020-09", // page has draft year-month only
        options: [],
      };

      const plan = mapFields([field], candidateProfile);
      expect(plan[0].decision).toBe("fill");
      expect(plan[0].proposedValue).toBe("2020-09-01");
    });

    it("protects identity.id_number and contact.mobile from being corrupted during harvest", () => {
      const testProfile: any = {
        profile_id: "test-prot",
        identity: {
          name: "张三",
          id_type: "身份证",
          id_number: "110228200208040036",
        },
        contact: {
          mobile: "13691503049",
        },
      };

      const scannedFields: PageField[] = [
        {
          ref: "s1",
          label: "证件类型",
          name: "idType",
          kind: "select",
          required: true,
          value: "国内身份证或护照（含港澳台）",
          options: ["国内身份证或护照（含港澳台）", "外国护照"],
        },
        {
          ref: "s2",
          label: "手机国家代码",
          name: "countryCode",
          kind: "select",
          required: true,
          value: "中国大陆（+86）",
          options: ["中国大陆（+86）", "其他地区"],
        },
      ];

      const harvested = harvestPageFields(scannedFields, testProfile);
      const updated = applyHarvestedFields(testProfile, harvested);

      expect(updated.identity!.id_number).toBe("110228200208040036");
      expect(updated.contact!.mobile).toBe("13691503049");
    });

    it("correctly maps soe education attributes: primary education, full-time highest, rank and department fallback", () => {
      const soeProfile: any = {
        ...profile,
        education: [
          {
            id: "edu_master",
            school_name: "北京工业大学",
            education_level: "master",
            academic_degree: "工学硕士",
            major: "计算机科学与技术",
            department: "计算机学院",
            study_mode: "全日制",
            is_highest_degree: "yes",
            ranking_pct: "前 5%",
            school_system: "3",
          },
          {
            id: "edu_bachelor",
            school_name: "北京工业大学",
            education_level: "bachelor",
            academic_degree: "工学学士",
            major: "计算机科学与技术",
            department: "计算机学院",
            study_mode: "全日制统招",
            is_highest_degree: "no",
            ranking_pct: "前 5%",
            school_system: "4",
          },
        ],
        soe_extended: {
          custom_fields: {
            受教育类型: "全日制统招",
            年级排名: "前5%",
          },
        },
      };

      const fields: PageField[] = [
        { ref: "f1", label: "是否主教育经历", name: "isPrimary", kind: "select", required: true, value: "", options: ["--请选择--", "是", "否"] },
        { ref: "f2", label: "是否全日制最高学历", name: "isFullTimeHighest", kind: "select", required: true, value: "", options: ["--请选择--", "是", "否"] },
        { ref: "f3", label: "受教育类型", name: "studyType", kind: "select", required: true, value: "", options: ["--请选择--", "全日制统招", "非全日制"] },
        { ref: "f4", label: "年级排名", name: "rank", kind: "select", required: true, value: "", options: ["--请选择--", "前5%", "前10%"] },
        { ref: "f5", label: "学制", name: "system", kind: "select", required: true, value: "", options: ["--请选择--", "2", "3", "4"] },
        { ref: "f6", label: "本科受教育类型", name: "bStudyType", kind: "select", required: true, value: "", options: ["--请选择--", "全日制统招", "非全日制"] },
        { ref: "f7", label: "本科成绩排名", name: "bRank", kind: "select", required: true, value: "", options: ["--请选择--", "前5%", "前10%"] },
        { ref: "f8", label: "院系", name: "deptCampus", kind: "select", required: true, value: "", options: ["--请选择--", "北京/北京工业大学", "北京/北京工业大学通州校区", "北京/北京工业大学耿丹学院"] },
      ];

      const plan = mapFields(fields, soeProfile);
      expect(plan[0].proposedValue).toBe("是");
      expect(plan[1].proposedValue).toBe("是");
      expect(plan[2].proposedValue).toBe("全日制统招");
      expect(plan[3].proposedValue).toBe("前5%");
      expect(plan[4].proposedValue).toBe("3");
      expect(plan[5].proposedValue).toBe("全日制统招");
      expect(plan[6].proposedValue).toBe("前5%");
      // Department falls back to university main campus when options are campuses!
      expect(plan[7].proposedValue).toBe("北京/北京工业大学");
      expect(plan.every((item) => item.decision === "fill")).toBe(true);
    });

    it("maps bachelor dates, school and department accurately with full date format", () => {
      const bachelorProfile: any = {
        ...profile,
        education: [
          {
            id: "edu_master",
            school_name: "北京/北京工业大学",
            education_level: "master",
            major: "计算机科学与技术类/计算机系统结构",
            start_date: "2024-09-01",
            end_date: "2027-07-01",
          },
          {
            id: "edu_bachelor",
            school_name: "北京/北京工业大学",
            education_level: "bachelor",
            major: "计算机类/计算机科学与技术",
            department: "计算机学院",
            start_date: "2020-09-01",
            end_date: "2024-07-01",
          },
        ],
      };

      const fields: PageField[] = [
        { ref: "b1", label: "* 本科入学时间", name: "bStartDate", kind: "text", required: true, value: "", options: [] },
        { ref: "b2", label: "* 本科毕业时间", name: "bEndDate", kind: "text", required: true, value: "", options: [] },
        { ref: "b3", label: "* 本科学校名称", name: "bSchool", kind: "text", required: true, value: "", options: [] },
        { ref: "b4", label: "* 本科院系", name: "bDept", kind: "text", required: true, value: "", options: [] },
        { ref: "b5", label: "* 本科专业", name: "bMajor", kind: "text", required: true, value: "", options: [] },
      ];

      const plan = mapFields(fields, bachelorProfile);
      expect(plan[0].proposedValue).toBe("2020-09-01");
      expect(plan[1].proposedValue).toBe("2024-07-01");
      expect(plan[2].proposedValue).toBe("北京/北京工业大学");
      expect(plan[3].proposedValue).toBe("计算机学院");
      expect(plan[4].proposedValue).toBe("计算机类/计算机科学与技术");
      expect(plan.every((item) => item.decision === "fill")).toBe(true);
    });
  });
});

