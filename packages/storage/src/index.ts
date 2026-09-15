import Dexie, { type Table } from "dexie";
import type { CandidateProfile } from "../../core/src/index";

type StoredProfile = { id: string; revision: number; updatedAt: string; ciphertext: string; nonce: string };
type VaultMetadata = { id: "vault"; salt: string; version: 1; verifier?: string; verifierNonce?: string };
export type OperationStatus = "prepared" | "verified" | "failed" | "unknown";
export type StoredOperation = { id: string; runId: string; fieldRef: string; status: OperationStatus; startedAt: string; finishedAt?: string; errorCode?: string };

class ApplyPilotDatabase extends Dexie {
  profiles!: Table<StoredProfile, string>;
  meta!: Table<VaultMetadata, string>;
  operations!: Table<StoredOperation, string>;

  constructor() {
    super("applypilot-extension");
    this.version(1).stores({ profiles: "id, updatedAt", meta: "id" });
    this.version(2).stores({ profiles: "id, updatedAt", meta: "id", operations: "id, runId, status, startedAt" });
  }
}

export class ProfileStore {
  private readonly db = new ApplyPilotDatabase();
  private key?: CryptoKey;

  async unlock(passphrase: string): Promise<void> {
    if (passphrase.trim().length < 8) throw new Error("资料库密码至少需要 8 个字符");
    let metadata = await this.db.meta.get("vault");
    if (!metadata) {
      const salt = crypto.getRandomValues(new Uint8Array(16));
      const candidate = await deriveKey(passphrase, salt);
      const verifierNonce = crypto.getRandomValues(new Uint8Array(12));
      metadata = { id: "vault", salt: toBase64(salt), version: 1, verifier: await encrypt(candidate, "applypilot-vault-verifier-v1", verifierNonce, "vault-verifier-v1"), verifierNonce: toBase64(verifierNonce) };
      await this.db.meta.put(metadata);
      const legacy = await this.db.profiles.get("default") as (StoredProfile & { profile?: CandidateProfile }) | undefined;
      if (legacy?.profile) {
        const nonce = crypto.getRandomValues(new Uint8Array(12));
        await this.db.profiles.put({ id: "default", revision: legacy.revision || 1, updatedAt: legacy.updatedAt || new Date().toISOString(), ciphertext: await encrypt(candidate, JSON.stringify(legacy.profile), nonce, "profile:default:v1"), nonce: toBase64(nonce) });
      }
      this.key = candidate;
      return;
    }
    const candidate = await deriveKey(passphrase, fromBase64(metadata.salt));
    if (metadata.verifier && metadata.verifierNonce) {
      try {
        if (await decrypt(candidate, metadata.verifier, metadata.verifierNonce, "vault-verifier-v1") !== "applypilot-vault-verifier-v1") throw new Error("invalid verifier");
      } catch { throw new Error("资料库密码不正确"); }
    }
    const row = await this.db.profiles.get("default");
    if (row) {
      try { await decrypt(candidate, row.ciphertext, row.nonce, "profile:default:v1"); }
      catch { throw new Error("资料库数据损坏或密码不正确"); }
    }
    if (!metadata.verifier || !metadata.verifierNonce) {
      const verifierNonce = crypto.getRandomValues(new Uint8Array(12));
      await this.db.meta.put({ ...metadata, verifier: await encrypt(candidate, "applypilot-vault-verifier-v1", verifierNonce, "vault-verifier-v1"), verifierNonce: toBase64(verifierNonce) });
    }
    this.key = candidate;
  }

  async load(): Promise<CandidateProfile | undefined> {
    const row = await this.db.profiles.get("default");
    if (!row) return undefined;
    if (!this.key) throw new Error("资料库已加密，请先解锁");
    return JSON.parse(await decrypt(this.key, row.ciphertext, row.nonce, "profile:default:v1")) as CandidateProfile;
  }

  async save(profile: CandidateProfile): Promise<void> {
    if (!this.key) throw new Error("资料库未解锁，请先设置密码");
    const current = await this.db.profiles.get("default");
    const nonce = crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = await encrypt(this.key, JSON.stringify(profile), nonce, "profile:default:v1");
    await this.db.profiles.put({ id: "default", revision: (current?.revision || 0) + 1, updatedAt: new Date().toISOString(), ciphertext, nonce: toBase64(nonce) });
  }

  async clear(): Promise<void> {
    await this.db.profiles.delete("default");
  }

  lock(): void { this.key = undefined; }
}

export class OperationStore {
  private readonly db = new ApplyPilotDatabase();

  async prepare(runId: string, fieldRef: string): Promise<string> {
    const id = `${runId}:${fieldRef}:${crypto.randomUUID()}`;
    await this.db.operations.put({ id, runId, fieldRef, status: "prepared", startedAt: new Date().toISOString() });
    return id;
  }

  async finish(id: string, status: OperationStatus, errorCode?: string): Promise<void> {
    const operation = await this.db.operations.get(id);
    if (!operation) return;
    await this.db.operations.put({ ...operation, status, errorCode, finishedAt: new Date().toISOString() });
  }

  async forRun(runId: string): Promise<StoredOperation[]> {
    return this.db.operations.where("runId").equals(runId).sortBy("startedAt");
  }
}

async function deriveKey(passphrase: string, salt: Uint8Array): Promise<CryptoKey> {
  const material = await crypto.subtle.importKey("raw", new TextEncoder().encode(passphrase), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey({ name: "PBKDF2", salt: salt as unknown as ArrayBuffer, iterations: 210_000, hash: "SHA-256" }, material, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
}

async function encrypt(key: CryptoKey, value: string, nonce: Uint8Array, additionalData: string): Promise<string> {
  const bytes = await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce as unknown as ArrayBuffer, additionalData: new TextEncoder().encode(additionalData) as unknown as ArrayBuffer }, key, new TextEncoder().encode(value));
  return toBase64(new Uint8Array(bytes));
}

async function decrypt(key: CryptoKey, ciphertext: string, nonce: string, additionalData: string): Promise<string> {
  const bytes = await crypto.subtle.decrypt({ name: "AES-GCM", iv: fromBase64(nonce) as unknown as ArrayBuffer, additionalData: new TextEncoder().encode(additionalData) as unknown as ArrayBuffer }, key, fromBase64(ciphertext) as unknown as ArrayBuffer);
  return new TextDecoder().decode(bytes);
}

function toBase64(bytes: Uint8Array): string {
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary);
}

function fromBase64(value: string): Uint8Array {
  const binary = atob(value);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}
