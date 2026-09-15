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
  it("round-trips a profile and rejects an incorrect password", async () => {
    const first = new ProfileStore();
    await first.unlock("correct horse battery");
    await first.save(sample);
    expect(await first.load()).toEqual(sample);

    const second = new ProfileStore();
    await expect(second.unlock("wrong password")).rejects.toThrow("密码不正确");
    await second.unlock("correct horse battery");
    expect(await second.load()).toEqual(sample);
  });

  it("records field operations without storing their values", async () => {
    const operations = new OperationStore();
    const id = await operations.prepare("run-1", "0:ap-1");
    await operations.finish(id, "verified");
    await expect(operations.forRun("run-1")).resolves.toMatchObject([{ fieldRef: "0:ap-1", status: "verified" }]);
  });
});
