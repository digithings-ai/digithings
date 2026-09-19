export type SeedApplyInput = {
  messages: ReadonlyArray<{ role: "user" | "assistant"; content: string }>;
  pending: string;
};

export function applyEmbedSeed(
  input: SeedApplyInput,
  ctrl: {
    seed: (messages: SeedApplyInput["messages"]) => void;
    send: (q: string) => void;
  },
): void {
  ctrl.seed(input.messages);
  const pending = input.pending.trim();
  if (pending) ctrl.send(pending);
}
