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

export type LocationComponents = {
  province: string;
  city: string;
  district: string;
};

const PROVINCE_NAMES = [
  "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
  "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
  "湖北", "湖南", "广东", "广西", "海南", "重庆", "四川", "贵州",
  "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆", "香港", "澳门", "台湾"
];

export function extractLocationComponents(rawAddress: unknown): LocationComponents {
  const str = String(rawAddress || "").trim();
  if (!str) return { province: "", city: "", district: "" };

  let province = "";
  let remaining = str;

  for (const prov of PROVINCE_NAMES) {
    if (str.startsWith(prov)) {
      province = prov;
      const match = str.match(new RegExp(`^${prov}(?:省|市|自治区|特别行政区|壮族自治区|回族自治区|维吾尔自治区)?`));
      if (match) {
        remaining = str.slice(match[0].length).trim();
      }
      break;
    }
  }

  const isMunicipality = ["北京", "天津", "上海", "重庆"].includes(province);
  let city = "";
  let district = "";

  if (isMunicipality) {
    province = `${province}市`;
    city = remaining ? `${province}${remaining}` : province;
    district = remaining || province;
  } else {
    const cityMatch = remaining.match(/^(.+?(?:市|自治州|地区|盟|州))/);
    if (cityMatch) {
      city = cityMatch[1];
      district = remaining.slice(cityMatch[0].length).trim() || city;
    } else {
      city = remaining || province;
      district = city;
    }
    if (province && !province.endsWith("省") && !province.endsWith("自治区")) {
      province = `${province}省`;
    }
  }

  return { province: province || str, city: city || str, district: district || city || str };
}

export const SYNONYM_GROUPS: string[][] = [
  // 政治面貌
  ["中国共产党党员", "中共党员", "党员"],
  ["中国共产党预备党员", "中共预备党员", "预备党员"],
  ["中国共产主义青年团团员", "共青团员", "共青团", "中国共青团员", "青年团团员", "团员"],
  ["群众", "普通群众"],
  ["无党派民主人士", "无党派人士", "无党派"],
  ["中国国民党革命委员会会员", "民革会员", "民革党员", "民革"],
  ["中国民主同盟盟员", "民盟盟员", "民盟"],
  ["中国民主建国会会员", "民建会员", "民建"],
  ["中国民主促进会会员", "民进会员", "民进"],
  ["中国农工民主党党员", "农工党党员", "农工党"],
  ["中国致公党党员", "致公党党员", "致公党"],
  ["九三学社社员", "九三学社"],
  ["台湾民主自治同盟盟员", "台盟盟员", "台盟"],

  // 证件类型
  ["国内身份证或护照（含港澳台）", "居民身份证", "中华人民共和国居民身份证", "二代居民身份证", "二代身份证", "身份证", "国内身份证", "大陆居民身份证", "国内身份证或护照"],
  ["国外身份证", "外籍身份证", "外籍证件"],
  ["护照", "中国护照", "因私普通护照", "外国护照"],
  ["港澳居民来往内地通行证", "港澳通行证", "回乡证"],
  ["台湾居民来往大陆通行证", "台胞证"],

  // 手机国家代码/区号
  ["中国大陆（+86）", "中国大陆(+86)", "+86", "86", "中国大陆", "中国(+86)", "+86(中国大陆)", "+86中国大陆", "中国"],
  ["其他地区手机号", "其他地区", "境外手机号", "其他国家或地区", "其他"],

  // 学历层次
  ["博士研究生", "博士", "doctor", "博士生"],
  ["硕士研究生", "硕士", "master", "研究生", "硕士生"],
  ["大学本科", "本科", "bachelor", "普通本科", "全日制本科", "本科生"],
  ["大学专科", "专科", "大专", "associate", "高职", "专科(高职)"],
  ["普通高中", "高中", "high_school", "中专"],

  // 是否 / 调剂 / 处分 / 犯罪
  ["是", "yes", "true", "1", "有", "服从", "同意", "参加", "合格", "已通过"],
  ["否", "no", "false", "0", "无", "不服从", "不同意", "未参加", "不合格", "未通过"],

  // 婚姻状况
  ["未婚", "未婚/single", "single"],
  ["已婚", "已婚/married", "married"],
  ["离异", "离异/divorced", "divorced"],

  // 性别
  ["男", "男性", "male"],
  ["女", "女性", "female"],

  // 户口性质
  ["城镇居民", "城镇", "城镇户口", "城市居民", "非农业户口", "非农"],
  ["农村居民", "农村", "农村户口", "农业户口", "农业"]
];

export function matchOptionText(options: string[], targetValue: unknown): string | undefined {
  if (!options || options.length === 0 || targetValue === undefined || targetValue === null) return undefined;
  const rawTarget = String(targetValue).trim();
  if (!rawTarget) return undefined;
  const normTarget = normalize(rawTarget);

  const validOptions = options.filter((opt) => {
    const norm = normalize(opt);
    return norm && !/^(请选择|--请选择--|选择|未选择|select)$/i.test(norm);
  });
  if (validOptions.length === 0) return undefined;

  // 1. Exact normalized match
  const exact = validOptions.find((opt) => normalize(opt) === normTarget);
  if (exact) return exact;

  // 2. Synonym groups lookup
  for (const group of SYNONYM_GROUPS) {
    const targetInGroup = group.some((item) => normalize(item) === normTarget || normTarget.includes(normalize(item)) || normalize(item).includes(normTarget));
    if (targetInGroup) {
      for (const item of group) {
        const normItem = normalize(item);
        const matched = validOptions.find((opt) => {
          const normOpt = normalize(opt);
          return normOpt === normItem || normOpt.includes(normItem) || normItem.includes(normOpt);
        });
        if (matched) return matched;
      }
    }
  }

  // 3. Location matching: check if target is location and option is province/city
  const loc = extractLocationComponents(rawTarget);
  if (loc.province) {
    const provShort = loc.province.replace(/省|市|自治区|特别行政区/g, "");
    const provMatch = validOptions.find((opt) => {
      const normOpt = normalize(opt);
      return normOpt === normalize(loc.province) || (provShort.length >= 2 && normOpt === provShort) || (normOpt.length >= 2 && loc.province.includes(normOpt));
    });
    if (provMatch) return provMatch;
  }
  if (loc.city) {
    const cityShort = loc.city.replace(/市|区|地区/g, "");
    const cityMatch = validOptions.find((opt) => {
      const normOpt = normalize(opt);
      return normOpt === normalize(loc.city) || (cityShort.length >= 2 && normOpt.includes(cityShort)) || (normOpt.length >= 2 && loc.city.includes(normOpt));
    });
    if (cityMatch) return cityMatch;
  }

  // 4. Substring inclusion match (longer options preferred)
  const sorted = [...validOptions].sort((a, b) => b.length - a.length);
  const inclusion = sorted.find((opt) => {
    const normOpt = normalize(opt);
    return normOpt.length >= 2 && (normTarget.includes(normOpt) || normOpt.includes(normTarget));
  });
  if (inclusion) return inclusion;

  return undefined;
}

const aliases: Record<string, { path: string; value: (profile: CandidateProfile) => unknown }> = {
  "姓名": { path: "identity.name", value: (p) => p.identity?.name },
  "真实姓名": { path: "identity.name", value: (p) => p.identity?.name },
  "英文名": { path: "identity.english_name", value: (p) => p.identity?.english_name },
  "性别": { path: "identity.gender", value: (p) => p.identity?.gender },
  "民族": { path: "identity.ethnicity", value: (p) => p.identity?.ethnicity },
  "证件类型": { path: "identity.id_type", value: (p) => p.identity?.id_type || "国内身份证或护照（含港澳台）" },
  "证件种类": { path: "identity.id_type", value: (p) => p.identity?.id_type || "国内身份证或护照（含港澳台）" },
  "身份证号": { path: "identity.id_number", value: (p) => p.identity?.id_number },
  "身份证": { path: "identity.id_number", value: (p) => p.identity?.id_number },
  "证件号码": { path: "identity.id_number", value: (p) => p.identity?.id_number },
  "证件编号": { path: "identity.id_number", value: (p) => p.identity?.id_number },
  "出生日期": { path: "identity.birth_date", value: (p) => display(p.identity?.birth_date) },
  "出生地": { path: "identity.birth_place", value: (p) => p.identity?.birth_place || p.soe_extended?.native_place },
  "出生地点": { path: "identity.birth_place", value: (p) => p.identity?.birth_place || p.soe_extended?.native_place },
  "证件有效期": { path: "identity.id_expiry_date", value: (p) => p.identity?.id_expiry_date },
  "身份证有效期": { path: "identity.id_expiry_date", value: (p) => p.identity?.id_expiry_date },
  "健康状况": { path: "identity.health_status", value: (p) => p.identity?.health_status },
  "健康状态": { path: "identity.health_status", value: (p) => p.identity?.health_status },
  "婚姻状况": { path: "identity.marital_status", value: (p) => p.identity?.marital_status },
  "婚姻状态": { path: "identity.marital_status", value: (p) => p.identity?.marital_status },
  "手机号": { path: "contact.mobile", value: (p) => p.contact?.mobile },
  "手机号码": { path: "contact.mobile", value: (p) => p.contact?.mobile },
  "手机": { path: "contact.mobile", value: (p) => p.contact?.mobile },
  "手机区号": { path: "contact.mobile_country_code", value: () => "中国大陆（+86）" },
  "国际区号": { path: "contact.mobile_country_code", value: () => "中国大陆（+86）" },
  "国家代码": { path: "contact.mobile_country_code", value: () => "中国大陆（+86）" },
  "区号": { path: "contact.mobile_country_code", value: () => "中国大陆（+86）" },
  "电子邮箱": { path: "contact.email", value: (p) => p.contact?.email },
  "邮箱": { path: "contact.email", value: (p) => p.contact?.email },
  "现居城市": { path: "contact.current_city", value: (p) => p.contact?.current_city },
  "现居住地": { path: "contact.current_city", value: (p) => p.contact?.current_city },
  "现居地址": { path: "contact.current_address", value: (p) => p.contact?.current_address },
  "现居住地省份": { path: "contact.current_city[province]", value: (p) => extractLocationComponents(p.contact?.current_city || p.contact?.current_address).province },
  "现居住地城市": { path: "contact.current_city[city]", value: (p) => extractLocationComponents(p.contact?.current_city || p.contact?.current_address).city },
  "现居住地(省)": { path: "contact.current_city[province]", value: (p) => extractLocationComponents(p.contact?.current_city || p.contact?.current_address).province },
  "现居住地(市)": { path: "contact.current_city[city]", value: (p) => extractLocationComponents(p.contact?.current_city || p.contact?.current_address).city },
  "紧急联系人": { path: "contact.emergency_contact_name", value: (p) => p.contact?.emergency_contact_name },
  "紧急联系人姓名": { path: "contact.emergency_contact_name", value: (p) => p.contact?.emergency_contact_name },
  "紧急联系人电话": { path: "contact.emergency_contact_phone", value: (p) => p.contact?.emergency_contact_phone },
  "紧急联系人手机": { path: "contact.emergency_contact_phone", value: (p) => p.contact?.emergency_contact_phone },
  "紧急联系人关系": { path: "contact.emergency_contact_relation", value: (p) => p.contact?.emergency_contact_relation },
  "与紧急联系人关系": { path: "contact.emergency_contact_relation", value: (p) => p.contact?.emergency_contact_relation },
  "家庭电话": { path: "contact.home_phone", value: (p) => p.contact?.home_phone },
  "固定电话": { path: "contact.home_phone", value: (p) => p.contact?.home_phone },
  "座机": { path: "contact.home_phone", value: (p) => p.contact?.home_phone },
  "邮编": { path: "contact.postal_code", value: (p) => p.contact?.postal_code },
  "邮政编码": { path: "contact.postal_code", value: (p) => p.contact?.postal_code },
  "国籍": { path: "identity.nationality", value: (p) => p.identity?.nationality },
  "国籍地区": { path: "identity.nationality", value: (p) => p.identity?.nationality },
  "QQ": { path: "contact.qq", value: (p) => p.contact?.qq },
  "微信": { path: "contact.wechat", value: (p) => p.contact?.wechat },
  "微信号": { path: "contact.wechat", value: (p) => p.contact?.wechat },
  "籍贯": { path: "soe_extended.native_place", value: (p) => p.soe_extended?.native_place },
  "籍贯所在地": { path: "soe_extended.native_place", value: (p) => p.soe_extended?.native_place },
  "籍贯省份": { path: "soe_extended.native_place[province]", value: (p) => extractLocationComponents(p.soe_extended?.native_place).province },
  "籍贯城市": { path: "soe_extended.native_place[city]", value: (p) => extractLocationComponents(p.soe_extended?.native_place).city },
  "籍贯区县": { path: "soe_extended.native_place[district]", value: (p) => extractLocationComponents(p.soe_extended?.native_place).district },
  "籍贯(省)": { path: "soe_extended.native_place[province]", value: (p) => extractLocationComponents(p.soe_extended?.native_place).province },
  "籍贯(市)": { path: "soe_extended.native_place[city]", value: (p) => extractLocationComponents(p.soe_extended?.native_place).city },
  "籍贯(区/县)": { path: "soe_extended.native_place[district]", value: (p) => extractLocationComponents(p.soe_extended?.native_place).district },
  "户口所在地": { path: "soe_extended.household_registration", value: (p) => p.soe_extended?.household_registration },
  "户籍所在地": { path: "soe_extended.household_registration", value: (p) => p.soe_extended?.household_registration },
  "户籍地址": { path: "soe_extended.household_registration", value: (p) => p.soe_extended?.household_registration },
  "户籍省份": { path: "soe_extended.household_registration[province]", value: (p) => extractLocationComponents(p.soe_extended?.household_registration).province },
  "户籍城市": { path: "soe_extended.household_registration[city]", value: (p) => extractLocationComponents(p.soe_extended?.household_registration).city },
  "户籍区县": { path: "soe_extended.household_registration[district]", value: (p) => extractLocationComponents(p.soe_extended?.household_registration).district },
  "户籍所在地省份": { path: "soe_extended.household_registration[province]", value: (p) => extractLocationComponents(p.soe_extended?.household_registration).province },
  "户籍所在地城市": { path: "soe_extended.household_registration[city]", value: (p) => extractLocationComponents(p.soe_extended?.household_registration).city },
  "户籍所在地(省)": { path: "soe_extended.household_registration[province]", value: (p) => extractLocationComponents(p.soe_extended?.household_registration).province },
  "户籍所在地(市)": { path: "soe_extended.household_registration[city]", value: (p) => extractLocationComponents(p.soe_extended?.household_registration).city },
  "户口类型": { path: "soe_extended.household_type", value: (p) => p.soe_extended?.household_type },
  "户口性质": { path: "soe_extended.household_type", value: (p) => p.soe_extended?.household_type },
  "政治面貌": { path: "soe_extended.political_status", value: (p) => p.soe_extended?.political_status },
  "入党时间": { path: "soe_extended.join_party_date", value: (p) => display(p.soe_extended?.join_party_date) },
  "入团时间": { path: "soe_extended.join_party_date", value: (p) => display(p.soe_extended?.join_party_date) },
  "身高": { path: "soe_extended.height_cm", value: (p) => p.soe_extended?.height_cm },
  "体重": { path: "soe_extended.weight_kg", value: (p) => p.soe_extended?.weight_kg },
  "血型": { path: "soe_extended.blood_type", value: (p) => p.soe_extended?.blood_type },
  "左眼视力": { path: "soe_extended.eyesight_left", value: (p) => p.soe_extended?.eyesight_left },
  "右眼视力": { path: "soe_extended.eyesight_right", value: (p) => p.soe_extended?.eyesight_right },
  "犯罪记录": { path: "soe_extended.has_criminal_record", value: (p) => p.soe_extended?.has_criminal_record },
  "有无犯罪记录": { path: "soe_extended.has_criminal_record", value: (p) => p.soe_extended?.has_criminal_record },
  "处分记录": { path: "soe_extended.has_disciplinary_record", value: (p) => p.soe_extended?.has_disciplinary_record },
  "有无处分": { path: "soe_extended.has_disciplinary_record", value: (p) => p.soe_extended?.has_disciplinary_record },
  "是否服从分配": { path: "soe_extended.can_relocate", value: (p) => p.soe_extended?.can_relocate },
  "是否服从调剂": { path: "soe_extended.can_relocate", value: (p) => p.soe_extended?.can_relocate },
  "服从调剂": { path: "soe_extended.can_relocate", value: (p) => p.soe_extended?.can_relocate },
  "服从分配": { path: "soe_extended.can_relocate", value: (p) => p.soe_extended?.can_relocate },
  "期望薪资": { path: "soe_extended.expected_salary", value: (p) => p.soe_extended?.expected_salary },
  "期望月薪": { path: "soe_extended.expected_salary", value: (p) => p.soe_extended?.expected_salary },
  "期望年薪": { path: "soe_extended.expected_salary", value: (p) => p.soe_extended?.expected_salary },
  "最早到岗": { path: "soe_extended.available_date", value: (p) => display(p.soe_extended?.available_date) },
  "到岗时间": { path: "soe_extended.available_date", value: (p) => display(p.soe_extended?.available_date) },
  "最早到岗时间": { path: "soe_extended.available_date", value: (p) => display(p.soe_extended?.available_date) },
  "推荐人": { path: "soe_extended.referrer_name", value: (p) => p.soe_extended?.referrer_name },
  "推荐人姓名": { path: "soe_extended.referrer_name", value: (p) => p.soe_extended?.referrer_name },
  "推荐人工号": { path: "soe_extended.referrer_employee_id", value: (p) => p.soe_extended?.referrer_employee_id },
  "内推人": { path: "soe_extended.referrer_name", value: (p) => p.soe_extended?.referrer_name },
  "内推工号": { path: "soe_extended.referrer_employee_id", value: (p) => p.soe_extended?.referrer_employee_id },
  "自我评价": { path: "soe_extended.personal_statement", value: (p) => p.soe_extended?.personal_statement },
  "个人陈述": { path: "soe_extended.personal_statement", value: (p) => p.soe_extended?.personal_statement },
  "个人简介": { path: "soe_extended.personal_statement", value: (p) => p.soe_extended?.personal_statement },
  "个人总结": { path: "soe_extended.personal_statement", value: (p) => p.soe_extended?.personal_statement },
  "兴趣爱好": { path: "soe_extended.hobbies", value: (p) => p.soe_extended?.hobbies },
  "爱好特长": { path: "soe_extended.hobbies", value: (p) => p.soe_extended?.hobbies },
  "特长": { path: "soe_extended.strengths", value: (p) => p.soe_extended?.strengths },
  "个人特长": { path: "soe_extended.strengths", value: (p) => p.soe_extended?.strengths },
  "个人优势": { path: "soe_extended.strengths", value: (p) => p.soe_extended?.strengths },
  "海外经历": { path: "soe_extended.has_overseas_background", value: (p) => p.soe_extended?.has_overseas_background },
  "有无海外经历": { path: "soe_extended.has_overseas_background", value: (p) => p.soe_extended?.has_overseas_background },
  "海外亲属": { path: "soe_extended.overseas_relatives", value: (p) => p.soe_extended?.overseas_relatives },
  "有无海外亲属": { path: "soe_extended.overseas_relatives", value: (p) => p.soe_extended?.overseas_relatives },
  "驾照": { path: "soe_extended.driving_license", value: (p) => p.soe_extended?.driving_license },
  "驾驶证": { path: "soe_extended.driving_license", value: (p) => p.soe_extended?.driving_license },
  "驾照类型": { path: "soe_extended.driving_license", value: (p) => p.soe_extended?.driving_license },
  "计算机水平": { path: "soe_extended.computer_proficiency", value: (p) => p.soe_extended?.computer_proficiency },
  "计算机等级": { path: "soe_extended.computer_proficiency", value: (p) => p.soe_extended?.computer_proficiency },
  "普通话等级": { path: "soe_extended.mandarin_level", value: (p) => p.soe_extended?.mandarin_level },
  "普通话水平": { path: "soe_extended.mandarin_level", value: (p) => p.soe_extended?.mandarin_level },
  "毕业年份": { path: "campus_context.graduation_year", value: (p) => p.campus_context?.graduation_year },
  "四级成绩": { path: "campus_context.cet4_score", value: (p) => p.campus_context?.cet4_score },
  "六级成绩": { path: "campus_context.cet6_score", value: (p) => p.campus_context?.cet6_score },
  "四级分数": { path: "campus_context.cet4_score", value: (p) => p.campus_context?.cet4_score },
  "六级分数": { path: "campus_context.cet6_score", value: (p) => p.campus_context?.cet6_score },
  "cet4": { path: "campus_context.cet4_score", value: (p) => p.campus_context?.cet4_score },
  "cet6": { path: "campus_context.cet6_score", value: (p) => p.campus_context?.cet6_score },
  "雅思": { path: "campus_context.ielts_score", value: (p) => p.campus_context?.ielts_score },
  "雅思成绩": { path: "campus_context.ielts_score", value: (p) => p.campus_context?.ielts_score },
  "托福": { path: "campus_context.toefl_score", value: (p) => p.campus_context?.toefl_score },
  "托福成绩": { path: "campus_context.toefl_score", value: (p) => p.campus_context?.toefl_score },
  "学生干部": { path: "campus_context.student_cadre", value: (p) => p.campus_context?.student_cadre },
  "是否学生干部": { path: "campus_context.student_cadre", value: (p) => p.campus_context?.student_cadre },
  "应届生": { path: "campus_context.is_fresh_graduate", value: (p) => p.campus_context?.is_fresh_graduate },
  "是否应届毕业生": { path: "campus_context.is_fresh_graduate", value: (p) => p.campus_context?.is_fresh_graduate },
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
  "绩点": { path: "education[highest].gpa", value: (p) => highest(p.education)?.gpa },
  "gpa": { path: "education[highest].gpa", value: (p) => highest(p.education)?.gpa },
  "成绩绩点": { path: "education[highest].gpa", value: (p) => highest(p.education)?.gpa },
  "院校类型": { path: "education[highest].school_type", value: (p) => highest(p.education)?.school_type },
  "院校性质": { path: "education[highest].school_type", value: (p) => highest(p.education)?.school_type },
  "学校类型": { path: "education[highest].school_type", value: (p) => highest(p.education)?.school_type },
  "学习方式": { path: "education[highest].study_mode", value: (p) => highest(p.education)?.study_mode },
  "学习形式": { path: "education[highest].study_mode", value: (p) => highest(p.education)?.study_mode },
  "培养方式": { path: "education[highest].study_mode", value: (p) => highest(p.education)?.study_mode },
  "班级": { path: "education[highest].class_name", value: (p) => highest(p.education)?.class_name },
  "所在班级": { path: "education[highest].class_name", value: (p) => highest(p.education)?.class_name },
  "学号": { path: "education[highest].student_id", value: (p) => highest(p.education)?.student_id },
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
  const normLabel = normalize(field.label);
  const fullValue = normalize(`${field.label}${field.name}`);

  // 1. Exact match on field.label first
  const exactLabelKey = Object.keys(rules).find((key) => normalize(key) === normLabel);
  if (exactLabelKey) return exactLabelKey;

  // 2. Exact match on fullValue
  const exactFullKey = Object.keys(rules).find((key) => normalize(key) === fullValue);
  if (exactFullKey) return exactFullKey;

  // 3. Guardrail against third-party / relation fields matching candidate identity
  const isEmergency = fullValue.includes("紧急");
  const isReferrer = fullValue.includes("推荐") || fullValue.includes("内推");
  const isFamily = fullValue.includes("父亲") || fullValue.includes("母亲") || fullValue.includes("配偶") || fullValue.includes("子女") || fullValue.includes("家属");
  const isSupervisor = fullValue.includes("证明人") || fullValue.includes("导师") || fullValue.includes("领导");

  // 4. Find all candidate keys that are substrings of fullValue
  const candidateKeys = Object.keys(rules).filter((key) => {
    const normK = normalize(key);
    if (normK.length < 2) return false;
    if (!fullValue.includes(normK)) return false;

    // Guardrail filtering: emergency contact cannot match general name/phone
    if (isEmergency && !normK.includes("紧急")) return false;
    if (isReferrer && !normK.includes("推荐") && !normK.includes("内推")) return false;
    if (isFamily && !normK.includes("父") && !normK.includes("母") && !normK.includes("配偶") && !normK.includes("子女")) return false;
    if (isSupervisor) return false;

    return true;
  });

  if (candidateKeys.length === 0) return "";

  // Sort by length descending (longest / most specific rule wins!)
  candidateKeys.sort((a, b) => normalize(b).length - normalize(a).length);
  return candidateKeys[0];
}

function fieldRule(field: PageField, section?: string, profile?: CandidateProfile): { rule: { path: string; value: (profile: CandidateProfile) => unknown }; source: MappingSource } | undefined {
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

  if (profile?.soe_extended?.custom_fields && typeof profile.soe_extended.custom_fields === "object") {
    const customFields = profile.soe_extended.custom_fields as Record<string, unknown>;
    const value = normalize(`${field.label}${field.name}`);
    for (const [key, val] of Object.entries(customFields)) {
      const normKey = normalize(key);
      if (normKey && (value === normKey || value.includes(normKey))) {
        return {
          rule: {
            path: `soe_extended.custom_fields["${key}"]`,
            value: () => val,
          },
          source: "base",
        };
      }
    }
  }

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
      const selected = fieldRule(field, section, profile);
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
    const selected = fieldRule(field, section, profile);
    if (!selected) return { field, decision: "review", reason: "没有唯一的字段规则，请手动选择资料" };
    const slotKey = selected.source === "base" ? "" : `${selected.source}:${selected.rule.path.match(/\.(\w+)$/)?.[1] || selected.rule.path}`;
    const index = slotKey ? occurrences[slotKey] || 0 : undefined;
    if (slotKey) occurrences[slotKey] = (index || 0) + 1;
    const recordIndex = index === undefined ? undefined : recordIndexFor(selected.source, index);
    const profilePath = pathForIndex(selected.rule.path, selected.source, recordIndex);
    let value = recordIndex === undefined ? selected.rule.value(profile) : valueForRecord(selected.rule, profile, selected.source, recordIndex);

    // Multi-select location cascade handling:
    if (field.kind === "select" && (selected.rule.path === "soe_extended.native_place" || selected.rule.path.startsWith("soe_extended.native_place["))) {
      const loc = extractLocationComponents(profile?.soe_extended?.native_place);
      const locIndex = occurrences["cascade:native_place"] || 0;
      occurrences["cascade:native_place"] = locIndex + 1;
      if (locIndex === 0) value = loc.province;
      else if (locIndex === 1) value = loc.city;
      else value = loc.district;
    } else if (field.kind === "select" && (selected.rule.path === "soe_extended.household_registration" || selected.rule.path.startsWith("soe_extended.household_registration["))) {
      const loc = extractLocationComponents(profile?.soe_extended?.household_registration);
      const locIndex = occurrences["cascade:household_registration"] || 0;
      occurrences["cascade:household_registration"] = locIndex + 1;
      if (locIndex === 0) value = loc.province;
      else if (locIndex === 1) value = loc.city;
      else value = loc.district;
    } else if (field.kind === "select" && (selected.rule.path === "contact.current_city" || selected.rule.path.startsWith("contact.current_city["))) {
      const loc = extractLocationComponents(profile?.contact?.current_city || profile?.contact?.current_address);
      const locIndex = occurrences["cascade:current_city"] || 0;
      occurrences["cascade:current_city"] = locIndex + 1;
      if (locIndex === 0) value = loc.province;
      else if (locIndex === 1) value = loc.city;
      else value = loc.district;
    }

    // Compound fields: Select for ID number is actually ID type!
    if (field.kind === "select" && profilePath === "identity.id_number") {
      value = profile?.identity?.id_type || "国内身份证或护照（含港澳台）";
    }
    // Compound fields: Select for Mobile is actually country code!
    if (field.kind === "select" && profilePath === "contact.mobile") {
      value = "中国大陆（+86）";
    }

    if (value === undefined || value === null || String(value).trim() === "") return { field, decision: "review", profilePath, reason: `资料缺少：${profilePath}` };
    if (field.kind === "choice") return { field, decision: "review", profilePath, proposedValue: String(value), reason: "选择控件需要确认具体选项" };
    if (field.kind === "file") return { field, decision: "review", profilePath, proposedValue: String(value), reason: "附件需要在浏览器中选择文件" };
    let proposedValue = formatValue(profilePath, value);
    if (field.type === "date" && /^\d{4}-\d{2}$/.test(proposedValue)) return { field, decision: "review", profilePath, proposedValue, reason: "资料只有年月，日期控件需要完整日期" };

    if (field.kind === "select" && field.options && field.options.length > 0) {
      const matched = matchOptionText(field.options, proposedValue);
      if (matched) {
        proposedValue = matched;
      }
    }

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
