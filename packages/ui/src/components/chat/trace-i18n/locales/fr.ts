import type { TraceStrings } from "../types";

export const fr: TraceStrings = {
  reasoning: "Raisonnement",
  thinking: "Réflexion en cours",
  thought: "Réflexion terminée",
  working: "En cours",
  worked: "Terminé",
  workingOn: "En cours — {tool}",
  toolFallbackName: "outil",
  needsInput: "Votre réponse est requise",
  stopped: "Arrêté",
  failed: "Échec",
  usedTools: { one: "{count} outil utilisé", many: "{count} d’outils utilisés", other: "{count} outils utilisés" },
  thoughtAndUsedTools: {
    one: "Réflexion et {count} outil utilisé",
    many: "Réflexion et {count} d’outils utilisés",
    other: "Réflexion et {count} outils utilisés",
  },
  toolCalls: { one: "{count} appel d’outil", many: "{count} d’appels d’outils", other: "{count} appels d’outils" },
  usedTool: "Outil utilisé",
  cancelledTool: "Outil annulé",
  failedTool: "Échec de l’outil",
  runningTool: "Outil en cours",
  waitingOnTool: "En attente de l’outil",
  errorPrefix: "Erreur :",
  cancelledPrefix: "Annulé :",
};
