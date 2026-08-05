export class DigivaultEnvError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DigivaultEnvError";
  }
}

export type DigivaultBackendConfig = {
  type: "digivault";
  supabaseUrlEnv: string;
  supabaseAnonKeyEnv: string;
  openRouterKeyEnv: string;
};

export type DigivaultResolvedEnv = {
  supabaseUrl: string;
  supabaseAnonKey: string;
  openRouterKey: string;
};

function readEnv(name: string): string {
  const value = process.env[name];
  if (typeof value !== "string" || !value.trim()) {
    throw new DigivaultEnvError("digivault backend is not configured");
  }
  return value.trim();
}

export function resolveDigivaultEnv(backend: DigivaultBackendConfig): DigivaultResolvedEnv {
  return {
    supabaseUrl: readEnv(backend.supabaseUrlEnv),
    supabaseAnonKey: readEnv(backend.supabaseAnonKeyEnv),
    openRouterKey: readEnv(backend.openRouterKeyEnv),
  };
}
