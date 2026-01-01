import { supportToolData } from "@/lib/support/tool-data";
import type { BrandTheme, SupportAssistantConfig } from "@/lib/support/types";

export const defaultBrandTheme = {
  "accent": "#2563eb",
  "surface": "#ffffff",
  "border": "#d8dee8",
  "mutedText": "#64748b",
  "success": "#15803d",
  "warning": "#b45309",
  "destructive": "#b91c1c",
  "focusRing": "#3b82f6"
} satisfies BrandTheme;

export const supportAssistantConfig = {
  ...{
  "companyName": "Northstar Cloud",
  "productName": "Northstar Sync",
  "assistantName": "Sync Support",
  "welcome": {
    "badge": "Logs and connector status supported",
    "title": "Resolve integration health issues",
    "subtitle": "Describe the connector problem and Sync Support will prepare an owner-ready handoff."
  },
  "labels": {
    "modalTrigger": "Open sync support",
    "modalClose": "Close support",
    "composerPlaceholder": "Describe the connector or access issue...",
    "composerInput": "Support issue input",
    "uploadButton": "Add screenshot or log",
    "send": "Send issue",
    "cancel": "Stop",
    "copy": "Copy summary",
    "refresh": "Refresh",
    "more": "More",
    "edit": "Edit",
    "previous": "Previous",
    "next": "Next",
    "scrollToBottom": "Scroll to bottom",
    "export": "Export as Markdown",
    "escalationCta": "Ready for integration owner",
    "loading": "Preparing integration handoff...",
    "success": "Integration handoff ready",
    "error": "Support handoff failed",
    "cancelled": "Support handoff cancelled"
  },
  "agentPrompt": {
    "persona": "an integration support specialist",
    "instructions": "Analyze connector sync and access issues, identify the affected integration area, and prepare a concise support handoff.",
    "responseStyle": "Use operational language with clear owner and SLA details."
  },
  "demoModeNotice": "Demo note: This is a mock support demo. Add OPENAI_API_KEY to .env.local to use real AI and connect your own tools.",
  "suggestedPrompts": [
    {
      "title": "Connector sync delayed",
      "label": "Triage sync",
      "prompt": "Salesforce connector sync is delayed.",
      "scenarioId": "sync_failure"
    },
    {
      "title": "User cannot reconnect",
      "label": "Check access",
      "prompt": "A teammate cannot reconnect the Salesforce integration.",
      "scenarioId": "auth_error"
    }
  ],
  "toolCardLabels": {
    "analyzeIssue": "Issue analysis",
    "createSupportSummary": "Support summary"
  },
  "toolCardDesign": {
    "density": "compact",
    "iconSet": "lucide",
    "statusBadgeStyle": "solid",
    "ticketSummaryLayout": "handoff"
  },
  "tools": [
    {
      "id": "analyzeIssue",
      "displayName": "Connector Analysis",
      "aiDescription": "Analyze a connector issue and identify affected service, severity, likely cause, and next step.",
      "realImplementationHint": "Call your integration telemetry API with connector, workspace, and error context.",
      "rendererType": "analysis"
    },
    {
      "id": "createSupportSummary",
      "displayName": "Integration Handoff",
      "aiDescription": "Create an integration-owner handoff summary from the connector analysis.",
      "realImplementationHint": "Create a ticket in Zendesk, Jira, Linear, or your support queue.",
      "rendererType": "summary"
    }
  ],
  "demoFlows": {
    "sync_failure": {
      "finalResponse": "The connector sync handoff is ready for Integration Ops.",
      "steps": [
        {
          "id": "analyze-connector-sync",
          "toolId": "analyzeIssue",
          "assistantText": "I found a connector sync pattern and will analyze the affected service.",
          "input": {
            "description": "Salesforce connector sync is delayed.",
            "service": "Sync Engine",
            "attachments": [
              {
                "name": "salesforce-sync.log",
                "type": "mock"
              }
            ],
            "scenarioId": "sync_failure"
          },
          "output": {
            "category": "sync_failure",
            "confidence": 91,
            "likelyCause": "Salesforce jobs are retrying after elevated API latency.",
            "affectedService": "Sync Engine",
            "severity": "high",
            "explanation": "Workspace access is healthy, but recent CRM records may appear late.",
            "nextStep": "Prepare a handoff with connector, region, and retry details.",
            "followUpQuestions": [
              "When did the last successful Salesforce sync complete?"
            ],
            "attachments": [
              {
                "name": "salesforce-sync.log",
                "type": "mock"
              }
            ]
          }
        },
        {
          "id": "create-connector-handoff",
          "toolId": "createSupportSummary",
          "assistantText": "I have enough connector context to prepare the handoff.",
          "input": {
            "issue": {
              "category": "sync_failure",
              "confidence": 91,
              "likelyCause": "Salesforce jobs are retrying after elevated API latency.",
              "affectedService": "Sync Engine",
              "severity": "high",
              "explanation": "Workspace access is healthy, but recent CRM records may appear late.",
              "nextStep": "Prepare a handoff with connector, region, and retry details.",
              "followUpQuestions": [
                "When did the last successful Salesforce sync complete?"
              ],
              "attachments": [
                {
                  "name": "salesforce-sync.log",
                  "type": "mock"
                }
              ]
            },
            "attachments": [
              {
                "name": "salesforce-sync.log",
                "type": "mock"
              }
            ],
            "scenarioId": "sync_failure"
          },
          "output": {
            "ticketId": "SYNC-2479",
            "priority": "P2",
            "customerImpact": "CRM updates are delayed for downstream teams.",
            "summary": "Sync Engine: Salesforce jobs are retrying after elevated API latency.",
            "recommendedOwner": "Integration Ops",
            "nextResponseSla": "Review within 2 business hours",
            "attachments": [
              "salesforce-sync.log"
            ]
          }
        }
      ]
    },
    "auth_error": {
      "finalResponse": "The integration access handoff is ready for Identity Support.",
      "steps": [
        {
          "id": "analyze-connector-auth",
          "toolId": "analyzeIssue",
          "assistantText": "I found an integration access pattern and will check the likely cause.",
          "input": {
            "description": "A teammate cannot reconnect the Salesforce integration.",
            "service": "Connector Auth",
            "attachments": [
              {
                "name": "oauth-error.png",
                "type": "mock"
              }
            ],
            "scenarioId": "auth_error"
          },
          "output": {
            "category": "auth_error",
            "confidence": 84,
            "likelyCause": "The integration user may be missing OAuth reconnect permission.",
            "affectedService": "Connector Auth",
            "severity": "medium",
            "explanation": "Only reconnect actions are blocked; existing sync jobs are still visible.",
            "nextStep": "Prepare a handoff with identity and connector ownership details.",
            "followUpQuestions": [
              "Is this affecting all connector admins or one teammate?"
            ],
            "attachments": [
              {
                "name": "oauth-error.png",
                "type": "mock"
              }
            ]
          }
        },
        {
          "id": "create-connector-auth-handoff",
          "toolId": "createSupportSummary",
          "assistantText": "I have enough access context to prepare the handoff.",
          "input": {
            "issue": {
              "category": "auth_error",
              "confidence": 84,
              "likelyCause": "The integration user may be missing OAuth reconnect permission.",
              "affectedService": "Connector Auth",
              "severity": "medium",
              "explanation": "Only reconnect actions are blocked; existing sync jobs are still visible.",
              "nextStep": "Prepare a handoff with identity and connector ownership details.",
              "followUpQuestions": [
                "Is this affecting all connector admins or one teammate?"
              ],
              "attachments": [
                {
                  "name": "oauth-error.png",
                  "type": "mock"
                }
              ]
            },
            "attachments": [
              {
                "name": "oauth-error.png",
                "type": "mock"
              }
            ],
            "scenarioId": "auth_error"
          },
          "output": {
            "ticketId": "AUTH-884",
            "priority": "P3",
            "customerImpact": "A teammate cannot reconnect the integration.",
            "summary": "Connector Auth: The integration user may be missing OAuth reconnect permission.",
            "recommendedOwner": "Identity Support",
            "nextResponseSla": "Review within 1 business day",
            "attachments": [
              "oauth-error.png"
            ]
          }
        }
      ]
    }
  }
},
  toolData: supportToolData,
} satisfies SupportAssistantConfig;
