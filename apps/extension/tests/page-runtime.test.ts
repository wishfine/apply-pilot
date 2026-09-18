/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fillField, installHarvestInterceptor, scanPage } from "../runtime/page";

beforeEach(() => {
  Object.defineProperty(globalThis, "CSS", { value: { escape: (value: string) => value.replace(/[^a-zA-Z0-9_-]/g, "_") }, configurable: true });
  Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", { configurable: true, value: () => ({ width: 200, height: 24, top: 0, left: 0, right: 200, bottom: 24 }) });
  Object.defineProperty(HTMLElement.prototype, "getClientRects", { configurable: true, value: () => [{ width: 200, height: 24 }] });
});

afterEach(() => { document.body.innerHTML = ""; });

describe("page runtime", () => {
  it("scans visible controls and fills through the native value setter", () => {
    document.body.innerHTML = `<form><label for="name">姓名</label><input id="name" name="name" required><label for="degree">学历</label><select id="degree"><option value="">请选择</option><option value="master">硕士</option></select></form>`;
    const result = scanPage();
    expect(result.pageState).toBe("form");
    expect(result.fields.map((field) => field.label)).toEqual(["姓名", "学历"]);
    const receipt = fillField(result.fields[0].ref, "张三");
    expect(receipt).toMatchObject({ ok: true, value: "张三" });
    expect(document.querySelector<HTMLInputElement>("#name")?.value).toBe("张三");
  });

  it("does not expose password fields and recognizes delayed login surfaces", () => {
    document.body.innerHTML = `<h2>欢迎登录</h2><input type="password" placeholder="密码"><input type="tel" placeholder="手机号">`;
    window.history.replaceState({}, "", "/xyzlogin");
    const result = scanPage();
    expect(result.pageState).toBe("login");
    expect(result.fields.some((field) => field.type === "password")).toBe(false);
  });

  it("fills controls inside an open shadow root", () => {
    const host = document.createElement("profile-field");
    const shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `<input placeholder="姓名">`;
    document.body.append(host);
    const result = scanPage();
    expect(result.fields).toHaveLength(1);
    const receipt = fillField(result.fields[0].ref, "张三");
    expect(receipt).toMatchObject({ ok: true, value: "张三" });
    expect(shadow.querySelector<HTMLInputElement>("input")?.value).toBe("张三");
  });

  it("keeps a hidden file input when its visible upload drop zone is labeled", () => {
    document.body.innerHTML = `<label>上传简历<input type="file" style="display:none"></label>`;
    const result = scanPage();
    expect(result.fields).toMatchObject([{ kind: "file", label: "上传简历" }]);
  });

  it("extracts a real label when the control is next to a Chinese placeholder", () => {
    document.body.innerHTML = `<nav><a>个人信息</a><a>实习经历</a></nav><div class="row"><span>姓名</span><input placeholder="请输入"></div>`;
    const result = scanPage();
    expect(result.fields[0]).toMatchObject({ label: "姓名" });
    expect(result.sections.map((section) => section.label)).toEqual(["个人信息", "实习经历"]);
  });

  it("uses the visible section heading when navigation does not expose an active state", () => {
    document.body.innerHTML = `<h1>实习经历</h1><div class="row"><span>公司名称</span><input placeholder="请输入"></div>`;
    const result = scanPage();
    expect(result.activeSection).toBe("实习经历");
  });

  it("recognizes project navigation and headings as a separate section", () => {
    document.body.innerHTML = `<nav><a class="nav-item active">项目经历</a></nav><h1>项目经历</h1><input aria-label="项目名称">`;
    const result = scanPage();
    expect(result.sections).toMatchObject([{ label: "项目经历", active: true }]);
    expect(result.activeSection).toBe("项目经历");
  });

  it("does not treat a generic ellipsis placeholder as a field label", () => {
    document.body.innerHTML = `<div class="row"><span>邮箱</span><input placeholder="请输入..."></div>`;
    expect(scanPage().fields[0].label).toBe("邮箱");
  });

  it("detects required markers without treating every empty input as required", () => {
    document.body.innerHTML = `<div class="form-item"><span>* 姓名</span><input placeholder="请输入"></div><div class="form-item"><span>QQ</span><input placeholder="请输入"></div>`;
    expect(scanPage().fields.map((field) => field.required)).toEqual([true, false]);
  });

  it("assigns fields to their nearest preceding section heading", () => {
    document.body.innerHTML = `<h2>教育经历</h2><input aria-label="学院名称"><h2>实习经历</h2><input aria-label="单位名称">`;
    expect(scanPage().fields.map((field) => field.section)).toEqual(["教育经历", "实习经历"]);
  });

  it("recognizes section title classes used by component libraries", () => {
    document.body.innerHTML = `<div class="section-title">项目经历</div><input aria-label="项目名称">`;
    expect(scanPage().fields[0].section).toBe("项目经历");
  });

  it("keeps a stable record group for repeated experience containers", () => {
    document.body.innerHTML = `<h2>实习经历</h2><div class="experience-record" data-record-id="exp-1"><input aria-label="单位名称"></div><div class="experience-record" data-record-id="exp-2"><input aria-label="单位名称"></div>`;
    expect(scanPage().fields.map((field) => field.recordGroup)).toEqual(["实习经历:exp-1", "实习经历:exp-2"]);
  });

  it("detects required markers on parent rows and associated labels", () => {
    document.body.innerHTML = `<div class="row is-required"><span>身份证号</span><input aria-label="身份证号"></div><div class="row" aria-required="true"><span>出生日期</span><input aria-label="出生日期"></div><label for="email"><span class="required-star">*</span> 邮箱</label><input id="email" aria-label="邮箱"><div class="row"><span>QQ（选填）</span><input aria-label="QQ"></div>`;
    expect(scanPage().fields.map((field) => field.required)).toEqual([true, true, true, false]);
  });

  it("does not mistake unrelated asterisks for required markers", () => {
    document.body.innerHTML = `<div class="row"><span>项目名称</span><span>匹配规则：*</span><input aria-label="项目名称"></div>`;
    expect(scanPage().fields[0].required).toBe(false);
  });

  it("fills select dropdowns using political status synonym matching", () => {
    document.body.innerHTML = `
      <form>
        <label for="political">政治面貌</label>
        <select id="political">
          <option value="">--请选择--</option>
          <option value="1">中国共产党党员</option>
          <option value="2">中国共产党预备党员</option>
          <option value="3">中国共产主义青年团团员</option>
          <option value="4">群众</option>
        </select>
      </form>
    `;
    const scan = scanPage();
    const receipt = fillField(scan.fields[0].ref, "共青团员");
    expect(receipt.ok).toBe(true);
    expect(document.querySelector<HTMLSelectElement>("#political")?.value).toBe("3");
  });

  it("disambiguates compound rows for ID number and mobile phone", () => {
    document.body.innerHTML = `
      <div class="form-item">
        <label>* 身份证号</label>
        <select id="id-type">
          <option value="1">国内身份证或护照（含港澳台）</option>
          <option value="2">国外身份证</option>
        </select>
        <input id="id-number" type="text" />
      </div>
      <div class="form-item">
        <label>* 手机号码</label>
        <select id="country-code">
          <option value="86">中国大陆（+86）</option>
          <option value="other">其他地区手机号</option>
        </select>
        <input id="mobile" type="text" />
      </div>
    `;
    const scan = scanPage();
    expect(scan.fields.map((f) => f.label)).toEqual([
      "证件类型",
      "* 身份证号",
      "手机区号",
      "* 手机号码",
    ]);

    // Test filling compound select and inputs
    const fillType = fillField(scan.fields[0].ref, "居民身份证");
    expect(fillType.ok).toBe(true);
    expect(document.querySelector<HTMLSelectElement>("#id-type")?.value).toBe("1");

    const fillId = fillField(scan.fields[1].ref, "110101199003072345");
    expect(fillId.ok).toBe(true);
    expect(document.querySelector<HTMLInputElement>("#id-number")?.value).toBe("110101199003072345");

    const fillCode = fillField(scan.fields[2].ref, "+86");
    expect(fillCode.ok).toBe(true);
    expect(document.querySelector<HTMLSelectElement>("#country-code")?.value).toBe("86");
  });

  it("disambiguates cascading selects for location like native place", () => {
    document.body.innerHTML = `
      <div class="form-item">
        <label>* 籍贯</label>
        <select id="prov">
          <option value="">--请选择--</option>
          <option value="bj">北京</option>
          <option value="hb">湖北</option>
        </select>
        <select id="city">
          <option value="">--请选择--</option>
          <option value="bj-dc">北京市东城区</option>
          <option value="hb-wh">武汉市</option>
        </select>
      </div>
    `;
    const scan = scanPage();
    expect(scan.fields.map((f) => f.label)).toEqual(["籍贯省份", "籍贯城市"]);

    const fillProv = fillField(scan.fields[0].ref, "北京");
    expect(fillProv.ok).toBe(true);
    expect(document.querySelector<HTMLSelectElement>("#prov")?.value).toBe("bj");

    const fillCity = fillField(scan.fields[1].ref, "北京市东城区");
    expect(fillCity.ok).toBe(true);
    expect(document.querySelector<HTMLSelectElement>("#city")?.value).toBe("bj-dc");
  });

  it("disambiguates table layout compound controls for ID number and mobile phone with required marking", () => {
    document.body.innerHTML = `
      <table>
        <tr>
          <td><span class="required">*</span> 身份证号</td>
          <td>
            <select id="id-type">
              <option value="id">国内身份证或护照（含港澳台）</option>
              <option value="passport">护照</option>
            </select>
            <input id="id-num" type="text" />
          </td>
        </tr>
        <tr>
          <td><span class="required">*</span> 手机号码</td>
          <td>
            <select id="mobile-code">
              <option value="86">中国大陆（+86）</option>
              <option value="other">其他地区</option>
            </select>
            <input id="mobile-num" type="text" />
            <div>手机号码用于接收应聘相关信息，请务必正确填写。</div>
          </td>
        </tr>
      </table>
    `;
    const scan = scanPage();
    expect(scan.fields.map((f) => f.label)).toEqual([
      "证件类型",
      "* 身份证号",
      "手机区号",
      "* 手机号码",
    ]);
    expect(scan.fields.map((f) => f.required)).toEqual([true, true, true, true]);

    const fillId = fillField(scan.fields[1].ref, "110101200105152345");
    expect(fillId.ok).toBe(true);
    expect(document.querySelector<HTMLInputElement>("#id-num")?.value).toBe("110101200105152345");

    const fillMobile = fillField(scan.fields[3].ref, "13800138000");
    expect(fillMobile.ok).toBe(true);
    expect(document.querySelector<HTMLInputElement>("#mobile-num")?.value).toBe("13800138000");
  });

  it("disambiguates split dropdowns for date of birth and fills year and month correctly", () => {
    document.body.innerHTML = `
      <table>
        <tr>
          <td><span class="star">*</span> 出生日期</td>
          <td>
            <select id="birth-year">
              <option value="">请选择</option>
              <option value="2028">2028年</option>
              <option value="2027">2027年</option>
              <option value="2001">2001年</option>
              <option value="2000">2000年</option>
            </select>
            年
            <select id="birth-month">
              <option value="">请选择</option>
              <option value="01">01月</option>
              <option value="02">02月</option>
              <option value="05">05月</option>
              <option value="12">12月</option>
            </select>
            月
          </td>
        </tr>
      </table>
    `;
    const scan = scanPage();
    expect(scan.fields.map((f) => f.label)).toEqual(["出生年份", "出生月份"]);
    expect(scan.fields.map((f) => f.required)).toEqual([true, true]);

    // Test filling year with "2001" matching "2001年"
    const fillYear = fillField(scan.fields[0].ref, "2001");
    expect(fillYear.ok).toBe(true);
    expect(document.querySelector<HTMLSelectElement>("#birth-year")?.value).toBe("2001");

    // Test filling month with "05" matching "05月"
    const fillMonth = fillField(scan.fields[1].ref, "05");
    expect(fillMonth.ok).toBe(true);
    expect(document.querySelector<HTMLSelectElement>("#birth-month")?.value).toBe("05");
  });

  it("intercepts next/submit click and renders harvest prompt modal when fields have values", () => {
    document.body.innerHTML = `
      <form>
        <label for="f_name">姓名</label>
        <input id="f_name" value="李四" />
        <button type="button" id="btn-next">下一步</button>
      </form>
    `;

    // Ensure flag is reset for test
    delete (window as unknown as { __applypilot_interceptor_installed?: boolean }).__applypilot_interceptor_installed;

    installHarvestInterceptor();

    const nextBtn = document.querySelector<HTMLButtonElement>("#btn-next")!;
    nextBtn.click();

    const modal = document.querySelector("#applypilot-harvest-modal");
    expect(modal).not.toBeNull();
    expect(modal?.textContent).toContain("ApplyPilot 档案自学习提醒");
    expect(modal?.querySelector("#ap-modal-sync")).not.toBeNull();
    expect(modal?.querySelector("#ap-modal-skip")).not.toBeNull();

    // Clicking skip closes the modal
    (modal?.querySelector("#ap-modal-skip") as HTMLButtonElement).click();
    expect(document.querySelector("#applypilot-harvest-modal")).toBeNull();
  });
});

