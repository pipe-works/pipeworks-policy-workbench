const AUTHORABLE_POLICY_TYPES = new Set([
  "species_block",
  "prompt",
  "image_block",
  "clothing_block",
  "tone_profile",
  "descriptor_layer",
  "registry",
]);

export function buildPolicySelectorLabel(item) {
  return `${item.policy_type}:${item.namespace}:${item.policy_key}:${item.variant}`;
}

export function isAuthorablePolicyType(policyType) {
  return AUTHORABLE_POLICY_TYPES.has(String(policyType || "").trim());
}
