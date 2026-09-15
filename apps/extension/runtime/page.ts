export type PageField = {
  ref: string;
  frameId?: number;
  label: string;
  name: string;
  type: string;
  kind: "text" | "textarea" | "select" | "choice" | "file" | "unsupported";
  required: boolean;
  value: string;
  options: string[];
};

export type PageSection = { ref: string; label: string; active: boolean };
export type PageScan = { url: string; title: string; fields: PageField[]; sections: PageSection[]; activeSection?: string; documentReady: boolean; pageState: "form" | "login" | "loading" | "empty"; embeddedFrameCount: number };
export type FillReceipt = { ok: boolean; message: string; value?: string };
export type FilePayload = { name: string; type: string; bytes: number[] };

/** This function is self-contained because Chrome serializes it for injection. */
export function scanPage(): PageScan {
  const visible = (element: Element) => {
    const node = element as HTMLElement;
    const style = getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
  };
  const clean = (value: string | null | undefined) => (value || "").replace(/\s+/g, " ").trim();
  const usefulLabel = (value: string, hint: string) => {
    const candidate = clean(value);
    if (!candidate) return "";
    if (/^(请输入|请选择|选择|上传文件|点击上传|点击选择|请填写|选填|必填)(?:\.\.\.|…)?$/i.test(candidate)) return "";
    return candidate.length <= 80 ? candidate : "";
  };
  const textWithoutControls = (node: Element) => {
    const copy = node.cloneNode(true) as Element;
    copy.querySelectorAll("input, textarea, select, button, [contenteditable='true'], [role='textbox'], [role='combobox'], [role='radio'], [role='checkbox']").forEach((control) => control.remove());
    return clean(copy.textContent);
  };
  const previousSiblingLabel = (element: Element, hint: string) => {
    let current: Element | null = element;
    for (let depth = 0; current && depth < 6; depth += 1) {
      const ancestor: HTMLElement | null = current.parentElement;
      if (!ancestor) break;
      const siblings: Element[] = Array.from(ancestor.children);
      const index = siblings.indexOf(current);
      for (let i = index - 1; i >= 0; i -= 1) {
        const candidate = usefulLabel(textWithoutControls(siblings[i]), hint);
        if (candidate) return candidate;
      }
      const preceding = current.previousElementSibling;
      const candidate = usefulLabel(preceding ? textWithoutControls(preceding) : "", hint);
      if (candidate) return candidate;
      current = ancestor;
    }
    return "";
  };
  const roots: ParentNode[] = [document];
  const visitShadow = (root: ParentNode) => {
    root.querySelectorAll("*").forEach((node) => {
      if (node.shadowRoot) {
        roots.push(node.shadowRoot);
        visitShadow(node.shadowRoot);
      }
    });
  };
  visitShadow(document);
  const candidates: Element[] = [];
  roots.forEach((root) => root.querySelectorAll("input, textarea, select, [contenteditable='true'], [role='textbox'], [role='combobox'], [role='radio'], [role='checkbox']").forEach((element) => candidates.push(element)));
  const fields: PageField[] = [];
  let sequence = 0;
  for (const element of Array.from(new Set(candidates))) {
    const control = element as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
    const type = String((control as HTMLInputElement).type || element.getAttribute("role") || "text").toLowerCase();
    const uploadHost = type === "file" ? element.closest("label, [role='button'], [class*='upload'], [class*='Upload']") : null;
    const inspectable = visible(element) || (type === "file" && uploadHost !== null && visible(uploadHost));
    if (!inspectable || (control as HTMLInputElement).disabled || element.getAttribute("aria-disabled") === "true") continue;
    if (["hidden", "password", "search"].includes(type)) continue;
    const hint = clean(element.getAttribute("aria-label") || element.getAttribute("placeholder") || element.getAttribute("name") || element.id);
    const ownerRoot = element.getRootNode() as Document | ShadowRoot;
    const associated = element.id ? ownerRoot.querySelector(`label[for="${CSS.escape(element.id)}"]`) : null;
    const container = element.closest("label, .form-item, .form-group, .field, [class*='field'], [class*='form']");
    const nearby = container?.querySelector("label, legend, .label, [class*='label']");
    const labelledBy = clean((element.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean).map((id) => ownerRoot.querySelector(`#${CSS.escape(id)}`)?.textContent || "").join(" "));
    const explicit = clean(element.getAttribute("data-label") || element.getAttribute("data-field-label") || element.getAttribute("title"));
    const label = usefulLabel(labelledBy, hint) || usefulLabel(associated?.textContent || "", hint) || usefulLabel(nearby?.textContent || "", hint) || usefulLabel(explicit, hint) || previousSiblingLabel(element, hint) || usefulLabel(hint, hint) || usefulLabel(uploadHost?.textContent || "", hint) || (type === "file" ? "附件上传" : "");
    if (!label) continue;
    let kind: PageField["kind"] = "unsupported";
    if (element instanceof HTMLSelectElement) kind = "select";
    else if (type === "file") kind = "file";
    else if (["checkbox", "radio"].includes(type) || ["checkbox", "radio"].includes(element.getAttribute("role") || "")) kind = "choice";
    else if (element instanceof HTMLTextAreaElement || element.getAttribute("contenteditable") === "true" || ["textbox", "combobox"].includes(element.getAttribute("role") || "")) kind = "textarea";
    else if (["text", "email", "tel", "number", "url", "date", "month", "time", "datetime-local"].includes(type)) kind = "text";
    if (kind === "unsupported") continue;
    const ref = `ap-${sequence++}`;
    element.setAttribute("data-applypilot-ref", ref);
    const options = element instanceof HTMLSelectElement ? Array.from(element.options).filter((option) => !option.disabled && clean(option.textContent)).map((option) => clean(option.textContent)) : [];
    const value = element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement ? control.value : clean(element.textContent);
    fields.push({ ref, label, name: clean(control.name || element.id || hint), type, kind, required: Boolean((control as HTMLInputElement).required || element.getAttribute("aria-required") === "true"), value, options });
  }
  const knownSections = ["个人信息", "求职意向", "教育经历", "实习经历", "项目经历", "在校实践", "获奖情况", "论文/专著", "证书", "其他信息", "简历附件"];
  const sections: PageSection[] = [];
  const sectionCandidates = document.querySelectorAll("a, button, [role='tab'], [role='menuitem'], [class*='menu-item'], [class*='nav-item'], [class*='side-item']");
  for (const element of Array.from(sectionCandidates)) {
    if (!visible(element)) continue;
    const label = clean(element.textContent);
    const matched = knownSections.find((candidate) => label === candidate || label.startsWith(candidate));
    if (!matched || sections.some((section) => section.label === matched)) continue;
    const ref = `ap-section-${sections.length}`;
    element.setAttribute("data-applypilot-section-ref", ref);
    sections.push({ ref, label: matched, active: /active|selected|current/i.test(element.className) || element.getAttribute("aria-current") === "page" || element.getAttribute("aria-selected") === "true" });
  }
  const activeHeading = Array.from(document.querySelectorAll("h1, h2, h3, h4, h5, h6, legend")).filter(visible).map((element) => clean(element.textContent)).map((label) => knownSections.find((candidate) => label === candidate || label.startsWith(candidate))).find(Boolean);
  const bodyText = clean(document.body?.innerText).slice(0, 12000);
  const loginPath = /(^|\/)(login|signin|auth|passport|xyzlogin)(?:\/|$)/i.test(location.pathname);
  const loginText = /(请先登录|欢迎登录|扫码登录|微信扫码登录|账号密码登录|短信登录|登录后投递|验证码登录)/i.test(bodyText);
  const pageState: PageScan["pageState"] = document.readyState === "loading" ? "loading" : loginPath || loginText ? "login" : fields.length ? "form" : "empty";
  const activeSection = sections.find((section) => section.active)?.label || activeHeading;
  return { url: location.href, title: document.title, fields, sections, activeSection, documentReady: document.readyState !== "loading", pageState, embeddedFrameCount: document.querySelectorAll("iframe").length };
}

/** This function is self-contained because Chrome serializes it for injection. */
export function fillField(ref: string, value: string): FillReceipt {
  const findInRoot = (root: ParentNode): Element | null => {
    const direct = root.querySelector(`[data-applypilot-ref="${CSS.escape(ref)}"]`);
    if (direct) return direct;
    for (const host of Array.from(root.querySelectorAll("*"))) {
      if (host.shadowRoot) {
        const nested = findInRoot(host.shadowRoot);
        if (nested) return nested;
      }
    }
    return null;
  };
  const element = findInRoot(document) as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | HTMLElement | null;
  if (!element) return { ok: false, message: "页面已变化，请重新扫描" };
  const expected = String(value);
  const dispatch = () => {
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    element.dispatchEvent(new Event("blur", { bubbles: true }));
  };
  try {
    if (element instanceof HTMLSelectElement) {
      const wanted = expected.trim().toLowerCase();
      const options = Array.from(element.options).filter((option) => !option.disabled);
      const option = options.find((candidate) => candidate.text.trim().toLowerCase() === wanted) || options.find((candidate) => candidate.text.trim().toLowerCase().includes(wanted) || wanted.includes(candidate.text.trim().toLowerCase()));
      if (!option) return { ok: false, message: `没有匹配的选项：${expected}` };
      element.value = option.value;
      dispatch();
    } else if (element instanceof HTMLInputElement && element.type === "file") {
      return { ok: false, message: "附件请在页面中手动选择文件" };
    } else if (element.getAttribute("role") === "combobox") {
      const input = element as HTMLInputElement;
      input.focus();
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      if (setter && "value" in input) setter.call(input, expected);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      const ownerRoot = element.getRootNode() as Document | ShadowRoot;
      const listId = input.getAttribute("aria-controls") || input.getAttribute("aria-owns");
      const list = listId ? ownerRoot.querySelector(`#${CSS.escape(listId)}`) : null;
      const optionRoots = list ? [list] : Array.from(ownerRoot.querySelectorAll("[role='listbox']")).filter((candidate) => (candidate as HTMLElement).getClientRects().length);
      const options = optionRoots.flatMap((candidate) => Array.from(candidate.querySelectorAll("[role='option']"))).filter((candidate) => (candidate as HTMLElement).getClientRects().length);
      const wanted = expected.trim().toLowerCase();
      const match = options.find((candidate) => (candidate.textContent || "").trim().toLowerCase() === wanted) || options.find((candidate) => (candidate.textContent || "").trim().toLowerCase().includes(wanted));
      if (!match) return { ok: false, message: `下拉选项未出现：${expected}` };
      (match as HTMLElement).click();
      dispatch();
    } else if (element instanceof HTMLInputElement && ["checkbox", "radio"].includes(element.type)) {
      const wanted = /^(是|有|true|yes|1|已婚|男)$/i.test(expected);
      if (element.checked !== wanted) element.click();
    } else if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
      const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
      if (!setter) return { ok: false, message: "浏览器不允许写入该控件" };
      setter.call(element, expected);
      dispatch();
    } else if (element.isContentEditable) {
      element.textContent = expected;
      dispatch();
    } else {
      return { ok: false, message: "此控件需要手动填写" };
    }
    const landed = element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement ? element.value : element.textContent || "";
    const ok = landed.trim() === expected.trim() || (element instanceof HTMLSelectElement && landed.length > 0);
    return { ok, value: landed, message: ok ? "已填写并回读" : "页面未保留填入值，请手动检查" };
  } catch (error) {
    return { ok: false, message: error instanceof Error ? error.message : "控件拒绝了写入" };
  }
}

/** Transfers one bounded chunk of a user-authorized local file. */
export function fillFileChunk(ref: string, name: string, type: string, bytes: number[], done: boolean, totalBytes: number): FillReceipt {
  const findInRoot = (root: ParentNode): Element | null => {
    const direct = root.querySelector(`[data-applypilot-ref="${CSS.escape(ref)}"]`);
    if (direct) return direct;
    for (const host of Array.from(root.querySelectorAll("*"))) {
      if (host.shadowRoot) {
        const nested = findInRoot(host.shadowRoot);
        if (nested) return nested;
      }
    }
    return null;
  };
  const element = findInRoot(document);
  if (!(element instanceof HTMLInputElement) || element.type !== "file") return { ok: false, message: "没有找到可用的附件上传控件，请手动上传" };
  try {
    const holder = element as HTMLInputElement & { __applypilotFileBuffer?: { name: string; type: string; totalBytes: number; bytes: number[] } };
    const buffer = holder.__applypilotFileBuffer || { name, type: type || "application/octet-stream", totalBytes, bytes: [] };
    if (buffer.name !== name || buffer.type !== (type || "application/octet-stream")) buffer.bytes = [];
    buffer.name = name;
    buffer.type = type || "application/octet-stream";
    buffer.totalBytes = totalBytes;
    buffer.bytes.push(...bytes);
    holder.__applypilotFileBuffer = buffer;
    if (!done) return { ok: true, message: "附件传输中" };
    if (buffer.bytes.length !== totalBytes) {
      delete holder.__applypilotFileBuffer;
      return { ok: false, message: "附件传输不完整，请重新选择文件" };
    }
    const file = new File([new Uint8Array(buffer.bytes)], buffer.name, { type: buffer.type });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    element.files = transfer.files;
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    const selected = element.files?.[0];
    delete holder.__applypilotFileBuffer;
    if (!selected || selected.name !== name || selected.size !== buffer.bytes.length) return { ok: false, message: "浏览器未接受附件，请在页面中手动选择" };
    return { ok: true, value: selected.name, message: "已选择附件并触发网站上传，请等待页面确认上传完成" };
  } catch (error) {
    return { ok: false, message: error instanceof Error ? error.message : "附件选择失败，请手动上传" };
  }
}

export function clearFileBuffer(ref: string): void {
  const findInRoot = (root: ParentNode): Element | null => {
    const direct = root.querySelector(`[data-applypilot-ref="${CSS.escape(ref)}"]`);
    if (direct) return direct;
    for (const host of Array.from(root.querySelectorAll("*"))) {
      if (host.shadowRoot) {
        const nested = findInRoot(host.shadowRoot);
        if (nested) return nested;
      }
    }
    return null;
  };
  const element = findInRoot(document) as (HTMLInputElement & { __applypilotFileBuffer?: unknown }) | null;
  if (element) delete element.__applypilotFileBuffer;
}

export function clickSection(ref: string): FillReceipt {
  const element = document.querySelector(`[data-applypilot-section-ref="${CSS.escape(ref)}"]`) as HTMLElement | null;
  if (!element) return { ok: false, message: "页面分区已变化，请重新扫描" };
  try {
    element.click();
    return { ok: true, message: `已切换到 ${element.textContent?.trim() || "目标分区"}，请等待页面更新` };
  } catch (error) {
    return { ok: false, message: error instanceof Error ? error.message : "分区切换失败" };
  }
}
