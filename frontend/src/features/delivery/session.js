import { request } from "./api.js";
import { change } from "./store.js";
import { accept, enqueue, resolveConflict, responseOf } from "./queue.js";

const offlineError = error => !error.status || error.status >= 500;
const denied = error => [401, 403, 404].includes(error.status);

export class AttemptSession {
  constructor(account, id, notify, storage = change) {
    this.account = account;
    this.id = id;
    this.path = "/attempts/" + encodeURIComponent(id);
    this.notify = notify;
    this.storage = storage;
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
          this.record = await this.storage(this.account, this.id, update);
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
    await this.refresh();
  }

  async refresh() {
    if (this.refreshing || !this.active || this.closed || this.state.denied) return;
    this.refreshing = true;
    try {
      const paper = await request(this.path);
      if (!this.active || this.closed || this.state.denied) return;
      this.examTitle = paper.title;
      if (paper.finalized_at) return await this.close(paper);
      const offset = Date.parse(paper.server_time) - Date.now();
      this.clock = { instant: Date.parse(paper.server_time), anchor: performance.now() };
      await this.mutate(old => {
        if (this.closed || this.state.denied) return old;
        // Keep an acknowledgment that raced with this read.
        for (const item of paper.items) {
          const cached = old?.paper.items.find(i => i.slot === item.slot);
          if (cached && cached.revision >= item.revision) Object.assign(item, cached);
        }
        return { paper, offset, pending: old?.pending ?? [], conflicts: old?.conflicts ?? {},
          scratch: old?.scratch ?? "" };
      });
      if (!this.active || this.closed || this.state.denied || !this.record) return;
      this.show({ error: "", status: this.record.pending.length ? "Saving" : "Saved on server" });
      await this.flush();
    } catch (error) {
      if (!this.active || this.closed || this.state.denied) return;
      // Only expose a cached paper when the server cannot answer an access check.
      if (!this.record && offlineError(error)) await this.mutate(value => value);
      await this.failure(error);
    } finally {
      this.refreshing = false;
    }
  }

  async failure(error) {
    if (denied(error)) {
      this.state.denied = true;
      await this.mutate(() => undefined);
      this.show({ error: "Access to this attempt has ended.", denied: true });
    } else {
      const pending = this.record?.pending.length;
      const status = offlineError(error) && pending && !this.memoryOnly ? "On this device"
        : this.record && !pending ? "Saved on server" : "Save failed";
      this.show({ error: offlineError(error) ? "Connection unavailable. Retry when connected." : error.message, status });
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
    if (!this.record) return 0;
    const serverNow = this.clock ? this.clock.instant + (performance.now() - this.clock.anchor)
      : Date.now() + this.record.offset;
    return Date.parse(this.record.paper.deadline_at) - serverNow;
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
      const hasSendable = record.pending.some(e => !record.conflicts[e.slot]);
      if (!hasSendable) {
        this.show({ status: record.pending.length ? "Conflict" : "Saved on server" });
        return;
      }
      if (navigator.onLine === false || this.timeLeft() <= 0) {
        this.show({ status: "On this device" });
        return;
      }
      let edit;
      // Claim the current value in the same shared transaction used by enqueue.
      // Once sent, its body must remain identical for lost-acknowledgment replay.
      await this.mutate(current => {
        edit = current?.pending.find(e => !current.conflicts[e.slot]);
        if (edit) edit.dispatched = true;
        return current;
      });
      if (!edit) continue;
      if (!this.active || this.closed || this.state.denied) return;
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

  async submit({ acceptedOnly = false } = {}) {
    if (!this.active || this.closed || this.state.submitting || this.state.denied) return;
    this.show({ submitting: true, submitBlocked: false });
    try {
      await this.writes;
      if (acceptedOnly) {
        // Wait for any in-flight save before posting the terminal transition.
        if (this.sending) await this.sending;
      } else {
        await this.flush();
      }
      if (!this.record || this.closed) return;
      if (this.record.pending.length && !acceptedOnly) {
        this.show({ submitBlocked: true });
        return;
      }
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
    let accepted = receipt.items;
    if (!accepted && this.record?.pending.length) {
      try { accepted = (await request(this.path)).items; } catch { /* Receipt is already authoritative. */ }
    }
    await this.mutate(record => {
      const lastBySlot = new Map(record?.pending.map(edit => [edit.slot, edit]) ?? []);
      outstanding = [...lastBySlot.values()].filter(edit => {
        const item = accepted?.find(candidate => candidate.slot === edit.slot);
        if (!item || item.flagged !== edit.body.flagged) return true;
        if (item.kind === "written") return item.written_answer !== edit.body.written_answer;
        const ids = edit.body.selected_option_ids;
        return ids.length !== item.selected_option_ids.length || !ids.every(id => item.selected_option_ids.includes(id));
      }).map(edit => record.paper.items.find(item => item.slot === edit.slot).display_no).sort((a,b) => a-b);
      return undefined;
    });
    const { attempt_id, finalized_at, close_reason } = receipt;
    this.show({ receipt: { attempt_id, finalized_at, close_reason }, outstanding, title: this.examTitle, error: "" });
  }
}
