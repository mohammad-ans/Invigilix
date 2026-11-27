import { request } from "./api.js";
import { change } from "./store.js";
import { accept, enqueue, resolveConflict, responseOf, visibleItem } from "./queue.js";

const offlineError = error => !error.status || error.status >= 500;
const denied = error => [401, 403, 404].includes(error.status);

export class AttemptSession {
  constructor(account, id, notify) {
    this.account = account;
    this.id = id;
    this.path = "/attempts/" + encodeURIComponent(id);
    this.notify = notify;
    this.writes = Promise.resolve();
    this.optimistic = [];
    this.state = { status: "Loading" };
  }

  show(fields = {}) {
    if (!this.active) return;
    Object.assign(this.state, fields);
    let record = this.record;
    if (record && this.optimistic.length) {
      record = structuredClone(record);
      for (const edit of this.optimistic) enqueue(record, edit.item, edit.body, edit.id);
    }
    this.notify({ ...this.state, record, storageFailed: this.memoryOnly });
  }

  mutate(update, committed) {
    const run = async () => {
      if (!this.active) return;
      if (!this.memoryOnly) {
        try {
          this.record = await change(this.account, this.id, update);
        } catch {
          this.memoryOnly = true;
        }
      }
      if (this.memoryOnly) this.record = update(this.record);
      committed?.();
      this.show();
    };
    this.writes = this.writes.then(run);
    return this.writes;
  }

  async init() {
    this.active = true;
    await this.mutate(value => value);
    await this.refresh();
  }

  async refresh() {
    if (this.refreshing || !this.active || this.state.receipt) return;
    this.refreshing = true;
    try {
      const paper = await request(this.path);
      if (!this.active) return;
      if (paper.finalized_at) return await this.close(paper);
      const offset = Date.parse(paper.server_time) - Date.now();
      await this.mutate(old => {
        // Keep an acknowledgment that raced with this read.
        for (const item of paper.items) {
          const cached = old?.paper.items.find(i => i.slot === item.slot);
          if (cached && cached.revision >= item.revision) Object.assign(item, cached);
        }
        return { paper, offset, pending: old?.pending ?? [], conflicts: old?.conflicts ?? {},
          scratch: old?.scratch ?? "" };
      });
      this.show({ error: "", status: "Saved on server" });
      await this.flush();
    } catch (error) {
      await this.failure(error);
    } finally {
      this.refreshing = false;
    }
  }

  async failure(error) {
    if (denied(error)) {
      await this.mutate(() => undefined);
      this.show({ error: "Access to this attempt has ended.", denied: true });
    } else {
      this.show({ error: offlineError(error) ? "Connection unavailable. Retry when connected." : error.message,
        status: navigator.onLine ? "Save failed" : "On this device" });
    }
  }

  edit(item, patch) {
    if (!this.active || this.closed || this.state.submitting || this.timeLeft() <= 0) return;
    const draft = { id: crypto.randomUUID(), item, body: { ...responseOf(item), ...patch } };
    this.optimistic.push(draft);
    this.show({ status: "Saving" });
    this.mutate(record => {
      if (record) enqueue(record, item, draft.body, draft.id);
      return record;
    }, () => { this.optimistic = this.optimistic.filter(d => d !== draft); }).then(() => this.flush());
  }

  timeLeft() {
    return this.record ? Date.parse(this.record.paper.deadline_at) - Date.now() - this.record.offset : 0;
  }

  flush() {
    if (!this.sending) this.sending = this.drain().finally(() => { this.sending = null; });
    return this.sending;
  }

  async drain() {
    while (this.active && !this.closed) {
      await this.writes;
      const record = this.record;
      if (!record) return;
      const edit = record.pending.find(e => !record.conflicts[e.slot]);
      if (!edit) {
        this.show({ status: record.pending.length ? "Conflict" : "Saved on server" });
        return;
      }
      if (!navigator.onLine || this.timeLeft() <= 0) {
        this.show({ status: "On this device" });
        return;
      }
      this.show({ status: "Saving" });
      try {
        const ack = await request(this.path + "/items/" + edit.slot, "PUT",
          { ...edit.body, base_revision: edit.base_revision });
        await this.mutate(current => {
          if (current) accept(current, edit, ack);
          return current;
        });
      } catch (error) {
        if (error.detail?.code === "attempt_closed") return this.close(error.detail.receipt);
        if (error.detail?.code === "stale_revision") {
          await this.mutate(current => {
            if (current?.pending.some(e => e.id === edit.id)) current.conflicts[edit.slot] = error.detail.item;
            return current;
          });
        } else {
          await this.failure(error);
          return;
        }
      }
    }
  }

  resolve(slot, keepLocal) {
    return this.mutate(record => {
      if (record) resolveConflict(record, slot, keepLocal);
      return record;
    }).then(() => this.flush());
  }

  scratch(text) {
    return this.mutate(record => record && { ...record, scratch: text });
  }

  async preferences(prefs) {
    try {
      const saved = await request("/me/preferences", "PATCH", prefs);
      await this.mutate(record => {
        if (record) record.paper.preferences = saved;
        return record;
      });
      this.show({ preferenceError: "" });
    } catch (error) {
      if (denied(error)) await this.failure(error);
      else this.show({ preferenceError: "Could not save preferences. Please retry." });
    }
  }

  async submit() {
    if (this.closed || this.state.submitting) return;
    this.show({ submitting: true });
    try {
      await this.flush();
      if (!this.record || this.record.pending.length || this.closed) return;
      await this.close(await request(this.path + "/submit", "POST"));
    } catch (error) {
      await this.failure(error);
    } finally {
      this.show({ submitting: false });
    }
  }

  async close(receipt) {
    this.closed = true;
    let outstanding = [];
    await this.mutate(record => {
      outstanding = [...new Set(record?.pending.map(edit => edit.slot) ?? [])];
      return undefined;
    });
    this.show({ receipt, outstanding, error: "" });
  }
}
