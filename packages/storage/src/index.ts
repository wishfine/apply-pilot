import Dexie, { type Table } from "dexie";
import type { CandidateProfile } from "../../core/src/index";

type StoredProfile = { id: string; revision: number; updatedAt: string; profile?: CandidateProfile; ciphertext?: string; nonce?: string };
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

  async unlock(_passphrase?: string): Promise<void> {
    // No-op for backward compatibility: password unlock is no longer required
  }

  async load(): Promise<CandidateProfile | undefined> {
    const row = await this.db.profiles.get("default");
    if (!row) return undefined;
    if (row.profile) return row.profile;
    return undefined;
  }

  async save(profile: CandidateProfile): Promise<void> {
    const current = await this.db.profiles.get("default");
    await this.db.profiles.put({
      id: "default",
      revision: (current?.revision || 0) + 1,
      updatedAt: new Date().toISOString(),
      profile,
    });
  }

  async clear(): Promise<void> {
    await this.db.profiles.delete("default");
  }

  lock(): void {
    // No-op for backward compatibility
  }
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


