import type { BrandTheme, DocsHostUiSpec } from "@/lib/docs/types";

export const defaultBrandTheme = {
  "accent": "#0369a1",
  "surface": "#ffffff",
  "border": "#dbe3ea",
  "mutedText": "#64748b",
  "focusRing": "#38bdf8"
} satisfies BrandTheme;

export const defaultDocsHostUi = {
  "version": 1,
  "root": {
    "type": "ContentShell",
    "props": {
      "productName": "Northstar Docs",
      "docsName": "Product Guides",
      "defaultPageId": "guided-onboarding",
      "pages": [
        {
          "id": "guided-onboarding",
          "title": "Guided Onboarding",
          "section": "Product guides",
          "description": "Set up a workspace, invite teammates, and publish your first customer guide.",
          "url": "/docs/guided-onboarding",
          "markdown": "## Create a workspace\n\nNorthstar workspaces keep product guides, owners, and release notes organized by team.\n\n## Invite teammates\n\nInvite teammates as editors when they need to update docs, or viewers when they only need review access.\n\n## Publish the guide\n\nPublish your first guide after assigning an owner, choosing a collection, and checking the preview.",
          "keywords": [
            "onboarding",
            "workspace",
            "guide",
            "publish",
            "setup"
          ],
          "relatedPageIds": [
            "roles-and-permissions",
            "release-notes"
          ]
        },
        {
          "id": "roles-and-permissions",
          "title": "Roles and Permissions",
          "section": "Product guides",
          "description": "Choose editor, reviewer, and viewer roles for a documentation workspace.",
          "url": "/docs/roles-and-permissions",
          "markdown": "## Editors\n\nEditors can update guides, manage screenshots, and publish approved changes.\n\n## Reviewers\n\nReviewers can leave comments and request changes before a guide is released.\n\n## Viewers\n\nViewers can read internal guides without changing the source content.",
          "keywords": [
            "roles",
            "permissions",
            "teammates",
            "workspace"
          ],
          "relatedPageIds": [
            "guided-onboarding",
            "release-notes"
          ]
        },
        {
          "id": "release-notes",
          "title": "Release Notes",
          "section": "Product guides",
          "description": "Prepare product updates and attach related docs before publishing.",
          "url": "/docs/release-notes",
          "markdown": "## Draft notes\n\nRelease notes summarize product changes and link readers to the guides they should read next.\n\n## Attach docs\n\nAttach related docs so support and customer success teams can answer follow-up questions quickly.\n\n## Publish updates\n\nSchedule release notes when launch timing matters across regions.",
          "keywords": [
            "release",
            "notes",
            "updates",
            "launch"
          ],
          "relatedPageIds": [
            "guided-onboarding",
            "roles-and-permissions"
          ]
        }
      ],
      "assistantPlacement": "sidebar"
    }
  }
} satisfies DocsHostUiSpec;
