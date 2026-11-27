let connection;

function open() {
  if (!connection) connection = new Promise((resolve, reject) => {
    const request = indexedDB.open("folio-delivery", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("attempts");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  }).catch(error => { connection = undefined; throw error; });
  return connection;
}

// Every read-modify-write is a single IndexedDB transaction, including across tabs.
export async function change(account, attempt, update) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("attempts", "readwrite");
    const store = tx.objectStore("attempts");
    const key = [account, attempt];
    const read = store.get(key);
    let result;
    read.onsuccess = () => {
      result = update(read.result);
      if (result) store.put(result, key);
      else store.delete(key);
    };
    tx.oncomplete = () => resolve(result);
    tx.onabort = () => reject(tx.error || Error("Local storage unavailable"));
  });
}

export async function purgeDeliveryAccount(account) {
  window.dispatchEvent(new CustomEvent("folio-delivery-logout", { detail: account }));
  const channel = new BroadcastChannel("folio-delivery-logout");
  channel.postMessage(account);
  channel.close();
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("attempts", "readwrite");
    tx.objectStore("attempts").delete(IDBKeyRange.bound([account], [account, []]));
    tx.oncomplete = resolve;
    tx.onabort = () => reject(tx.error);
  });
}
