import "fake-indexeddb/auto";
import { afterEach, describe, expect, it } from "vitest";
import { OperationStore, ProfileStore } from "../../../packages/storage/src/index";

const sample = { profile_id: "encrypted-test", identity: { name: "张三" }, education: [] };

async function deleteDatabase() {
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase("applypilot-extension");
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
    request.onblocked = () => resolve();
  });
}

afterEach(() => deleteDatabase());

describe("encrypted profile store", () => {
  it("round-trips a profile directly without requiring a password", async () => {
    const first = new ProfileStore();
    await first.save(sample);
    expect(await first.load()).toEqual(sample);

    const second = new ProfileStore();
    expect(await second.load()).toEqual(sample);

    await second.clear();
    expect(await second.load()).toBeUndefined();
  });

  it("records field operations without storing their values", async () => {
    const operations = new OperationStore();
    const id = await operations.prepare("run-1", "0:ap-1");
    await operations.finish(id, "verified");
    await expect(operations.forRun("run-1")).resolves.toMatchObject([{ fieldRef: "0:ap-1", status: "verified" }]);
  });
});
