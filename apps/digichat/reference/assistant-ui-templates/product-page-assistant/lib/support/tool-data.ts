import type { SupportToolData } from "@/lib/support/types";

export const supportToolData = {
  "serviceOptions": [
    "Sync Engine",
    "Connector Auth",
    "Webhook Delivery",
    "API"
  ],
  "mockAccountStatus": {
    "accountName": "Acme Operations",
    "plan": "Scale",
    "region": "us-west",
    "accountHealth": "Sync degraded"
  },
  "escalationLabels": {
    "defaultOwner": "Tier 2 Sync Support",
    "defaultSla": "First response within 2 business hours"
  },
  "priorityLabels": {
    "P1": "Critical",
    "P2": "High",
    "P3": "Normal"
  },
  "scenarioPacks": [
    {
      "id": "sync_failure",
      "title": "Connector sync delay",
      "triggerPhrases": [
        "sync",
        "connector",
        "salesforce",
        "delay"
      ],
      "defaultAffectedService": "Sync Engine",
      "mockAttachments": [
        "salesforce-sync.log"
      ],
      "firstResponse": "I will review connector health and retry activity.",
      "analysis": {
        "category": "sync_failure",
        "likelyCause": "Salesforce jobs are retrying after elevated API latency.",
        "severity": "high",
        "explanation": "Workspace access is healthy, but recent CRM records may appear late.",
        "nextStep": "Prepare a handoff with connector, region, and retry details."
      },
      "summary": {
        "ticketId": "SYNC-2479",
        "priority": "P2",
        "customerImpact": "CRM updates are delayed for downstream teams.",
        "recommendedOwner": "Integration Ops",
        "nextResponseSla": "Review within 2 business hours"
      }
    },
    {
      "id": "auth_error",
      "title": "Connector reconnect blocked",
      "triggerPhrases": [
        "reconnect",
        "access",
        "oauth",
        "permission"
      ],
      "defaultAffectedService": "Connector Auth",
      "mockAttachments": [
        "oauth-error.png"
      ],
      "firstResponse": "I will review the reconnect report and access details.",
      "analysis": {
        "category": "auth_error",
        "likelyCause": "The integration user may be missing OAuth reconnect permission.",
        "severity": "medium",
        "explanation": "Only reconnect actions are blocked; existing sync jobs are still visible.",
        "nextStep": "Prepare a handoff with identity and connector ownership details."
      },
      "summary": {
        "ticketId": "AUTH-884",
        "priority": "P3",
        "customerImpact": "A teammate cannot reconnect the integration.",
        "recommendedOwner": "Identity Support",
        "nextResponseSla": "Review within 1 business day"
      }
    }
  ]
} satisfies SupportToolData;
