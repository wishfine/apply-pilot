import pytest
from applypilot.modules.apply.readiness import FormRequirementDetector


def test_native_required_attribute():
    detector = FormRequirementDetector()
    assert detector.is_field_required({"required": ""}, "姓名") is True
    assert detector.is_field_required({"required": True}, "姓名") is True
    assert detector.is_field_required({"required": "required"}, "姓名") is True
    # Case-insensitive false should not be considered required
    assert detector.is_field_required({"required": "false"}, "姓名") is False
    assert detector.is_field_required({"required": "False"}, "姓名") is False
    assert detector.is_field_required({"required": "FALSE"}, "姓名") is False


def test_native_aria_required_attribute():
    detector = FormRequirementDetector()
    assert detector.is_field_required({"aria-required": "true"}, "手机号") is True
    assert detector.is_field_required({"aria-required": "True"}, "手机号") is True
    assert detector.is_field_required({"aria-required": True}, "手机号") is True
    assert detector.is_field_required({"aria-required": "false"}, "手机号") is False


def test_label_asterisk_indicators():
    detector = FormRequirementDetector()
    assert detector.is_field_required({}, "* 姓名") is True
    assert detector.is_field_required({}, "手机号 *") is True
    assert detector.is_field_required({}, "*电子邮箱") is True
    assert detector.is_field_required({}, "当前城市*") is True


def test_label_required_text():
    detector = FormRequirementDetector()
    assert detector.is_field_required({}, "期望薪资(必填)") is True
    assert detector.is_field_required({}, "求职状态（必填）") is True
    assert detector.is_field_required({}, "到岗时间 必填") is True


def test_explicit_optional_downgrade_highest_priority():
    detector = FormRequirementDetector()
    # Explicit optional markers override native attributes, asterisks, and outer HTML
    assert detector.is_field_required({"required": True}, "个人网站 (选填)") is False
    assert detector.is_field_required({"aria-required": "true"}, "英文名 （选填）") is False
    assert detector.is_field_required({}, "博客链接 (optional)") is False
    assert detector.is_field_required({}, "GitHub [选填]") is False
    assert detector.is_field_required({}, "社交账号 【选填】") is False
    assert (
        detector.is_field_required(
            {"required": True},
            "* 备注 (选填)",
            outer_html='<div class="is-required"></div>',
        )
        is False
    )


def test_fei_bi_tian_optional_marker():
    detector = FormRequirementDetector()
    # '非必填' contains '必填', but must be treated as optional
    assert detector.is_field_required({}, "个人网站 (非必填)") is False
    assert detector.is_field_required({}, "家庭住址（非必填）") is False
    assert detector.is_field_required({}, "备注 [非必填]") is False
    assert detector.is_field_required({}, "微信 【非必填】") is False
    assert detector.is_field_required({"required": True}, "* 个人网站 (非必填)") is False


def test_outer_html_element_ui_required():
    detector = FormRequirementDetector()
    outer_html = '<div class="el-form-item is-required"><label class="el-form-item__label">毕业院校</label></div>'
    assert detector.is_field_required({}, "毕业院校", outer_html=outer_html) is True

    # Single quotes support
    outer_html_single = "<div class='el-form-item is-required'><label class='el-form-item__label'>毕业院校</label></div>"
    assert detector.is_field_required({}, "毕业院校", outer_html=outer_html_single) is True


def test_outer_html_ant_design_required():
    detector = FormRequirementDetector()
    outer_html = (
        '<div class="ant-form-item-label ant-form-item-required">'
        '<label title="最高学历">最高学历</label></div>'
    )
    assert detector.is_field_required({}, "最高学历", outer_html=outer_html) is True

    outer_html_single = (
        "<div class='ant-form-item-label ant-form-item-required'>"
        "<label title='最高学历'>最高学历</label></div>"
    )
    assert detector.is_field_required({}, "最高学历", outer_html=outer_html_single) is True


def test_outer_html_star_or_must_span():
    detector = FormRequirementDetector()
    html_star = '<label><span class="star">*</span>专业名称</label>'
    assert detector.is_field_required({}, "专业名称", outer_html=html_star) is True

    html_req = "<label><span class='required'>*</span>入学时间</label>"
    assert detector.is_field_required({}, "入学时间", outer_html=html_req) is True

    html_must = '<label><span class="must">*</span>毕业时间</label>'
    assert detector.is_field_required({}, "毕业时间", outer_html=html_must) is True


def test_normal_unrequired_fields_return_false():
    detector = FormRequirementDetector()
    outer_html = '<div class="form-group"><label>技能证书</label><input type="text" /></div>'
    assert detector.is_field_required({"type": "text", "name": "cert"}, "技能证书", outer_html=outer_html) is False


def test_graceful_empty_and_none_handling():
    detector = FormRequirementDetector()
    assert detector.is_field_required({}, "") is False
    assert detector.is_field_required({}, None) is False
    assert detector.is_field_required({}, None, outer_html=None) is False
