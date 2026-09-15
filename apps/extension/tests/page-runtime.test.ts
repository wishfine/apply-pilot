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
});
