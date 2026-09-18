"""
字段注册表 (Field Registry)
提供中英文字段映射，将英文 YAML 路径映射到中文标签。
包含身份信息、联系方式、教育经历、国企扩充信息、校园招聘上下文等字段。
"""

from typing import List, Tuple, Optional, Dict

# (yaml_path, chinese_label, description)
FIELD_REGISTRY: List[Tuple[str, str, str]] = [
    # identity fields
    ("identity.name", "姓名", "姓名"),
    ("identity.gender", "性别 (男/女)", "性别 (男/女)"),
    ("identity.pinyin_first_name", "拼音名", "拼音名"),
    ("identity.pinyin_last_name", "拼音姓", "拼音姓"),
    ("identity.english_name", "英文名", "英文名"),
    ("identity.nationality", "国籍", "国籍"),
    ("identity.birth_date", "出生日期 (YYYY-MM-DD)", "出生日期 (YYYY-MM-DD)"),
    ("identity.birth_place", "出生地", "出生地 (NEW)"),
    ("identity.id_type", "证件类型", "证件类型"),
    ("identity.id_number", "身份证号", "身份证号"),
    ("identity.id_expiry_date", "证件有效期", "证件有效期 (NEW)"),
    ("identity.ethnicity", "民族", "民族"),
    ("identity.health_status", "健康状况", "健康状况"),
    ("identity.marital_status", "婚姻状况", "婚姻状况"),
    ("identity.photo_path", "证件照路径", "证件照路径 (NEW)"),

    # contact fields
    ("contact.mobile", "手机号", "手机号"),
    ("contact.email", "邮箱", "邮箱"),
    ("contact.current_city", "现居城市", "现居城市"),
    ("contact.current_address", "现居地址", "现居地址"),
    ("contact.qq", "QQ", "QQ"),
    ("contact.wechat", "微信", "微信"),
    ("contact.emergency_contact_name", "紧急联系人姓名", "紧急联系人姓名"),
    ("contact.emergency_contact_phone", "紧急联系人电话", "紧急联系人电话"),
    ("contact.emergency_contact_phone", "紧急联系方式", "紧急联系方式 (NEW)"),
    ("contact.emergency_contact_relation", "紧急联系人关系", "紧急联系人关系 (NEW)"),
    ("contact.home_phone", "家庭电话", "家庭电话 (NEW)"),
    ("contact.postal_code", "邮政编码", "邮政编码 (NEW)"),

    # education fields
    ("education[__HIGHEST__].school_name", "毕业院校", "毕业院校"),
    ("education[__HIGHEST__].education_level", "学历", "学历"),
    ("education[__HIGHEST__].academic_degree", "学位", "学位"),
    ("education[__HIGHEST__].major", "专业", "专业"),
    ("education[__HIGHEST__].department", "院系", "院系"),
    ("education[__HIGHEST__].start_date", "入学时间", "入学时间"),
    ("education[__HIGHEST__].end_date", "毕业时间", "毕业时间"),
    ("education[__HIGHEST__].gpa", "绩点", "绩点"),
    ("education[__HIGHEST__].gpa_scale", "绩点满分", "绩点满分"),
    ("education[__HIGHEST__].ranking_pct", "成绩排名", "成绩排名"),
    ("education[__HIGHEST__].thesis_title", "毕业论文题目", "毕业论文题目"),
    ("education[__HIGHEST__].school_type", "院校类型", "院校类型 (NEW, 985/211/双一流)"),
    ("education[__HIGHEST__].study_mode", "学习方式", "学习方式 (NEW, 全日制/非全日制)"),
    ("education[__HIGHEST__].class_name", "班级", "班级 (NEW)"),
    ("education[__HIGHEST__].student_id", "学号", "学号 (NEW)"),

    # soe_extended fields
    ("soe_extended.political_status", "政治面貌", "政治面貌"),
    ("soe_extended.join_party_date", "入党时间", "入党时间"),
    ("soe_extended.native_place", "籍贯", "籍贯"),
    ("soe_extended.household_registration", "户籍所在地", "户籍所在地"),
    ("soe_extended.household_type", "户口类型", "户口类型"),
    ("soe_extended.conflict_of_interest", "亲属利益冲突", "亲属利益冲突"),
    ("soe_extended.conflict_details", "利益冲突详情", "利益冲突详情"),
    ("soe_extended.height_cm", "身高", "身高 (NEW, cm)"),
    ("soe_extended.weight_kg", "体重", "体重 (NEW, kg)"),
    ("soe_extended.blood_type", "血型", "血型 (NEW)"),
    ("soe_extended.eyesight_left", "左眼视力", "左眼视力 (NEW)"),
    ("soe_extended.eyesight_right", "右眼视力", "右眼视力 (NEW)"),
    ("soe_extended.has_criminal_record", "有无犯罪记录", "有无犯罪记录 (NEW)"),
    ("soe_extended.has_disciplinary_record", "有无处分记录", "有无处分记录 (NEW)"),
    ("soe_extended.can_relocate", "是否服从分配", "是否服从分配 (NEW)"),
    ("soe_extended.expected_salary", "期望薪资", "期望薪资 (NEW)"),
    ("soe_extended.available_date", "最早到岗时间", "最早到岗时间 (NEW)"),
    ("soe_extended.referrer_name", "推荐人姓名", "推荐人姓名 (NEW)"),
    ("soe_extended.referrer_employee_id", "推荐人工号", "推荐人工号 (NEW)"),
    ("soe_extended.personal_statement", "个人陈述", "个人陈述 (NEW)"),
    ("soe_extended.strengths", "个人特长", "个人特长 (NEW)"),
    ("soe_extended.hobbies", "兴趣爱好", "兴趣爱好 (NEW)"),
    ("soe_extended.has_overseas_background", "有无海外背景", "有无海外背景 (NEW)"),
    ("soe_extended.overseas_relatives", "有无海外亲属", "有无海外亲属 (NEW)"),
    ("soe_extended.has_commercial_insurance", "有无商业保险", "有无商业保险 (NEW)"),
    ("soe_extended.driving_license", "驾照类型", "驾照类型 (NEW)"),
    ("soe_extended.computer_proficiency", "计算机水平", "计算机水平 (NEW)"),
    ("soe_extended.mandarin_level", "普通话等级", "普通话等级 (NEW)"),
    ("soe_extended.custom_fields", "自定义字段", "自定义字段 (NEW)"),

    # campus_context fields
    ("campus_context.graduation_year", "毕业年份", "毕业年份"),
    ("campus_context.graduation_month", "毕业月份", "毕业月份"),
    ("campus_context.employment_status", "就业状态", "就业状态"),
    ("campus_context.cet4_score", "四级成绩", "四级成绩"),
    ("campus_context.cet6_score", "六级成绩", "六级成绩"),
    ("campus_context.ielts_score", "雅思成绩", "雅思成绩"),
    ("campus_context.toefl_score", "托福成绩", "托福成绩"),
    ("campus_context.has_dispatch_qualification", "派遣资格", "派遣资格"),
    ("campus_context.putonghua_level", "普通话等级", "普通话等级 (NEW)"),
    ("campus_context.computer_rank", "计算机等级", "计算机等级 (NEW)"),
    ("campus_context.scholarship_info", "奖学金情况", "奖学金情况 (NEW)"),
    ("campus_context.student_cadre", "是否学生干部", "是否学生干部 (NEW)"),
    ("campus_context.is_fresh_graduate", "是否应届生", "是否应届生 (NEW)"),

    # family_members fields
    ("soe_extended.family_members[*].relation", "关系", "关系"),
    ("soe_extended.family_members[*].name", "姓名", "姓名"),
    ("soe_extended.family_members[*].political_status", "政治面貌", "政治面貌"),
    ("soe_extended.family_members[*].workplace", "工作单位", "工作单位"),
    ("soe_extended.family_members[*].title", "职务", "职务"),
    ("soe_extended.family_members[*].phone", "联系电话", "联系电话"),
    ("soe_extended.family_members[*].age", "年龄", "年龄 (NEW)"),
    ("soe_extended.family_members[*].id_number", "身份证号", "身份证号 (NEW)"),
    ("soe_extended.family_members[*].is_party_member", "是否党员", "是否党员 (NEW)")
]

_PATH_TO_CN_MAP: Optional[Dict[str, str]] = None
_CN_TO_PATH_MAP: Optional[Dict[str, str]] = None


def _init_maps() -> None:
    """初始化懒加载的映射字典。"""
    global _PATH_TO_CN_MAP, _CN_TO_PATH_MAP
    if _PATH_TO_CN_MAP is None or _CN_TO_PATH_MAP is None:
        _PATH_TO_CN_MAP = {}
        _CN_TO_PATH_MAP = {}
        for path, cn_label, _ in FIELD_REGISTRY:
            _PATH_TO_CN_MAP[path] = cn_label
            if cn_label not in _CN_TO_PATH_MAP:
                _CN_TO_PATH_MAP[cn_label] = path


def search(query: str) -> List[Tuple[str, str, str]]:
    """
    模糊查询字段。
    :param query: 模糊匹配的中文字符串或路径名。
    :return: 匹配的 (yaml_path, chinese_label, description) 列表。
    """
    query = query.lower()
    results = []
    for path, cn_label, desc in FIELD_REGISTRY:
        if query in path.lower() or query in cn_label or query in desc:
            results.append((path, cn_label, desc))
    return results


def path_to_cn(path: str) -> Optional[str]:
    """
    根据 YAML 路径查找对应的中文标签。
    :param path: 英文 YAML 路径，如 "identity.name"
    :return: 对应的中文标签，如果未找到则返回 None
    """
    _init_maps()
    if _PATH_TO_CN_MAP is not None:
        return _PATH_TO_CN_MAP.get(path)
    return None


def cn_to_path(label: str) -> Optional[str]:
    """
    根据中文标签查找对应的 YAML 路径。
    :param label: 中文标签，如 "姓名"
    :return: 对应的 YAML 路径，如果未找到则返回 None
    """
    _init_maps()
    if _CN_TO_PATH_MAP is not None:
        return _CN_TO_PATH_MAP.get(label)
    return None
