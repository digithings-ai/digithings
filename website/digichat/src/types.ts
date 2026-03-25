export interface Config {
  digigraphUrl: string;
  model: string;
  stream: boolean;
  openwebuiFormat: boolean;
  apiKey: string;
  title: string;
  subtitle: string;
}

export const CONFIG_DEFAULTS: Config = {
  digigraphUrl: "http://127.0.0.1:8000",
  model: "sitaas-rag",
  stream: true,
  openwebuiFormat: true,
  apiKey: "",
  title: "Digichat",
  subtitle: "DigiGraph",
};

export type HealthState = "unknown" | "ok" | "err";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** true while the assistant is still streaming */
  streaming?: boolean;
  /** true if the request errored */
  error?: boolean;
}
