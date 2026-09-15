import { parse as parseYaml } from "yaml";
import { mapFields, parseCandidateProfile, type CandidateProfile, type FieldPlan } from "../../../../packages/core/src/index";
import { OperationStore, ProfileStore } from "../../../../packages/storage/src/index";
import { fillField, scanPage, type FillReceipt, type PageScan } from "../../runtime/page";
import "../../styles/sidepanel.css";

const store = new ProfileStore();
const rootElement = document.querySelector<HTMLDivElement>("#app");
if (!rootElement) throw new Error("ApplyPilot sidepanel root is missing");
const root = rootElement;

type UiState = { activeTab?: chrome.tabs.Tab; scan?: PageScan; runId?: string; plan: FieldPlan[]; receipts: Record<string, FillReceipt>; profile?: CandidateProfile; error?: string; warning?: string; busy: boolean };
const state: UiState = { plan: [], receipts: {}, busy: false };
const operations = new OperationStore();

function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, string> = {}, children: (Node | string)[] = []) {
  const el = document.createElement(tag);
  Object.entries(attrs).forEach(([key, value]) => { if (key === "class") el.className = value; else if (key === "text") el.textContent = value; else el.setAttribute(key, value); });
  el.append(...children);
  return el;
}

async function activeTab(): Promise<chrome.tabs.Tab> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url) throw new Error("当前没有可操作的网页标签页");
  if (!/^https?:/i.test(tab.url)) throw new Error("浏览器设置页、扩展页和新标签页不能运行填写");
  state.activeTab = tab;
  return tab;
}

async function scan() {
  state.busy = true; state.error = undefined; state.warning = undefined; render();
  try {
    const tab = await activeTab();
    let results: chrome.scripting.InjectionResult<PageScan>[];
    try {
      results = await chrome.scripting.executeScript({ target: { tabId: tab.id!, allFrames: true }, func: scanPage });
    } catch {
      results = await chrome.scripting.executeScript({ target: { tabId: tab.id!, frameIds: [0] }, func: scanPage });
      state.warning = "已扫描主页面；部分跨域内嵌表单没有访问权限，请在页面中手动完成。";
    }
    const frames = results.map((item) => ({ frameId: item.frameId ?? 0, scan: item.result as PageScan })).filter((item) => item.scan);
    if (!frames.length) throw new Error("页面没有返回扫描结果");
    const first = frames[0].scan;
    state.scan = { url: first.url, title: first.title, pageState: first.pageState, documentReady: frames.every((item) => item.scan.documentReady), embeddedFrameCount: first.embeddedFrameCount, fields: frames.flatMap((item) => item.scan.fields.map((field) => ({ ...field, frameId: item.frameId }))) };
    if (first.embeddedFrameCount > frames.length - 1) state.warning = "部分内嵌表单没有访问权限，已只扫描当前可访问的页面。";
    state.runId = crypto.randomUUID();
    state.plan = mapFields(state.scan.fields, state.profile);
    state.receipts = {};
  } catch (error) { state.error = error instanceof Error ? error.message : "扫描页面失败"; }
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
        const results = await chrome.scripting.executeScript({ target: { tabId: state.activeTab.id, frameIds: [item.field.frameId ?? 0] }, func: fillField, args: [item.field.ref, value] });
        state.receipts[receiptKey] = results[0]?.result as FillReceipt || { ok: false, message: "页面没有返回填写结果" };
        await operations.finish(operationId, state.receipts[receiptKey].ok ? "verified" : "failed");
      } catch (error) {
        await operations.finish(operationId, "unknown", "EXECUTION_ERROR");
        throw error;
      }
      render();
    }
  } catch (error) { state.error = error instanceof Error ? error.message : "填写失败"; }
  finally { state.busy = false; render(); }
}

async function start() {
  if (!state.scan) await scan();
  if (state.scan?.pageState === "form") await fill();
}

async function importProfile(file: File) {
  const source = await file.text();
  const parsed = file.name.toLowerCase().endsWith(".json") ? JSON.parse(source) : parseYaml(source);
  const profile = parseCandidateProfile(parsed);
  await store.save(profile);
  state.profile = profile;
  if (state.scan) state.plan = mapFields(state.scan.fields, profile);
  state.error = undefined; render();
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

  const content = h("section", { class: "card" });
  if (state.scan) {
    if (state.scan.pageState === "login") {
      content.append(h("p", { class: "notice", text: "当前页面需要先登录或完成验证。请在此标签页完成后重新扫描，ApplyPilot 不读取账号密码和短信验证码。" }));
    } else if (state.scan.pageState === "loading") {
      content.append(h("p", { class: "notice", text: "页面仍在加载填写内容，请稍后重新扫描。" }));
    }
    const counts = state.plan.reduce((acc, item) => { acc[item.decision] = (acc[item.decision] || 0) + 1; return acc; }, {} as Record<string, number>);
    content.append(h("div", { class: "summary", text: `发现 ${state.scan.fields.length} 项 · 可填写 ${counts.fill || 0} · 待处理 ${counts.review || 0} · 跳过 ${counts.skip || 0}` }));
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
