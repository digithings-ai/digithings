import type { DocsAssistantConfig } from "./types";

export const docsAssistantConfig = {
  "productName": "Northstar Docs",
  "docsName": "Product Guides",
  "assistantName": "Product Docs Assistant",
  "welcome": {
    "headline": "Ask Product Guides",
    "body": "Search source pages, preview related content, and get concise answers grounded in these docs."
  },
  "labels": {
    "currentPage": "Current page",
    "source": "Source",
    "relatedPages": "Related pages",
    "openPage": "Open in preview",
    "headerSearch": "Search Product Guides with the assistant",
    "articleCtaTitle": "Need a targeted answer?",
    "articleCtaBody": "Use the assistant to search these docs with this page as context.",
    "articleCtaAction": "Ask Product Docs Assistant",
    "composerPlaceholder": "Ask about setup, auth, webhooks, examples, or the current page...",
    "previewWarning": "Preview config could not be loaded. Showing default template."
  },
  "suggestedPrompts": [
    {
      "title": "How do I get started?",
      "description": "Search the quickstart and related setup pages.",
      "prompt": "Find the fastest product setup path",
      "flowId": "auth401"
    },
    {
      "title": "Find release notes",
      "description": "Open product update docs.",
      "prompt": "Find release note docs"
    }
  ],
  "tools": [
    {
      "id": "searchDocs",
      "displayName": "Search docs",
      "aiDescription": "Search the documentation corpus and return relevant source pages with snippets.",
      "realImplementationHint": "Replace the mock search with your docs index, vector store, or search provider.",
      "rendererType": "sourceResults"
    },
    {
      "id": "openPage",
      "displayName": "Open page metadata",
      "aiDescription": "Return metadata and a preview for a documentation page. This does not mutate the visible page.",
      "realImplementationHint": "Look up the page by id or URL in your CMS and return safe metadata.",
      "rendererType": "pagePreview"
    },
    {
      "id": "generateCodeSnippet",
      "displayName": "Generate code snippet",
      "aiDescription": "Return a short implementation snippet for a docs topic and programming language.",
      "realImplementationHint": "Use your SDK examples or an internal snippet library for production code.",
      "rendererType": "codeSnippet"
    }
  ],
  "demoModeNotice": "Demo mode is deterministic because no OPENAI_API_KEY is set. Add a key to enable live model responses.",
  "demoFlows": {
    "auth401": {
      "title": "Search Guided Onboarding",
      "triggerPhrases": [
        "401",
        "auth",
        "authentication",
        "api key",
        "setup"
      ],
      "steps": [
        {
          "id": "search-auth-docs",
          "assistantText": "I will search the source docs first.",
          "toolId": "searchDocs",
          "input": {
            "query": "Guided Onboarding setup",
            "limit": 3
          },
          "output": {
            "query": "Guided Onboarding setup",
            "results": [
              {
                "pageId": "guided-onboarding",
                "title": "Guided Onboarding",
                "section": "Product guides",
                "url": "/docs/guided-onboarding",
                "snippet": "Set up a workspace, invite teammates, and publish your first customer guide.",
                "score": 90
              },
              {
                "pageId": "guided-onboarding",
                "title": "Guided Onboarding",
                "section": "Product guides",
                "url": "/docs/guided-onboarding",
                "snippet": "Set up a workspace, invite teammates, and publish your first customer guide.",
                "score": 78
              }
            ]
          }
        },
        {
          "id": "open-auth-page",
          "assistantText": "This page is the strongest source match.",
          "toolId": "openPage",
          "input": {
            "pageId": "guided-onboarding"
          },
          "output": {
            "pageId": "guided-onboarding",
            "title": "Guided Onboarding",
            "section": "Product guides",
            "url": "/docs/guided-onboarding",
            "description": "Set up a workspace, invite teammates, and publish your first customer guide.",
            "relatedPageIds": [
              "roles-and-permissions",
              "release-notes"
            ]
          }
        }
      ],
      "finalResponse": "Use Guided Onboarding as the source of truth, then verify related setup on Guided Onboarding."
    },
    "webhooks": {
      "title": "Find Guided Onboarding",
      "triggerPhrases": [
        "webhook",
        "webhooks",
        "event",
        "events"
      ],
      "steps": [
        {
          "id": "search-webhook-docs",
          "assistantText": "I will search for the relevant event or webhook page.",
          "toolId": "searchDocs",
          "input": {
            "query": "Guided Onboarding setup",
            "limit": 3
          },
          "output": {
            "query": "Guided Onboarding setup",
            "results": [
              {
                "pageId": "guided-onboarding",
                "title": "Guided Onboarding",
                "section": "Product guides",
                "url": "/docs/guided-onboarding",
                "snippet": "Set up a workspace, invite teammates, and publish your first customer guide.",
                "score": 90
              },
              {
                "pageId": "guided-onboarding",
                "title": "Guided Onboarding",
                "section": "Product guides",
                "url": "/docs/guided-onboarding",
                "snippet": "Set up a workspace, invite teammates, and publish your first customer guide.",
                "score": 78
              }
            ]
          }
        },
        {
          "id": "open-webhook-page",
          "assistantText": "I will open the best matching page metadata.",
          "toolId": "openPage",
          "input": {
            "pageId": "guided-onboarding"
          },
          "output": {
            "pageId": "guided-onboarding",
            "title": "Guided Onboarding",
            "section": "Product guides",
            "url": "/docs/guided-onboarding",
            "description": "Set up a workspace, invite teammates, and publish your first customer guide.",
            "relatedPageIds": [
              "roles-and-permissions",
              "release-notes"
            ]
          }
        }
      ],
      "finalResponse": "Start with Guided Onboarding, then review related pages before implementation."
    },
    "codeExample": {
      "title": "Generate Guided Onboarding",
      "triggerPhrases": [
        "code",
        "snippet",
        "example",
        "typescript",
        "curl"
      ],
      "steps": [
        {
          "id": "search-example-docs",
          "assistantText": "I will search for the source page for this example.",
          "toolId": "searchDocs",
          "input": {
            "query": "Guided Onboarding code example",
            "limit": 3
          },
          "output": {
            "query": "Guided Onboarding code example",
            "results": [
              {
                "pageId": "guided-onboarding",
                "title": "Guided Onboarding",
                "section": "Product guides",
                "url": "/docs/guided-onboarding",
                "snippet": "Set up a workspace, invite teammates, and publish your first customer guide.",
                "score": 90
              }
            ]
          }
        },
        {
          "id": "generate-example",
          "assistantText": "I will return a focused implementation snippet.",
          "toolId": "generateCodeSnippet",
          "input": {
            "topic": "Guided Onboarding",
            "language": "typescript"
          },
          "output": {
            "topic": "Guided Onboarding",
            "language": "typescript",
            "docsUrl": "/docs/guided-onboarding",
            "notes": [
              "Replace this demo snippet with your production example."
            ],
            "code": "const response = await fetch(\"/api/example\");"
          }
        }
      ],
      "finalResponse": "Use this typescript example as a starting point, then adapt environment variables and error handling for your app."
    }
  }
} satisfies DocsAssistantConfig;
