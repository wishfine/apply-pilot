export type CandidateProfile = {
  profile_id: string;
  schema_version?: string;
  identity?: Record<string, unknown>;
  contact?: Record<string, unknown>;
  education?: Array<Record<string, unknown>>;
  experiences?: Array<Record<string, unknown>>;
  projects?: Array<Record<string, unknown>>;
  awards?: Array<Record<string, unknown>>;
  publications?: Array<Record<string, unknown>>;
  certificates?: Array<Record<string, unknown>>;
  campus_practices?: Array<Record<string, unknown>>;
  skills?: Array<Record<string, unknown>>;
  campus_context?: Record<string, unknown>;
  soe_extended?: Record<string, unknown>;
  assets?: Array<Record<string, unknown>>;
  [key: string]: unknown;
};

export type PageField = {
  ref: string;
  frameId?: number;
  label: string;
  name: string;
  type?: string;
  kind: string;
  required: boolean;
  value: string;
  options: string[];
  section?: string;
};

export type FieldPlan = {
  field: PageField;
  decision: "fill" | "review" | "skip";
  profilePath?: string;
  proposedValue?: string;
  reason: string;
};

type MappingSource = "base" | "experience" | "project" | "award" | "publication" | "certificate" | "practice";

export function parseCandidateProfile(input: unknown): CandidateProfile {
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("资料文件必须是对象");
  const profile = input as Record<string, unknown>;
  if (typeof profile.profile_id !== "string" || !profile.profile_id.trim()) throw new Error("资料缺少 profile_id");
  for (const key of ["identity", "contact", "campus_context", "soe_extended"] as const) {
    if (profile[key] !== undefined && (typeof profile[key] !== "object" || profile[key] === null || Array.isArray(profile[key]))) throw new Error(`${key} 必须是对象`);
  }
  for (const key of ["education", "experiences", "projects", "awards", "publications", "certificates", "campus_practices", "skills", "assets"] as const) {
    if (profile[key] !== undefined && !Array.isArray(profile[key])) throw new Error(`${key} 必须是数组`);
    if (Array.isArray(profile[key]) && profile[key].some((item) => !item || typeof item !== "object" || Array.isArray(item))) throw new Error(`${key} 中的每一项必须是对象`);
  }
  for (const item of (profile.education as Array<Record<string, unknown>> | undefined) || []) {
    for (const key of ["id", "school_name", "education_level", "major"]) if (typeof item[key] !== "string" || !item[key]) throw new Error(`education 缺少 ${key}`);
  }
  return profile as CandidateProfile;
}

const aliases: Record<string, { path: string; value: (profile: CandidateProfile) => unknown }> = {
  "姓名": { path: "identity.name", value: (p) => p.identity?.name },
  "真实姓名": { path: "identity.name", value: (p) => p.identity?.name },
  "英文名": { path: "identity.english_name", value: (p) => p.identity?.english_name },
  "性别": { path: "identity.gender", value: (p) => p.identity?.gender },
  "民族": { path: "identity.ethnicity", value: (p) => p.identity?.ethnicity },
  "证件类型": { path: "identity.id_type", value: (p) => p.identity?.id_type },
  "身份证号": { path: "identity.id_number", value: (p) => p.identity?.id_number },
  "身份证": { path: "identity.id_number", value: (p) => p.identity?.id_number },
  "证件号码": { path: "identity.id_number", value: (p) => p.identity?.id_number },
  "证件编号": { path: "identity.id_number", value: (p) => p.identity?.id_number },
  "出生日期": { path: "identity.birth_date", value: (p) => display(p.identity?.birth_date) },
  "出生地": { path: "soe_extended.native_place", value: (p) => p.soe_extended?.native_place },
  "健康状况": { path: "identity.health_status", value: (p) => p.identity?.health_status },
  "健康状态": { path: "identity.health_status", value: (p) => p.identity?.health_status },
  "婚姻状况": { path: "identity.marital_status", value: (p) => p.identity?.marital_status },
  "手机号": { path: "contact.mobile", value: (p) => p.contact?.mobile },
  "手机号码": { path: "contact.mobile", value: (p) => p.contact?.mobile },
  "手机": { path: "contact.mobile", value: (p) => p.contact?.mobile },
  "电子邮箱": { path: "contact.email", value: (p) => p.contact?.email },
  "邮箱": { path: "contact.email", value: (p) => p.contact?.email },
  "现居城市": { path: "contact.current_city", value: (p) => p.contact?.current_city },
  "现居住地": { path: "contact.current_city", value: (p) => p.contact?.current_city },
  "现居地址": { path: "contact.current_address", value: (p) => p.contact?.current_address },
  "国籍": { path: "identity.nationality", value: (p) => p.identity?.nationality },
  "国籍地区": { path: "identity.nationality", value: (p) => p.identity?.nationality },
  "QQ": { path: "contact.qq", value: (p) => p.contact?.qq },
  "微信": { path: "contact.wechat", value: (p) => p.contact?.wechat },
  "微信号": { path: "contact.wechat", value: (p) => p.contact?.wechat },
  "籍贯": { path: "soe_extended.native_place", value: (p) => p.soe_extended?.native_place },
  "户口所在地": { path: "soe_extended.household_registration", value: (p) => p.soe_extended?.household_registration },
  "政治面貌": { path: "soe_extended.political_status", value: (p) => p.soe_extended?.political_status },
  "毕业院校": { path: "education[highest].school_name", value: (p) => highest(p.education)?.school_name },
  "学校名称": { path: "education[highest].school_name", value: (p) => highest(p.education)?.school_name },
  "专业": { path: "education[highest].major", value: (p) => highest(p.education)?.major },
  "专业名称": { path: "education[highest].major", value: (p) => highest(p.education)?.major },
  "所学专业": { path: "education[highest].major", value: (p) => highest(p.education)?.major },
  "学校": { path: "education[highest].school_name", value: (p) => highest(p.education)?.school_name },
  "毕业学校": { path: "education[highest].school_name", value: (p) => highest(p.education)?.school_name },
  "院校": { path: "education[highest].school_name", value: (p) => highest(p.education)?.school_name },
  "最高学历": { path: "education[highest].education_level", value: (p) => highest(p.education)?.education_level },
  "学历": { path: "education[highest].education_level", value: (p) => highest(p.education)?.education_level },
  "学位": { path: "education[highest].academic_degree", value: (p) => highest(p.education)?.academic_degree },
  "毕业时间": { path: "education[highest].end_date", value: (p) => display(highest(p.education)?.end_date) },
  "结束时间": { path: "education[highest].end_date", value: (p) => display(highest(p.education)?.end_date) },
  "结束日期": { path: "education[highest].end_date", value: (p) => display(highest(p.education)?.end_date) },
  "开始时间": { path: "education[highest].start_date", value: (p) => display(highest(p.education)?.start_date) },
  "开始日期": { path: "education[highest].start_date", value: (p) => display(highest(p.education)?.start_date) },
  "入学时间": { path: "education[highest].start_date", value: (p) => display(highest(p.education)?.start_date) },
  "学院名称": { path: "education[highest].department", value: (p) => highest(p.education)?.department },
  "学院": { path: "education[highest].department", value: (p) => highest(p.education)?.department },
  "院系": { path: "education[highest].department", value: (p) => highest(p.education)?.department },
  "院系名称": { path: "education[highest].department", value: (p) => highest(p.education)?.department },
};

const experienceAliases: Record<string, { path: string; value: (profile: CandidateProfile) => unknown }> = {
  "公司名称": { path: "experiences[latest].org_name", value: (p) => latestExperience(p.experiences)?.org_name },
  "公司": { path: "experiences[latest].org_name", value: (p) => latestExperience(p.experiences)?.org_name },
  "单位名称": { path: "experiences[latest].org_name", value: (p) => latestExperience(p.experiences)?.org_name },
  "实习单位": { path: "experiences[latest].org_name", value: (p) => latestExperience(p.experiences)?.org_name },
  "实习公司": { path: "experiences[latest].org_name", value: (p) => latestExperience(p.experiences)?.org_name },
  "工作单位": { path: "experiences[latest].org_name", value: (p) => latestExperience(p.experiences)?.org_name },
  "所在单位": { path: "experiences[latest].org_name", value: (p) => latestExperience(p.experiences)?.org_name },
  "任职单位": { path: "experiences[latest].org_name", value: (p) => latestExperience(p.experiences)?.org_name },
  "任职公司": { path: "experiences[latest].org_name", value: (p) => latestExperience(p.experiences)?.org_name },
  "职位": { path: "experiences[latest].title", value: (p) => latestExperience(p.experiences)?.title },
  "岗位": { path: "experiences[latest].title", value: (p) => latestExperience(p.experiences)?.title },
  "岗位名称": { path: "experiences[latest].title", value: (p) => latestExperience(p.experiences)?.title },
  "职位名称": { path: "experiences[latest].title", value: (p) => latestExperience(p.experiences)?.title },
  "职务": { path: "experiences[latest].title", value: (p) => latestExperience(p.experiences)?.title },
  "任职岗位": { path: "experiences[latest].title", value: (p) => latestExperience(p.experiences)?.title },
  "实习岗位": { path: "experiences[latest].title", value: (p) => latestExperience(p.experiences)?.title },
  "部门": { path: "experiences[latest].department", value: (p) => latestExperience(p.experiences)?.department },
  "所在城市": { path: "experiences[latest].city", value: (p) => latestExperience(p.experiences)?.city },
  "工作城市": { path: "experiences[latest].city", value: (p) => latestExperience(p.experiences)?.city },
  "开始时间": { path: "experiences[latest].start_date", value: (p) => display(latestExperience(p.experiences)?.start_date) },
  "开始日期": { path: "experiences[latest].start_date", value: (p) => display(latestExperience(p.experiences)?.start_date) },
  "入职时间": { path: "experiences[latest].start_date", value: (p) => display(latestExperience(p.experiences)?.start_date) },
  "实习开始时间": { path: "experiences[latest].start_date", value: (p) => display(latestExperience(p.experiences)?.start_date) },
  "结束时间": { path: "experiences[latest].end_date", value: (p) => display(latestExperience(p.experiences)?.end_date) },
  "结束日期": { path: "experiences[latest].end_date", value: (p) => display(latestExperience(p.experiences)?.end_date) },
  "离职时间": { path: "experiences[latest].end_date", value: (p) => display(latestExperience(p.experiences)?.end_date) },
  "实习结束时间": { path: "experiences[latest].end_date", value: (p) => display(latestExperience(p.experiences)?.end_date) },
  "工作内容": { path: "experiences[latest].description_bullets", value: (p) => experienceDescription(p.experiences) },
  "实习内容": { path: "experiences[latest].description_bullets", value: (p) => experienceDescription(p.experiences) },
  "工作描述": { path: "experiences[latest].description_bullets", value: (p) => experienceDescription(p.experiences) },
  "工作职责": { path: "experiences[latest].description_bullets", value: (p) => experienceDescription(p.experiences) },
};

const projectAliases: Record<string, { path: string; value: (profile: CandidateProfile) => unknown }> = {
  "项目名称": { path: "projects[latest].project_name", value: (p) => latestProject(p.projects)?.project_name },
  "项目标题": { path: "projects[latest].project_name", value: (p) => latestProject(p.projects)?.project_name },
  "项目角色": { path: "projects[latest].role", value: (p) => latestProject(p.projects)?.role },
  "项目职责": { path: "projects[latest].role", value: (p) => latestProject(p.projects)?.role },
  "担任角色": { path: "projects[latest].role", value: (p) => latestProject(p.projects)?.role },
  "项目简介": { path: "projects[latest].summary", value: (p) => latestProject(p.projects)?.summary },
  "项目介绍": { path: "projects[latest].summary", value: (p) => latestProject(p.projects)?.summary },
  "项目描述": { path: "projects[latest].description_bullets", value: (p) => projectDescription(p.projects) },
  "项目内容": { path: "projects[latest].description_bullets", value: (p) => projectDescription(p.projects) },
  "项目成果": { path: "projects[latest].description_bullets", value: (p) => projectDescription(p.projects) },
  "项目链接": { path: "projects[latest].repo_url", value: (p) => latestProject(p.projects)?.repo_url },
  "项目地址": { path: "projects[latest].repo_url", value: (p) => latestProject(p.projects)?.repo_url },
  "项目开始时间": { path: "projects[latest].start_date", value: (p) => display(latestProject(p.projects)?.start_date) },
  "项目结束时间": { path: "projects[latest].end_date", value: (p) => display(latestProject(p.projects)?.end_date) },
  "开始时间": { path: "projects[latest].start_date", value: (p) => display(latestProject(p.projects)?.start_date) },
  "结束时间": { path: "projects[latest].end_date", value: (p) => display(latestProject(p.projects)?.end_date) },
  "开始日期": { path: "projects[latest].start_date", value: (p) => display(latestProject(p.projects)?.start_date) },
  "结束日期": { path: "projects[latest].end_date", value: (p) => display(latestProject(p.projects)?.end_date) },
};

const awardAliases: Record<string, { path: string; value: (profile: CandidateProfile) => unknown }> = {
  "获奖项": { path: "awards[latest].name", value: (p) => latestRecord(p.awards)?.name },
  "奖项": { path: "awards[latest].name", value: (p) => latestRecord(p.awards)?.name },
  "奖项名称": { path: "awards[latest].name", value: (p) => latestRecord(p.awards)?.name },
  "获奖名称": { path: "awards[latest].name", value: (p) => latestRecord(p.awards)?.name },
  "获奖描述": { path: "awards[latest].description", value: (p) => latestRecord(p.awards)?.description || latestRecord(p.awards)?.name },
  "奖项描述": { path: "awards[latest].description", value: (p) => latestRecord(p.awards)?.description || latestRecord(p.awards)?.name },
};

const publicationAliases: Record<string, { path: string; value: (profile: CandidateProfile) => unknown }> = {
  "论文题目": { path: "publications[latest].title", value: (p) => latestRecord(p.publications)?.title },
  "论文名称": { path: "publications[latest].title", value: (p) => latestRecord(p.publications)?.title },
  "论文": { path: "publications[latest].title", value: (p) => latestRecord(p.publications)?.title },
  "专著名称": { path: "publications[latest].title", value: (p) => latestRecord(p.publications)?.title },
  "论文描述": { path: "publications[latest].description", value: (p) => latestRecord(p.publications)?.description },
  "发表刊物": { path: "publications[latest].venue", value: (p) => latestRecord(p.publications)?.venue },
  "期刊名称": { path: "publications[latest].venue", value: (p) => latestRecord(p.publications)?.venue },
  "论文作者": { path: "publications[latest].authors", value: (p) => latestRecord(p.publications)?.authors },
  "名称": { path: "publications[latest].title", value: (p) => latestRecord(p.publications)?.title },
  "成果描述": { path: "publications[latest].description", value: (p) => latestRecord(p.publications)?.description },
};

const certificateAliases: Record<string, { path: string; value: (profile: CandidateProfile) => unknown }> = {
  "证书名称": { path: "certificates[latest].name", value: (p) => latestRecord(p.certificates)?.name },
  "证书描述": { path: "certificates[latest].description", value: (p) => latestRecord(p.certificates)?.description },
  "证书编号": { path: "certificates[latest].number", value: (p) => latestRecord(p.certificates)?.number },
};

const practiceAliases: Record<string, { path: string; value: (profile: CandidateProfile) => unknown }> = {
  "实践名称": { path: "campus_practices[latest].name", value: (p) => latestRecord(p.campus_practices)?.name },
  "实践描述": { path: "campus_practices[latest].description", value: (p) => latestRecord(p.campus_practices)?.description },
  "实践内容": { path: "campus_practices[latest].description", value: (p) => latestRecord(p.campus_practices)?.description },
};

function display(value: unknown): unknown {
  if (!value || typeof value !== "object") return value;
  const date = value as { year?: number; month?: number; day?: number };
  if (!date.year) return value;
  if (date.day && date.month) return `${date.year}-${String(date.month).padStart(2, "0")}-${String(date.day).padStart(2, "0")}`;
  if (date.month) return `${date.year}-${String(date.month).padStart(2, "0")}`;
  return String(date.year);
}

function highest(records: Array<Record<string, unknown>> | undefined) {
  return [...(records || [])].sort((a, b) => weight(b.education_level) - weight(a.education_level))[0];
}

function latestExperience(records: Array<Record<string, unknown>> | undefined) {
  return experienceRecords(records)[0];
}

function experienceRecords(records: Array<Record<string, unknown>> | undefined) {
  const internships = (records || []).filter((record) => {
    const type = String(record.experience_type || record.type || "").toLowerCase();
    return !type || type.includes("intern") || type.includes("实习");
  });
  return [...(internships.length ? internships : records || [])].sort((a, b) => dateSortKey(b.end_date || b.start_date).localeCompare(dateSortKey(a.end_date || a.start_date)));
}

function latestRecord(records: Array<Record<string, unknown>> | undefined) {
  return recordRecords(records)[0];
}

function recordRecords(records: Array<Record<string, unknown>> | undefined) {
  return [...(records || [])].sort((a, b) => dateSortKey(b.end_date || b.date || b.published_date || b.start_date || b.year).localeCompare(dateSortKey(a.end_date || a.date || a.published_date || a.start_date || a.year)));
}

function projectRecords(records: Array<Record<string, unknown>> | undefined) {
  return [...(records || [])].sort((a, b) => dateSortKey(b.end_date || b.start_date).localeCompare(dateSortKey(a.end_date || a.start_date)));
}

function latestProject(records: Array<Record<string, unknown>> | undefined) {
  return projectRecords(records)[0];
}

function dateSortKey(value: unknown) {
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  if (value && typeof value === "object") {
    const date = value as { year?: number; month?: number; day?: number };
    if (date.year) return `${date.year}-${String(date.month || 0).padStart(2, "0")}-${String(date.day || 0).padStart(2, "0")}`;
  }
  return "";
}

function experienceDescription(records: Array<Record<string, unknown>> | undefined) {
  const bullets = latestExperience(records)?.description_bullets;
  return Array.isArray(bullets) ? bullets.filter((bullet): bullet is string => typeof bullet === "string").join("\n") : undefined;
}

function experienceDescriptionAt(record: Record<string, unknown> | undefined) {
  const bullets = record?.description_bullets;
  return Array.isArray(bullets) ? bullets.filter((bullet): bullet is string => typeof bullet === "string").join("\n") : undefined;
}

function projectDescription(records: Array<Record<string, unknown>> | undefined) {
  const project = latestProject(records);
  if (!project) return undefined;
  if (Array.isArray(project.description_bullets)) return project.description_bullets.filter((bullet): bullet is string => typeof bullet === "string").join("\n");
  return project.summary;
}

function projectDescriptionAt(record: Record<string, unknown> | undefined) {
  if (!record) return undefined;
  if (Array.isArray(record.description_bullets)) return record.description_bullets.filter((bullet): bullet is string => typeof bullet === "string").join("\n");
  return record.summary;
}

function weight(value: unknown) {
  const text = String(value || "").toLowerCase();
  if (text.includes("doctor") || text.includes("博士")) return 5;
  if (text.includes("master") || text.includes("硕士")) return 4;
  if (text.includes("bachelor") || text.includes("本科")) return 3;
  if (text.includes("associate") || text.includes("专科") || text.includes("大专")) return 2;
  return 1;
}

function normalize(value: string) {
  return value.replace(/[\s:*：\/／,，.。·()（）【】\[\]_-]/g, "").replace(/必选填项|必填|选填/g, "").toLowerCase();
}

function findKey(field: PageField, rules: Record<string, unknown>) {
  const value = normalize(`${field.label}${field.name}`);
  return Object.keys(rules).find((key) => value === normalize(key) || value.includes(normalize(key))) || "";
}

function fieldRule(field: PageField, section?: string): { rule: { path: string; value: (profile: CandidateProfile) => unknown }; source: MappingSource } | undefined {
  const scope = field.section || section;
  if (scope === "实习经历") {
    const key = findKey(field, experienceAliases);
    if (key) return { rule: experienceAliases[key], source: "experience" };
  }
  if (scope === "项目经历") {
    const key = findKey(field, projectAliases);
    if (key) return { rule: projectAliases[key], source: "project" };
  }
  if (scope === "获奖情况") {
    const key = findKey(field, awardAliases);
    if (key) return { rule: awardAliases[key], source: "award" };
  }
  if (scope === "论文/专著") {
    const key = findKey(field, publicationAliases);
    if (key) return { rule: publicationAliases[key], source: "publication" };
  }
  if (scope === "证书") {
    const key = findKey(field, certificateAliases);
    if (key) return { rule: certificateAliases[key], source: "certificate" };
  }
  if (scope === "在校实践") {
    const key = findKey(field, practiceAliases);
    if (key) return { rule: practiceAliases[key], source: "practice" };
  }
  const baseKey = findKey(field, aliases);
  if (baseKey) return { rule: aliases[baseKey], source: "base" };
  const experienceKey = findKey(field, experienceAliases);
  if (experienceKey && !["开始时间", "结束时间", "开始日期", "结束日期"].includes(experienceKey)) return { rule: experienceAliases[experienceKey], source: "experience" };
  const projectKey = findKey(field, projectAliases);
  if (projectKey) return { rule: projectAliases[projectKey], source: "project" };
  const awardKey = findKey(field, awardAliases);
  if (awardKey) return { rule: awardAliases[awardKey], source: "award" };
  const publicationKey = findKey(field, publicationAliases);
  if (publicationKey && !["名称", "成果描述"].includes(publicationKey)) return { rule: publicationAliases[publicationKey], source: "publication" };
  const certificateKey = findKey(field, certificateAliases);
  if (certificateKey) return { rule: certificateAliases[certificateKey], source: "certificate" };
  const practiceKey = findKey(field, practiceAliases);
  if (practiceKey) return { rule: practiceAliases[practiceKey], source: "practice" };
  return undefined;
}

function valueForRecord(rule: { path: string }, profile: CandidateProfile, source: MappingSource, index: number) {
  const recordMatch = rule.path.match(/^(?:experiences|projects|awards|publications|certificates|campus_practices)\[latest\]\.(.+)$/);
  if (!recordMatch) return rule.path.includes("education[highest]") ? undefined : undefined;
  const key = recordMatch[1];
  const records = source === "experience" ? experienceRecords(profile.experiences) : source === "project" ? projectRecords(profile.projects) : recordRecords(source === "award" ? profile.awards : source === "publication" ? profile.publications : source === "certificate" ? profile.certificates : profile.campus_practices);
  const record = records[index];
  if (source === "experience" && key === "description_bullets") return experienceDescriptionAt(record);
  if (source === "project" && key === "description_bullets") return projectDescriptionAt(record);
  return record?.[key];
}

function pathForIndex(path: string, source: MappingSource, index: number | undefined) {
  if (index === undefined || source === "base") return path;
  return path.replace("[latest]", `[${index}]`);
}

export function mapFields(fields: PageField[], profile?: CandidateProfile, section?: string): FieldPlan[] {
  const occurrences: Record<string, number> = {};
  const experienceSlotIndices: number[] = [];
  const usedExperienceIndices = new Set<number>();
  if (profile) {
    fields.forEach((field) => {
      if (!field.value.trim()) return;
      const selected = fieldRule(field, section);
      if (!selected || selected.source !== "experience" || !/\.(org_name|title)$/.test(selected.rule.path)) return;
      const wanted = field.value.trim().toLowerCase();
      const index = experienceRecords(profile.experiences).findIndex((record) => [record.org_name, record.title].some((value) => String(value || "").trim().toLowerCase() === wanted));
      if (index >= 0) usedExperienceIndices.add(index);
    });
  }
  const recordIndexFor = (source: MappingSource, slot: number) => {
    if (source !== "experience") return slot;
    if (experienceSlotIndices[slot] !== undefined) return experienceSlotIndices[slot];
    const records = experienceRecords(profile?.experiences);
    const used = new Set([...usedExperienceIndices, ...experienceSlotIndices.filter((index): index is number => index !== undefined)]);
    const available = records.findIndex((_record, index) => !used.has(index));
    experienceSlotIndices[slot] = available >= 0 ? available : records.length;
    return experienceSlotIndices[slot];
  };
  return fields.map((field) => {
    if (field.value.trim()) return { field, decision: "skip", reason: "已有内容，已保留" };
    if (!field.required) return { field, decision: "skip", reason: "选填项，按要求留空" };
    if (!profile) return { field, decision: "review", reason: "请先导入候选人资料" };
    const selected = fieldRule(field, section);
    if (!selected) return { field, decision: "review", reason: "没有唯一的字段规则，请手动选择资料" };
    const slotKey = selected.source === "base" ? "" : `${selected.source}:${selected.rule.path.match(/\.(\w+)$/)?.[1] || selected.rule.path}`;
    const index = slotKey ? occurrences[slotKey] || 0 : undefined;
    if (slotKey) occurrences[slotKey] = (index || 0) + 1;
    const recordIndex = index === undefined ? undefined : recordIndexFor(selected.source, index);
    const profilePath = pathForIndex(selected.rule.path, selected.source, recordIndex);
    const value = recordIndex === undefined ? selected.rule.value(profile) : valueForRecord(selected.rule, profile, selected.source, recordIndex);
    if (value === undefined || value === null || String(value).trim() === "") return { field, decision: "review", profilePath, reason: `资料缺少：${profilePath}` };
    if (field.kind === "choice") return { field, decision: "review", profilePath, proposedValue: String(value), reason: "选择控件需要确认具体选项" };
    if (field.kind === "file") return { field, decision: "review", profilePath, proposedValue: String(value), reason: "附件需要在浏览器中选择文件" };
    const proposedValue = formatValue(profilePath, value);
    if (field.type === "date" && /^\d{4}-\d{2}$/.test(proposedValue)) return { field, decision: "review", profilePath, proposedValue, reason: "资料只有年月，日期控件需要完整日期" };
    return { field, decision: "fill", profilePath, proposedValue, reason: `来源：${profilePath}` };
  });
}

function formatValue(path: string, value: unknown): string {
  const displayed = String(display(value));
  if (path.endsWith("education_level")) {
    return ({ high_school: "高中", associate: "专科", bachelor: "本科", master: "硕士", doctor: "博士" } as Record<string, string>)[displayed.toLowerCase()] || displayed;
  }
  return displayed;
}
