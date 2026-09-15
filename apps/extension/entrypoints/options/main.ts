import { parse as parseYaml, stringify as stringifyYaml } from "yaml";
import { parseCandidateProfile, type CandidateProfile } from "../../../../packages/core/src/index";
import { ProfileStore } from "../../../../packages/storage/src/index";
import "../../styles/sidepanel.css";

const rootElement = document.querySelector<HTMLDivElement>("#app");
if (!rootElement) throw new Error("ApplyPilot options root is missing");
const root = rootElement;
const store = new ProfileStore();
let profile: CandidateProfile | undefined;
let error = "";

function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, string> = {}, children: (Node | string)[] = []) {
  const element = document.createElement(tag);
  Object.entries(attrs).forEach(([key, value]) => { if (key === "class") element.className = value; else if (key === "text") element.textContent = value; else element.setAttribute(key, value); });
  element.append(...children);
  return element;
}

async function unlock(passphrase: string) {
  try { await store.unlock(passphrase); profile = await store.load(); error = ""; render(); }
  catch (cause) { error = cause instanceof Error ? cause.message : "资料库解锁失败"; render(); }
}

async function importFile(file: File) {
  try {
    const source = await file.text();
    const parsed = file.name.toLowerCase().endsWith(".json") ? JSON.parse(source) : parseYaml(source);
    const imported = parseCandidateProfile(parsed);
    await store.save(imported);
    profile = imported; error = "资料已保存到本地加密资料库"; render();
  } catch (cause) { error = cause instanceof Error ? cause.message : "资料导入失败"; render(); }
}

function exportFile() {
  if (!profile) { error = "请先解锁资料库"; render(); return; }
  const blob = new Blob([stringifyYaml(profile)], { type: "application/yaml" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a"); link.href = url; link.download = "profile.yaml"; document.body.append(link); link.click(); link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function render() {
  root.replaceChildren(h("header", {}, [h("div", { class: "brand" }, [h("span", { class: "mark", text: "✓" }), h("strong", { text: "ApplyPilot 资料中心" })])]), h("section", { class: "card" }, [h("h1", { text: "本地资料库" }), h("p", { class: "muted", text: "资料只保存在此浏览器，并使用密码加密。导出前请确认文件保存位置。" }), h("div", { class: "unlock-row" }, (() => { const input = h("input", { id: "passphrase", type: "password", placeholder: "资料库密码（至少 8 个字符）" }) as HTMLInputElement; const button = h("button", { class: "primary small-button", text: "解锁" }) as HTMLButtonElement; button.onclick = () => void unlock(input.value); return [input, button]; })()), h("div", { class: "actions" }, (() => { const input = h("input", { type: "file", accept: ".yaml,.yml,.json" }) as HTMLInputElement; input.onchange = () => { const file = input.files?.[0]; if (file) void importFile(file); }; const exportButton = h("button", { class: "secondary", text: "导出 YAML" }) as HTMLButtonElement; exportButton.onclick = exportFile; return [input, exportButton]; })())]), h("section", { class: "card" }, [h("div", { class: "card-title", text: profile ? `已加载：${profile.identity?.name || profile.profile_id}` : "尚未加载档案" }), h("p", { class: "muted", text: profile ? `教育 ${profile.education?.length || 0} 条 · 经历 ${profile.experiences?.length || 0} 条 · 附件 ${profile.assets?.length || 0} 个` : "导入现有 profile.yaml 或 profile.json 后，可以在侧栏中填写当前页面。" })]), ...(error ? [h("div", { class: "error", text: error })] : []));
}

void store.load().then((loaded) => { profile = loaded; render(); }).catch(() => render());
render();
