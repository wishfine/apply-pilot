export type CandidateProfile = {
  profile_id: string;
  schema_version?: string;
  identity?: Record<string, unknown>;
  contact?: Record<string, unknown>;
  education?: Array<Record<string, unknown>>;
  experiences?: Array<Record<string, unknown>>;
  projects?: Array<Record<string, unknown>>;
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
};

export type FieldPlan = {
  field: PageField;
  decision: "fill" | "review" | "skip";
  profilePath?: string;
  proposedValue?: string;
  reason: string;
};

export function parseCandidateProfile(input: unknown): CandidateProfile {
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("资料文件必须是对象");
  const profile = input as Record<string, unknown>;
  if (typeof profile.profile_id !== "string" || !profile.profile_id.trim()) throw new Error("资料缺少 profile_id");
  for (const key of ["identity", "contact", "campus_context", "soe_extended"] as const) {
    if (profile[key] !== undefined && (typeof profile[key] !== "object" || profile[key] === null || Array.isArray(profile[key]))) throw new Error(`${key} 必须是对象`);
  }
  for (const key of ["education", "experiences", "projects", "skills", "assets"] as const) {
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
  "身份证号": { path: "identity.id_number", value: (p) => p.identity?.id_number },
  "出生日期": { path: "identity.birth_date", value: (p) => display(p.identity?.birth_date) },
  "手机号": { path: "contact.mobile", value: (p) => p.contact?.mobile },
  "手机号码": { path: "contact.mobile", value: (p) => p.contact?.mobile },
  "手机": { path: "contact.mobile", value: (p) => p.contact?.mobile },
  "电子邮箱": { path: "contact.email", value: (p) => p.contact?.email },
  "邮箱": { path: "contact.email", value: (p) => p.contact?.email },
  "现居城市": { path: "contact.current_city", value: (p) => p.contact?.current_city },
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
  "入学时间": { path: "education[highest].start_date", value: (p) => display(highest(p.education)?.start_date) },
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

function weight(value: unknown) {
  const text = String(value || "").toLowerCase();
  if (text.includes("doctor") || text.includes("博士")) return 5;
  if (text.includes("master") || text.includes("硕士")) return 4;
  if (text.includes("bachelor") || text.includes("本科")) return 3;
  if (text.includes("associate") || text.includes("专科") || text.includes("大专")) return 2;
  return 1;
}

function normalize(value: string) {
  return value.replace(/[\s:*：()（）【】\[\]必选填项]/g, "").toLowerCase();
}

function fieldKey(field: PageField) {
  const value = normalize(`${field.label}${field.name}`);
  return Object.keys(aliases).find((key) => value === normalize(key) || value.includes(normalize(key))) || "";
}

export function mapFields(fields: PageField[], profile?: CandidateProfile): FieldPlan[] {
  return fields.map((field) => {
    if (field.value.trim()) return { field, decision: "skip", reason: "已有内容，已保留" };
    if (!profile) return { field, decision: "review", reason: "请先导入候选人资料" };
    const key = fieldKey(field);
    const rule = aliases[key];
    if (!rule) return { field, decision: "review", reason: "没有唯一的字段规则，请手动选择资料" };
    const value = rule.value(profile);
    if (value === undefined || value === null || String(value).trim() === "") return { field, decision: "review", profilePath: rule.path, reason: `资料缺少：${rule.path}` };
    if (field.kind === "choice") return { field, decision: "review", profilePath: rule.path, proposedValue: String(value), reason: "选择控件需要确认具体选项" };
    if (field.kind === "file") return { field, decision: "review", profilePath: rule.path, proposedValue: String(value), reason: "附件需要在浏览器中选择文件" };
    const proposedValue = formatValue(rule.path, value);
    if (field.type === "date" && /^\d{4}-\d{2}$/.test(proposedValue)) return { field, decision: "review", profilePath: rule.path, proposedValue, reason: "资料只有年月，日期控件需要完整日期" };
    return { field, decision: "fill", profilePath: rule.path, proposedValue, reason: `来源：${rule.path}` };
  });
}

function formatValue(path: string, value: unknown): string {
  const displayed = String(display(value));
  if (path.endsWith("education_level")) {
    return ({ high_school: "高中", associate: "专科", bachelor: "本科", master: "硕士", doctor: "博士" } as Record<string, string>)[displayed.toLowerCase()] || displayed;
  }
  return displayed;
}
