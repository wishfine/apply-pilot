import { parse as parseYaml } from "yaml";
import { mapFields, parseCandidateProfile, type CandidateProfile, type FieldPlan } from "../../../../packages/core/src/index";
import { OperationStore, ProfileStore } from "../../../../packages/storage/src/index";
import { clickSection, clearFileBuffer, fillField, fillFileChunk, scanPage, type FilePayload, type FillReceipt, type PageScan, type PageSection } from "../../runtime/page";
import "../../styles/sidepanel.css";

const store = new ProfileStore();
const rootElement = document.querySelector<HTMLDivElement>("#app");
if (!rootElement) throw new Error("ApplyPilot sidepanel root is missing");
const root = rootElement;

type UiState = { activeTab?: chrome.tabs.Tab; scan?: PageScan; runId?: string; plan: FieldPlan[]; receipts: Record<string, FillReceipt>; profile?: CandidateProfile; asset?: FilePayload; error?: string; warning?: string; busy: boolean };
const state: UiState = { plan: [], receipts: {}, busy: false };
const operations = new OperationStore();

function explainBrowserError(error: unknown, fallback: string): string {
  const message = error instanceof Error ? error.message : String(error || "");
  if (/cannot access|permission|not allowed|scripting/i.test(message)) {
    return "浏览器没有授予当前网页访问权限。请点击工具栏中的 ApplyPilot 图标打开侧栏，再允许此网站权限后重新扫描。";
  }
  return message || fallback;
}

function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, string> = {}, children: (Node | string)[] = []) {
  const el = document.createElement(tag);
  Object.entries(attrs).forEach(([key, value]) => { if (key === "class") el.className = value; else if (key === "text") el.textContent = value; else el.setAttribute(key, value); });
  el.append(...children);
  return el;
}

async function activeTab(): Promise<chrome.tabs.Tab> {
  const currentWindowTabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const lastFocusedTabs = currentWindowTabs.length ? [] : await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  const tab = [...currentWindowTabs, ...lastFocusedTabs].find((candidate) => candidate.id !== undefined);
  if (!tab?.id) throw new Error("当前没有可操作的网页标签页，请先选中招聘网站标签页");
  if (!tab.url) {
    try {
      const hasTabsPermission = await chrome.permissions.contains({ permissions: ["tabs"] });
      if (hasTabsPermission || await chrome.permissions.request({ permissions: ["tabs"] })) {
        const refreshed = await chrome.tabs.get(tab.id);
        Object.assign(tab, refreshed);
      }
    } catch {
      // activeTab may still be enough to inject after the user clicked the action.
    }
  }
  if (tab.url && !/^https?:/i.test(tab.url)) throw new Error("浏览器设置页、扩展页和新标签页不能运行填写");
  state.activeTab = tab;
  return tab;
}

async function ensureSiteAccess(tab: chrome.tabs.Tab): Promise<void> {
  // When the side panel was opened from Chrome's side-panel menu, the activeTab
  // grant may not expose the URL to this extension page yet. executeScript can
  // still use the temporary action grant, so do not misclassify that tab as absent.
  if (!tab.url) return;
  const origin = new URL(tab.url).origin;
  try {
    if (await chrome.permissions.contains({ origins: [`${origin}/*`] })) return;
    const granted = await chrome.permissions.request({ origins: [`${origin}/*`] });
    if (!granted) throw new Error(`未获得 ${origin} 的访问权限，请允许后再次点击扫描当前页`);
  } catch (error) {
    if (error instanceof Error && error.message.includes("未获得")) throw error;
    throw new Error(`无法访问当前网站（${origin}）。请在扩展权限中允许此网站后重试`);
  }
}

function buildPlan(fields: PageScan["fields"], section?: string): FieldPlan[] {
  const plan = mapFields(fields, state.profile, section);
  if (!state.asset) return plan;
  const fileFields = fields.filter((field) => field.kind === "file");
  for (const item of plan) {
    if (item.field.kind !== "file") continue;
    if (!item.field.required) continue;
    const text = `${item.field.label} ${item.field.name}`;
    if (fileFields.length === 1 || /简历|resume|cv/i.test(text)) {
      item.decision = "fill";
      item.proposedValue = state.asset.name;
      item.reason = `附件：${state.asset.name}`;
    }
  }
  return plan;
}

async function scan() {
  state.busy = true; state.error = undefined; state.warning = undefined; render();
  try {
    const tab = await activeTab();
    await ensureSiteAccess(tab);
    let results: chrome.scripting.InjectionResult<PageScan>[];
    try {
      results = await chrome.scripting.executeScript({ target: { tabId: tab.id!, allFrames: true }, func: scanPage });
    } catch {
      results = await chrome.scripting.executeScript({ target: { tabId: tab.id!, frameIds: [0] }, func: scanPage });
      state.warning = "已扫描主页面；部分跨域内嵌表单没有访问权限，请在页面中手动完成。";
    }
    const frames = results.map((item) => ({ frameId: item.frameId ?? 0, scan: item.result as PageScan })).filter((item) => item.scan);
    if (!frames.length) throw new Error("页面没有返回扫描结果");
    const primary = frames.find((item) => item.frameId === 0) || frames[0];
    const pageState = primary.scan.pageState !== "empty" ? primary.scan.pageState : frames.find((item) => item.scan.pageState === "form")?.scan.pageState || frames.find((item) => item.scan.pageState === "login")?.scan.pageState || "empty";
    const sections = primary.scan.sections.length ? primary.scan.sections : frames.find((item) => item.scan.sections.length)?.scan.sections || [];
    state.scan = { url: primary.scan.url, title: primary.scan.title, pageState, activeSection: primary.scan.activeSection || frames.find((item) => item.scan.activeSection)?.scan.activeSection, documentReady: frames.every((item) => item.scan.documentReady), embeddedFrameCount: primary.scan.embeddedFrameCount, sections, fields: frames.flatMap((item) => item.scan.fields.map((field) => ({ ...field, frameId: item.frameId }))) };
    if (primary.scan.embeddedFrameCount > frames.length - 1) state.warning = "部分内嵌表单没有访问权限，已只扫描当前可访问的页面。";
    state.runId = crypto.randomUUID();
    state.plan = buildPlan(state.scan.fields, state.scan.activeSection);
    state.receipts = {};
  } catch (error) { state.error = explainBrowserError(error, "扫描页面失败"); }
  finally { state.busy = false; render(); }
}

async function fill() {
  if (!state.activeTab?.id) return;
  if (!state.scan || state.scan.pageState !== "form") {
    state.error = "当前页面不是可填写的申请表，请完成登录或加载后重新扫描";
    render();
    return;
  }
  state.busy = true; state.error = undefined; render();
  try {
    for (const item of state.plan.filter((candidate) => candidate.decision === "fill" && candidate.proposedValue !== undefined)) {
      const receiptKey = `${item.field.frameId ?? 0}:${item.field.ref}`;
      if (state.receipts[receiptKey]?.ok) continue;
      const value = item.proposedValue;
      if (value === undefined) continue;
      const operationId = await operations.prepare(state.runId || "untracked", receiptKey);
      try {
        if (item.field.kind === "file") {
          if (!state.asset) {
            state.receipts[receiptKey] = { ok: false, message: "请先在侧栏选择简历附件" };
            await operations.finish(operationId, "failed", "ASSET_NOT_SELECTED");
            continue;
          }
          const chunkSize = 512 * 1024;
          let receipt: FillReceipt | undefined;
          try {
            for (let offset = 0; offset < state.asset.bytes.length; offset += chunkSize) {
              const chunk = state.asset.bytes.slice(offset, offset + chunkSize);
              const done = offset + chunk.length >= state.asset.bytes.length;
              const results = await chrome.scripting.executeScript({ target: { tabId: state.activeTab.id, frameIds: [item.field.frameId ?? 0] }, func: fillFileChunk, args: [item.field.ref, state.asset.name, state.asset.type, chunk, done, state.asset.bytes.length] });
              if (done) receipt = results[0]?.result as FillReceipt | undefined;
            }
          } catch (error) {
            await chrome.scripting.executeScript({ target: { tabId: state.activeTab.id, frameIds: [item.field.frameId ?? 0] }, func: clearFileBuffer, args: [item.field.ref] }).catch(() => undefined);
            throw error;
          }
          state.receipts[receiptKey] = receipt || { ok: false, message: "页面没有返回附件结果" };
        } else {
          const results = await chrome.scripting.executeScript({ target: { tabId: state.activeTab.id, frameIds: [item.field.frameId ?? 0] }, func: fillField, args: [item.field.ref, value] });
          state.receipts[receiptKey] = results[0]?.result as FillReceipt || { ok: false, message: "页面没有返回填写结果" };
        }
        await operations.finish(operationId, state.receipts[receiptKey].ok ? "verified" : "failed");
      } catch (error) {
        await operations.finish(operationId, "unknown", "EXECUTION_ERROR");
        throw error;
      }
      render();
    }
  } catch (error) { state.error = explainBrowserError(error, "填写失败"); }
  finally { state.busy = false; render(); }
}

async function start() {
  if (!state.scan) await scan();
  if (state.scan?.pageState === "form") await fill();
}

async function openSection(section: PageSection) {
  if (!state.activeTab?.id || state.busy) return;
  state.busy = true; state.error = undefined; render();
  try {
    const result = await chrome.scripting.executeScript({ target: { tabId: state.activeTab.id, frameIds: [0] }, func: clickSection, args: [section.ref] });
    const receipt = result[0]?.result as FillReceipt | undefined;
    if (!receipt?.ok) throw new Error(receipt?.message || "分区切换失败");
    await new Promise((resolve) => setTimeout(resolve, 500));
    await scan();
  } catch (error) { state.error = explainBrowserError(error, "分区切换失败"); state.busy = false; render(); }
}

async function importProfile(file: File) {
  const source = await file.text();
  const parsed = file.name.toLowerCase().endsWith(".json") ? JSON.parse(source) : parseYaml(source);
  const profile = parseCandidateProfile(parsed);
  await store.save(profile);
  state.profile = profile;
  if (state.scan) state.plan = buildPlan(state.scan.fields, state.scan.activeSection);
  state.error = undefined; render();
}

async function importAttachment(file: File) {
  const maxBytes = 50 * 1024 * 1024;
  if (file.size > maxBytes) {
    state.error = "附件超过 50 MB，招聘页面通常也不会接受";
    render();
    return;
  }
  const bytes = Array.from(new Uint8Array(await file.arrayBuffer()));
  state.asset = { name: file.name, type: file.type || "application/octet-stream", bytes };
  if (state.scan) state.plan = buildPlan(state.scan.fields, state.scan.activeSection);
  state.error = undefined;
  render();
}

async function unlock() {
  const passphrase = document.querySelector<HTMLInputElement>("#passphrase")?.value || "";
  state.busy = true; state.error = undefined; render();
  try {
    await store.unlock(passphrase);
    state.profile = await store.load();
  } catch (error) { state.error = error instanceof Error ? error.message : "资料库解锁失败"; }
  finally { state.busy = false; render(); }
}

function render() {
  root.replaceChildren();
  const header = h("header", {}, [h("div", { class: "brand" }, [h("span", { class: "mark", text: "✓" }), h("strong", { text: "ApplyPilot" })]), h("span", { class: "version", text: "当前页助手" })]);
  const intro = h("section", { class: "intro" }, [h("h1", { text: "填写当前页面" }), h("p", { text: state.busy ? "处理中…" : state.activeTab?.title || "尚未扫描页面" })]);
  const actions = h("div", { class: "actions" });
  const scanButton = h("button", { class: "primary", text: state.busy ? "请稍候" : "扫描当前页" }) as HTMLButtonElement;
  scanButton.disabled = state.busy; scanButton.onclick = () => void scan();
  const fillButton = h("button", { class: "secondary", text: "开始填写" }) as HTMLButtonElement;
  fillButton.disabled = state.busy || state.scan?.pageState === "login" || state.scan?.pageState === "loading";
  fillButton.onclick = () => void start();
  actions.append(scanButton, fillButton);

  const profileSection = h("section", { class: "card" });
  profileSection.append(h("div", { class: "card-title", text: "候选人资料" }), h("p", { class: "muted", text: state.profile ? `已加载：${state.profile.identity?.name || state.profile.profile_id}` : "尚未导入资料" }));
  const passphrase = h("input", { id: "passphrase", type: "password", placeholder: "资料库密码（至少 8 个字符）" }) as HTMLInputElement;
  const unlockButton = h("button", { class: "small-button", text: "解锁资料库" }) as HTMLButtonElement;
  unlockButton.disabled = state.busy; unlockButton.onclick = () => void unlock();
  profileSection.append(h("div", { class: "unlock-row" }, [passphrase, unlockButton]));
  const file = h("input", { type: "file", accept: ".yaml,.yml,.json" }) as HTMLInputElement;
  file.onchange = () => { const selected = file.files?.[0]; if (selected) void importProfile(selected).catch((error) => { state.error = error instanceof Error ? error.message : "资料导入失败"; render(); }); };
  profileSection.append(file);
  profileSection.append(h("p", { class: "muted attachment-help", text: state.asset ? `简历附件：${state.asset.name}` : "需要自动上传简历时，请在这里选择 PDF/DOC/DOCX 文件" }));
  const attachment = h("input", { type: "file", accept: ".pdf,.doc,.docx,.txt,.rtf,.jpg,.jpeg,.png" }) as HTMLInputElement;
  attachment.onchange = () => { const selected = attachment.files?.[0]; if (selected) void importAttachment(selected).catch((error) => { state.error = error instanceof Error ? error.message : "附件读取失败"; render(); }); };
  profileSection.append(attachment);

  const content = h("section", { class: "card" });
  if (state.scan) {
    if (state.scan.pageState === "login") {
      content.append(h("p", { class: "notice", text: "当前页面需要先登录或完成验证。请在此标签页完成后重新扫描，ApplyPilot 不读取账号密码和短信验证码。" }));
    } else if (state.scan.pageState === "loading") {
      content.append(h("p", { class: "notice", text: "页面仍在加载填写内容，请稍后重新扫描。" }));
    }
    const counts = state.plan.reduce((acc, item) => { acc[item.decision] = (acc[item.decision] || 0) + 1; return acc; }, {} as Record<string, number>);
    const optionalCount = state.plan.filter((item) => item.decision === "skip" && item.reason === "选填项，按要求留空").length;
    content.append(h("div", { class: "summary", text: `发现 ${state.scan.fields.length} 项 · 必填可填写 ${counts.fill || 0} · 待处理 ${counts.review || 0} · 选填留空 ${optionalCount} · 已有内容 ${Math.max(0, (counts.skip || 0) - optionalCount)}` }));
    if (state.scan.sections.length > 1) {
      const sectionNav = h("div", { class: "section-nav" });
      sectionNav.append(h("div", { class: "section-title", text: "网站分区" }));
      state.scan.sections.forEach((section) => { const button = h("button", { class: `section-button ${section.active ? "active" : ""}`, text: section.label }) as HTMLButtonElement; button.disabled = state.busy; button.onclick = () => void openSection(section); sectionNav.append(button); });
      content.append(sectionNav);
    }
    const list = h("ul", { class: "field-list" });
    state.plan.forEach((item) => { const receipt = state.receipts[`${item.field.frameId ?? 0}:${item.field.ref}`]; const symbol = receipt?.ok ? "✓" : item.decision === "fill" ? "○" : item.decision === "review" ? "!" : "–"; list.append(h("li", { class: `field ${receipt?.ok ? "done" : item.decision}` }, [h("span", { class: "symbol", text: symbol }), h("div", {}, [h("strong", { text: item.field.label || item.field.name || "未命名字段" }), h("small", { text: receipt?.message || item.reason })])])); });
    content.append(list);
  } else content.append(h("p", { class: "muted", text: "进入已登录的招聘填写页面后，先扫描当前页。" }));
  root.append(header, intro, actions, profileSection, content);
  if (state.error) root.append(h("div", { class: "error", text: state.error }));
  if (state.warning) root.append(h("div", { class: "warning", text: state.warning }));
}

void store.load().then((profile) => { state.profile = profile; render(); }).catch((error) => { state.error = error instanceof Error ? error.message : "资料库需要先解锁"; render(); });
render();
