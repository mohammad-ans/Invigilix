export function responseOf(item) {
  return item.kind === "written"
    ? { written_answer: item.written_answer, flagged: item.flagged }
    : { selected_option_ids: item.selected_option_ids, flagged: item.flagged };
}

export function visibleItem(record, slot) {
  const item = record.paper.items.find(i => i.slot === slot);
  const last = record.pending.findLast(edit => edit.slot === slot);
  return last ? { ...item, ...last.body, pendingId: last.id } : item;
}

export function enqueue(record, observed, body, id) {
  const parent = record.pending.find(edit => edit.id === observed.pendingId);
  // A save can complete between the keystroke and the IndexedDB transaction.
  const item = record.paper.items.find(i => i.slot === observed.slot);
  const revision = observed.pendingId && item.ackId === observed.pendingId
    ? item.revision : observed.revision;
  // Replace only our direct, unsent leaf. Another tab may have dispatched the
  // parent or created a competing edit since this component last rendered it.
  if (parent?.dispatched === false && !record.pending.some(edit => edit.parent === parent.id)) {
    parent.id = id;
    parent.body = body;
    return;
  }
  record.pending.push({ id, slot: observed.slot, base_revision: revision, parent: parent?.id, dispatched: false, body });
}

export function accept(record, edit, ack) {
  if (!record.pending.some(e => e.id === edit.id)) return;
  const item = record.paper.items.find(i => i.slot === edit.slot);
  if (ack.revision >= item.revision) Object.assign(item, edit.body, ack, { ackId: edit.id });
  record.pending = record.pending.filter(e => e.id !== edit.id);
  for (const next of record.pending.filter(e => e.parent === edit.id)) {
    next.parent = null;
    next.base_revision = ack.revision;
  }
}

export function resolveConflict(record, slot, keepLocal) {
  const conflict = record.conflicts[slot];
  if (!conflict) return;
  const latest = visibleItem(record, slot);
  Object.assign(record.paper.items.find(i => i.slot === slot), conflict);
  record.pending = record.pending.filter(e => e.slot !== slot);
  delete record.conflicts[slot];
  if (keepLocal) enqueue(record, conflict, responseOf(latest), crypto.randomUUID());
}
