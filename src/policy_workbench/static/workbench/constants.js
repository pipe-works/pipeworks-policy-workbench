export const THEME_STORAGE_KEY = "ppw-theme";
export const HASH_REFRESH_LABEL = "Refresh Hash Snapshot";
export const SYNC_REFRESH_LABEL = "Refresh Dry-Run Plan";
export const SYNC_APPLY_LABEL = "Apply Create/Update";
export const SYNC_STEP_KEYS = new Set(["build", "review", "apply"]);
export const SYNC_ACTION_SORT_ORDER = {
  update: 0,
  create: 1,
  target_only: 2,
  unchanged: 3,
};
