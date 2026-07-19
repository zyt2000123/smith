export type LifecycleHook = {
  event: string;
  description: string;
  handler: string;
  detail: string;
};

// This is the built-in dispatch catalog, not a snapshot of a live
// HookManager: managers are created per runtime and register their handlers
// lazily. Keep it aligned with the concrete dispatch points in
// engine/execution/agent_loop.py.
export const LIFECYCLE_HOOKS: readonly LifecycleHook[] = [
  {
    event: "memory_after_turn_completed",
    description: "After a completed agent turn",
    handler: "MemoryLifecycleHooks",
    detail: "Records the completed turn and refreshes Smith's working memory.",
  },
  {
    event: "memory_after_turn_incomplete",
    description: "After an incomplete agent turn",
    handler: "MemoryLifecycleHooks",
    detail: "Persists partial work without promoting it to completed memory.",
  },
  {
    event: "memory_after_turn_failed",
    description: "After a failed agent turn",
    handler: "MemoryLifecycleHooks",
    detail: "Persists failed partial work with its terminal reason.",
  },
  {
    event: "memory_idle_tick",
    description: "During idle memory maintenance",
    handler: "MemoryLifecycleHooks",
    detail: "Runs the same maintenance service when Smith is idle.",
  },
  {
    event: "memory_daily_tick",
    description: "During daily memory maintenance",
    handler: "MemoryLifecycleHooks",
    detail: "Runs scheduled daily memory maintenance through the lifecycle hook.",
  },
];
