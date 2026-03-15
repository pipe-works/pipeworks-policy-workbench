let _fetchJson = null;
let _setStatus = null;

export function configureInventory({ fetchJson, setStatus }) {
  _fetchJson = fetchJson;
  _setStatus = setStatus;
}

export function requireInventoryDeps() {
  if (!_fetchJson || !_setStatus) {
    throw new Error("Inventory helpers are not configured.");
  }
}

export function fetchJson(url, options = undefined) {
  requireInventoryDeps();
  return _fetchJson(url, options);
}

export function setStatus(message) {
  requireInventoryDeps();
  _setStatus(message);
}
