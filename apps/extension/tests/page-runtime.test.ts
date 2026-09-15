/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fillField, scanPage } from "../runtime/page";

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
});
