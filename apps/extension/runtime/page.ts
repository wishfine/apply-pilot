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
  section?: string;
  recordGroup?: string;
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
  const isControl = (node: Element | null | undefined): boolean => {
    if (!node || typeof (node as Element).matches !== "function") return false;
    return (node as Element).matches("input, textarea, select, button, [contenteditable='true'], [role='textbox'], [role='combobox'], [role='radio'], [role='checkbox']");
  };
  const textWithoutControls = (node: Element) => {
    if (isControl(node)) return "";
    const copy = node.cloneNode(true) as Element;
    copy.querySelectorAll("input, textarea, select, button, [contenteditable='true'], [role='textbox'], [role='combobox'], [role='radio'], [role='checkbox']").forEach((control) => control.remove());
    return clean(copy.textContent);
  };
  const pseudoContent = (element: Element | null) => {
    if (!element) return "";
    if (typeof navigator !== "undefined" && /jsdom/i.test(navigator.userAgent)) return "";
    try {
      return `${getComputedStyle(element, "::before").content || ""} ${getComputedStyle(element, "::after").content || ""}`;
    } catch {
      return "";
    }
  };
  const requiredFor = (element: Element, label: string, associated: Element | null, nearby: Element | null, container: Element | null) => {
    const input = element as HTMLInputElement;
    const hardRequired = (input.required === true)
      || element.getAttribute("aria-required") === "true"
      || ["data-required", "data-is-required", "data-required-field"].some((name) => /^(true|1|required|必填|必选)$/i.test(element.getAttribute(name) || ""));
    if (hardRequired) return true;

    const nodes: Element[] = [];
    const add = (node: Element | null) => { if (node && !nodes.includes(node)) nodes.push(node); };
    add(element);
    add(associated);
    add(nearby);
    add(container);
    let current: Element | null = element.parentElement;
    for (let depth = 0; current && depth < 5; depth += 1, current = current.parentElement) {
      add(current);
      if (current.getAttribute("aria-required") === "true" || ["data-required", "data-is-required", "data-required-field"].some((name) => /^(true|1|required|必填|必选)$/i.test(current?.getAttribute(name) || "")) || /(?:^|[-_ ])(?:is[-_ ]?)?(?:required|mandatory|must|required-field)(?:$|[-_ ])/i.test(current.className || "")) return true;
      if (current === document.body || current === document.documentElement) break;
    }
    const hasClassOrIconRequired = container?.querySelector(".required, .star, [class*='require'], [class*='star'], [class*='mandatory'], [style*='color: red'], [style*='color:red']") !== null;
    if (hasClassOrIconRequired) return true;
    const semanticTexts = [associated, nearby].filter((node): node is Element => Boolean(node)).map(textWithoutControls);
    const semanticMarker = [label, ...nodes.flatMap((node) => [node.className || "", node.getAttribute("aria-label") || "", node.getAttribute("data-label") || ""]), ...semanticTexts].join(" ").slice(0, 1200);
    const starMarker = [label, associated?.textContent || "", nearby?.textContent || "", ...nodes.map(pseudoContent)].join(" ");
    // Explicit optional markers take precedence over a generic asterisk in nearby text.
    if (/选填|非必填|可选|optional/i.test(semanticMarker) || /选填|非必填|可选|optional/i.test(starMarker)) return false;
    return /必填|必选|required|is[-_ ]?required|must[-_ ]?fill|necess(?:ary|ity)/i.test(semanticMarker) || /[*＊]/.test(starMarker);
  };
  const previousSiblingLabel = (element: Element, hint: string) => {
    let current: Element | null = element;
    for (let depth = 0; depth < 6; depth += 1) {
      const ancestor: HTMLElement | null = current.parentElement;
      if (!ancestor) break;
      const siblings: Element[] = Array.from(ancestor.children);
      const index = siblings.indexOf(current);
      for (let i = index - 1; i >= 0; i -= 1) {
        if (isControl(siblings[i])) continue;
        const candidate = usefulLabel(textWithoutControls(siblings[i]), hint);
        if (candidate && (!/[*＊]/.test(candidate) || /^[*＊]\s*[^*＊]/.test(candidate) || /^[^:*＊：]{1,40}\s*[*＊]$/.test(candidate))) return candidate;
      }
      const preceding = current.previousElementSibling;
      if (preceding && !isControl(preceding)) {
        const candidate = usefulLabel(textWithoutControls(preceding), hint);
        if (candidate && (!/[*＊]/.test(candidate) || /^[*＊]\s*[^*＊]/.test(candidate) || /^[^:*＊：]{1,40}\s*[*＊]$/.test(candidate))) return candidate;
      }
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
  const knownSections = ["个人信息", "求职意向", "教育经历", "实习经历", "项目经历", "在校实践", "获奖情况", "论文/专著", "证书", "其他信息", "简历附件"];
  const sectionHeadings = Array.from(document.querySelectorAll("h1, h2, h3, h4, h5, h6, legend, [role='heading'], [class*='section-title'], [class*='sectionTitle'], [class*='form-title'], [class*='formTitle']"));
  const matchingSection = (value: string) => knownSections.find((candidate) => value === candidate || value.startsWith(candidate));
  const sectionFor = (element: Element) => {
    const fieldset = element.closest("fieldset");
    const legend = fieldset?.querySelector(":scope > legend");
    const fieldsetSection = legend ? matchingSection(clean(legend.textContent)) : undefined;
    if (fieldsetSection) return fieldsetSection;
    let previous: string | undefined;
    for (const heading of sectionHeadings.filter(visible)) {
      if ((heading.compareDocumentPosition(element) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0) previous = matchingSection(clean(heading.textContent)) || previous;
    }
    return previous;
  };
  const recordGroupFor = (element: Element, section?: string) => {
    if (!section || !["实习经历", "项目经历", "获奖情况", "论文/专著", "证书", "在校实践"].includes(section)) return undefined;
    const ancestor = element.closest("[data-record-id], [data-row-id], [data-item-id], [data-index], fieldset, [class*='experience'], [class*='Experience'], [class*='intern'], [class*='Intern'], [class*='project'], [class*='Project'], [class*='record'], [class*='Record'], [class*='entry'], [class*='Entry']");
    if (!ancestor) return undefined;
    const marker = ["data-record-id", "data-row-id", "data-item-id", "data-index"].map((name) => ancestor.getAttribute(name)).find(Boolean);
    if (marker) return `${section}:${marker}`;
    const peers = Array.from(document.querySelectorAll("fieldset, [class*='experience'], [class*='Experience'], [class*='intern'], [class*='Intern'], [class*='project'], [class*='Project'], [class*='record'], [class*='Record'], [class*='entry'], [class*='Entry']"));
    const index = peers.filter((candidate) => candidate.parentElement === ancestor.parentElement).indexOf(ancestor);
    return `${section}:${ancestor.tagName.toLowerCase()}:${Math.max(index, 0)}`;
  };
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
    const container = element.closest("label, .form-item, .form-group, .field, [class*='field'], [class*='form'], [class*='row'], .row, tr, [class*='item'], [class*='line']");
    let nearby = container?.querySelector("label, legend, th, .label, [class*='label'], [class*='title']");
    if (!nearby && (element.closest("td") || element.closest("th"))) {
      const cell = element.closest("td, th");
      nearby = cell?.previousElementSibling || container?.querySelector("td:first-child, th:first-child");
    }
    const labelledBy = clean((element.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean).map((id) => ownerRoot.querySelector(`#${CSS.escape(id)}`)?.textContent || "").join(" "));
    const explicit = clean(element.getAttribute("data-label") || element.getAttribute("data-field-label") || element.getAttribute("title"));
    const label = usefulLabel(labelledBy, hint) || usefulLabel(associated?.textContent || "", hint) || usefulLabel(nearby?.textContent || "", hint) || usefulLabel(explicit, hint) || previousSiblingLabel(element, hint) || usefulLabel(hint, hint) || usefulLabel(uploadHost?.textContent || "", hint) || (type === "file" ? "附件上传" : "");
    if (!label) continue;
    const required = requiredFor(element, label, associated, nearby ?? null, container);
    let kind: PageField["kind"] = "unsupported";
    if (element instanceof HTMLSelectElement) kind = "select";
    else if (type === "file") kind = "file";
    else if (["checkbox", "radio"].includes(type) || ["checkbox", "radio"].includes(element.getAttribute("role") || "")) kind = "choice";
    else if (element instanceof HTMLTextAreaElement || element.getAttribute("contenteditable") === "true" || ["textbox", "combobox"].includes(element.getAttribute("role") || "")) kind = "textarea";
    else if (["text", "email", "tel", "number", "url", "date", "month", "time", "datetime-local"].includes(type)) kind = "text";
    if (kind === "unsupported") continue;

    // Disambiguate compound fields and cascading selects within the same container
    let finalLabel = label;
    const normL = clean(label).replace(/[*＊:：\s]/g, "");
    const hostContainer = element.closest("tr, td, label, .form-item, .form-group, .field, [class*='field'], [class*='form'], [class*='row'], .row, [class*='item'], [class*='line'], [class*='group']");
    const containerText = clean(hostContainer?.textContent || "").replace(/[*＊:：\s]/g, "");

    if (kind === "select") {
      if (hostContainer) {
        const siblingSelects = Array.from(hostContainer.querySelectorAll("select")).filter(visible);
        if (/身份证|证件号|证件号码/.test(normL) && !/类型|种类/.test(normL)) {
          finalLabel = "证件类型";
        } else if (/手机|移动电话/.test(normL) && !/区号|国家|地区/.test(normL)) {
          finalLabel = "手机区号";
        } else if (siblingSelects.length > 1 && (/出生|生日/.test(normL) || /出生|生日/.test(containerText))) {
          const selectIndex = siblingSelects.indexOf(element as HTMLSelectElement);
          if (selectIndex === 0) finalLabel = "出生年份";
          else if (selectIndex === 1) finalLabel = "出生月份";
          else if (selectIndex === 2) finalLabel = "出生日";
        } else if (siblingSelects.length > 1 && (/入学|开始/.test(normL) || /入学|开始/.test(containerText))) {
          const selectIndex = siblingSelects.indexOf(element as HTMLSelectElement);
          if (selectIndex === 0) finalLabel = "入学年份";
          else if (selectIndex === 1) finalLabel = "入学月份";
        } else if (siblingSelects.length > 1 && (/毕业|结束|离校/.test(normL) || /毕业|结束|离校/.test(containerText))) {
          const selectIndex = siblingSelects.indexOf(element as HTMLSelectElement);
          if (selectIndex === 0) finalLabel = "毕业年份";
          else if (selectIndex === 1) finalLabel = "毕业月份";
        } else if (siblingSelects.length > 1 && /籍贯|户籍|户口|居住|现居|常住|地址/.test(normL)) {
          const selectIndex = siblingSelects.indexOf(element as HTMLSelectElement);
          if (selectIndex === 0) finalLabel = `${normL}省份`;
          else if (selectIndex === 1) finalLabel = `${normL}城市`;
          else if (selectIndex === 2) finalLabel = `${normL}区县`;
        } else if (normL === "年" || normL === "月" || normL === "日") {
          const prefix = /出生|生日/.test(containerText) ? "出生" : /毕业/.test(containerText) ? "毕业" : /入学/.test(containerText) ? "入学" : "";
          if (prefix) {
            if (normL === "年") finalLabel = `${prefix}年份`;
            else if (normL === "月") finalLabel = `${prefix}月份`;
            else if (normL === "日") finalLabel = `${prefix}日`;
          }
        }
      }
    } else if (kind === "text") {
      // If text input is in compound row with select (like ID type + ID number, or Country code + Mobile)
      if (hostContainer) {
        const hasSiblingSelect = hostContainer.querySelector("select") !== null;
        if (hasSiblingSelect) {
          if (/证件类型|证件种类/.test(normL)) {
            finalLabel = label.includes("*") ? "* 身份证号" : "身份证号";
          } else if (/手机区号|国家代码|国际区号/.test(normL)) {
            finalLabel = label.includes("*") ? "* 手机号码" : "手机号码";
          }
        }
      }
    }

    const ref = `ap-${sequence++}`;
    element.setAttribute("data-applypilot-ref", ref);
    const options = element instanceof HTMLSelectElement ? Array.from(element.options).filter((option) => !option.disabled && clean(option.textContent)).map((option) => clean(option.textContent)) : [];
    let value = "";
    if (element instanceof HTMLSelectElement) {
      const selected = element.selectedOptions?.[0] || element.options[element.selectedIndex];
      const optText = selected ? clean(selected.textContent) : "";
      const valText = clean(control.value || "");
      const isPlaceholderText = (t: string) => !t || /^[-—_/\s]*$/i.test(t) || /^[-—_/\s]*(请选择|选择|未选择|select|none|null|undefined|请挑选)[-—_/\s.]*$/i.test(t);
      if (isPlaceholderText(optText) || (isPlaceholderText(valText) && (element.selectedIndex <= 0 || /^(-1|0|)$/.test(valText)))) {
        value = "";
      } else {
        value = optText || valText;
      }
    } else if (element instanceof HTMLInputElement && (element.type === "checkbox" || element.type === "radio")) {
      value = element.checked ? (clean(element.value) || "是") : "";
    } else if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
      value = control.value;
    } else {
      value = clean(element.textContent);
    }
    const section = sectionFor(element);
    fields.push({ ref, label: finalLabel, name: clean(control.name || element.id || hint), type, kind, required, value, options, section, recordGroup: recordGroupFor(element, section) });
  }
  const sections: PageSection[] = [];
  const sectionCandidates = document.querySelectorAll("a, button, [role='tab'], [role='menuitem'], [class*='menu-item'], [class*='nav-item'], [class*='side-item']");
  for (const element of Array.from(sectionCandidates)) {
    if (!visible(element)) continue;
    const label = clean(element.textContent);
    const matched = matchingSection(label);
    if (!matched || sections.some((section) => section.label === matched)) continue;
    const ref = `ap-section-${sections.length}`;
    element.setAttribute("data-applypilot-section-ref", ref);
    sections.push({ ref, label: matched, active: /active|selected|current/i.test(element.className) || element.getAttribute("aria-current") === "page" || element.getAttribute("aria-selected") === "true" });
  }
  const activeHeading = sectionHeadings.filter(visible).map((element) => matchingSection(clean(element.textContent))).find(Boolean);
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
    try {
      if (typeof InputEvent !== "undefined") {
        element.dispatchEvent(new InputEvent("input", { bubbles: true, composed: true, data: expected, inputType: "insertText" }));
      } else {
        element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
      }
    } catch {
      element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    }
    element.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    element.dispatchEvent(new Event("blur", { bubbles: true, composed: true }));
  };
  try {
    if (element instanceof HTMLSelectElement) {
      const wanted = expected.trim();
      const options = Array.from(element.options).filter((option) => !option.disabled);

      const norm = (str: string) => (str || "").replace(/[\s:*：\/／,，.。·()（）【】\[\]_-]/g, "").toLowerCase();
      const normWanted = norm(wanted);

      const validOptions = options.filter((opt) => {
        const n = norm(opt.text);
        return n && !/^(请选择|--请选择--|选择|未选择|select)$/i.test(norm(n));
      });
      const candidates = validOptions.length ? validOptions : options;

      // 1. Exact match (by text or value)
      let matchedOption = candidates.find((c) => norm(c.text) === normWanted || c.value.trim().toLowerCase() === wanted.toLowerCase());

      // 2. Numeric / Date component matching (e.g. "05" matches "5", "05", "5月", "05月"; "2001" matches "2001", "2001年")
      if (!matchedOption) {
        const targetDigits = normWanted.replace(/\D/g, "");
        if (targetDigits.length > 0 && targetDigits.length <= 4) {
          const targetNum = parseInt(targetDigits, 10);
          matchedOption = candidates.find((c) => {
            const optDigits = norm(c.text).replace(/\D/g, "");
            return optDigits.length > 0 && parseInt(optDigits, 10) === targetNum;
          });
        }
      }

      // 3. Synonym groups lookup
      if (!matchedOption) {
        const SYNONYMS = [
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
          ["国内身份证或护照（含港澳台）", "居民身份证", "中华人民共和国居民身份证", "二代居民身份证", "二代身份证", "身份证", "国内身份证", "大陆居民身份证", "国内身份证或护照"],
          ["国外身份证", "外籍身份证", "外籍证件"],
          ["护照", "中国护照", "因私普通护照", "外国护照"],
          ["港澳居民来往内地通行证", "港澳通行证", "回乡证"],
          ["台湾居民来往大陆通行证", "台胞证"],
          ["中国大陆（+86）", "中国大陆(+86)", "+86", "86", "中国大陆", "中国(+86)", "+86(中国大陆)", "+86中国大陆", "中国"],
          ["其他地区手机号", "其他地区", "境外手机号", "其他国家或地区", "其他"],
          ["博士研究生", "博士", "doctor", "博士生"],
          ["硕士研究生", "硕士", "master", "研究生", "硕士生"],
          ["大学本科", "本科", "bachelor", "普通本科", "全日制本科", "本科生"],
          ["大学专科", "专科", "大专", "associate", "高职", "专科(高职)"],
          ["普通高中", "高中", "high_school", "中专"],
          ["是", "yes", "true", "1", "有", "服从", "同意", "参加", "合格", "已通过"],
          ["否", "no", "false", "0", "无", "不服从", "不同意", "未参加", "不合格", "未通过"],
          ["未婚", "未婚/single", "single"],
          ["已婚", "已婚/married", "married"],
          ["离异", "离异/divorced", "divorced"],
          ["男", "男性", "male"],
          ["女", "女性", "female"],
          ["城镇居民", "城镇", "城镇户口", "城市居民", "非农业户口", "非农"],
          ["农村居民", "农村", "农村户口", "农业户口", "农业"]
        ];
        for (const group of SYNONYMS) {
          const inGroup = group.some((item) => {
            const n = norm(item);
            return n === normWanted || (n.length >= 2 && normWanted.length >= 2 && (normWanted.includes(n) || n.includes(normWanted)));
          });
          if (inGroup) {
            for (const item of group) {
              const normItem = norm(item);
              const found = candidates.find((c) => {
                const normText = norm(c.text);
                return normText === normItem || (normText.length >= 2 && normItem.length >= 2 && (normText.includes(normItem) || normItem.includes(normText)));
              });
              if (found) {
                matchedOption = found;
                break;
              }
            }
            if (matchedOption) break;
          }
        }
      }

      // 4. Location partial match (e.g. wanted is "湖北省武汉市", option is "湖北" or "武汉市")
      if (!matchedOption) {
        const PROVINCES = ["北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江", "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "广西", "海南", "重庆", "四川", "贵州", "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆", "香港", "澳门", "台湾"];
        for (const prov of PROVINCES) {
          if (wanted.startsWith(prov)) {
            const provMatch = candidates.find((c) => {
              const n = norm(c.text);
              return n === prov || n === `${prov}省` || n === `${prov}市` || (n.length >= 2 && prov.includes(n));
            });
            if (provMatch) {
              matchedOption = provMatch;
              break;
            }
          }
        }
      }

      // 5. Substring / inclusion match (longest option match first)
      if (!matchedOption) {
        const sorted = [...candidates].sort((a, b) => b.text.length - a.text.length);
        matchedOption = sorted.find((c) => {
          const normText = norm(c.text);
          return normText.length >= 2 && (normWanted.includes(normText) || normText.includes(normWanted));
        });
      }

      if (!matchedOption) return { ok: false, message: `没有匹配的选项：${expected}` };
      element.value = matchedOption.value;
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
      if (typeof element.focus === "function") element.focus();
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

