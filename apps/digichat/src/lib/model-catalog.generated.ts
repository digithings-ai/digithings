// GENERATED FILE -- do not edit. Produced by scripts/refresh_model_catalog.py
// (`make model-catalog`) from models.dev; validated by `make model-catalog-check`.
// Source of truth: config/model-catalog.json. Edit the generator, not this file.
import type { ModelCatalogEntry } from "./model-catalog";

export const MODEL_CATALOG_SCHEMA_VERSION = 1;

export const MODEL_CATALOG_PROVIDERS = ["anthropic", "deepseek", "fireworks-ai", "google", "groq", "ollama-cloud", "openai", "openrouter", "togetherai", "xai"] as const;

export const MODEL_CATALOG_META = {
  "schema_version": 1,
  "source": "models.dev",
  "source_url": "https://models.dev/catalog.json",
  "fetched_at": "2026-10-02T23:38:18+00:00",
  "providers": [
    "anthropic",
    "deepseek",
    "fireworks-ai",
    "google",
    "groq",
    "ollama-cloud",
    "openai",
    "openrouter",
    "togetherai",
    "xai"
  ]
} as const;

export const MODEL_CATALOG_BYOK_PROVIDER_MAP: Record<string, string> = {"anthropic": "anthropic", "deepseek": "deepseek", "fireworks": "fireworks-ai", "gemini": "google", "groq": "groq", "openai": "openai", "openrouter": "openrouter", "together": "togetherai", "xai": "xai"};

export const MODEL_CATALOG_ROUTABLE_BYOK_MODEL_IDS: Record<string, readonly string[]> = {
  "anthropic": [
    "claude-haiku-4-20250514",
    "claude-opus-4-20250514",
    "claude-sonnet-4-20250514"
  ],
  "gemini": [
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-2.5-pro"
  ],
  "openai": [
    "gpt-4o",
    "gpt-4o-mini",
    "o4-mini"
  ],
  "openrouter": [
    "auto",
    "claude-sonnet-4",
    "cohere/north-mini-code:free",
    "deepseek-v4-flash",
    "deepseek-v4-flash-0731",
    "deepseek-v4-flash:online",
    "deepseek-v4-pro",
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-v4-flash-0731",
    "deepseek/deepseek-v4-flash:online",
    "deepseek/deepseek-v4-pro",
    "dots-3-note-preview:free",
    "dots-studio/dots-3-note-preview:free",
    "gemini-2.0-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.7-flash:online",
    "gemma-3-12b-it",
    "gemma-4-26b-a4b-it:free",
    "gemma-4-31b-it:free",
    "glm-5.3-flash",
    "google/gemini-3.1-flash-lite",
    "google/gemini-3.7-flash",
    "google/gemini-3.7-flash:online",
    "google/gemma-3-12b-it",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-5.6-luna",
    "gpt-5.6-luna:online",
    "gpt-5.6-sol",
    "gpt-5.6-sol:online",
    "gpt-oss-120b",
    "gpt-oss-20b",
    "gpt-oss-20b:free",
    "inclusionai/ling-3.0-flash",
    "inclusionai/ling-3.0-flash-fin:free",
    "inclusionai/ling-3.0-flash-sante:free",
    "inkling-small:free",
    "inkling:free",
    "laguna-s-2.1:free",
    "laguna-xs-2.1:free",
    "lfm-2.5-2.6b:free",
    "ling-3.0-flash",
    "ling-3.0-flash-fin:free",
    "ling-3.0-flash-sante:free",
    "liquid/lfm-2.5-2.6b:free",
    "llama-3.1-8b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
    "mistral-nemo",
    "mistral-small-3.2-24b-instruct",
    "mistralai/mistral-nemo",
    "mistralai/mistral-small-3.2-24b-instruct",
    "nemotron-3-nano-30b-a3b",
    "nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "nemotron-3-super-120b-a12b:free",
    "nemotron-3-ultra-550b-a55b:free",
    "nemotron-3.5-lightning:free",
    "nex-agi/nex-n2.5-mini:free",
    "nex-agi/nex-n2.5-pro:free",
    "nex-n2.5-mini:free",
    "nex-n2.5-pro:free",
    "north-mini-code:free",
    "nvidia/nemotron-3-nano-30b-a3b",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3.5-lightning:free",
    "openai/gpt-5.6-luna",
    "openai/gpt-5.6-luna:online",
    "openai/gpt-5.6-sol",
    "openai/gpt-5.6-sol:online",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-20b:free",
    "poolside/laguna-s-2.1:free",
    "poolside/laguna-xs-2.1:free",
    "qwen/qwen3-30b-a3b-instruct-2507",
    "qwen/qwen3.7-flash",
    "qwen3-30b-a3b-instruct-2507",
    "qwen3.7-flash",
    "thinkingmachines/inkling-small:free",
    "thinkingmachines/inkling:free",
    "z-ai/glm-5.3-flash"
  ],
  "xai": [
    "grok-4-3",
    "grok-4.5"
  ]
};

export const MODEL_CATALOG_BY_PROVIDER: Record<string, readonly ModelCatalogEntry[]> = {
  "anthropic": [
    {
      "id": "claude-fable-5",
      "label": "Claude Fable 5",
      "cost_input_usd_per_million": 10.0,
      "cost_output_usd_per_million": 50.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "claude-fable-5-1",
      "label": "Claude Fable 5.1",
      "cost_input_usd_per_million": 10.0,
      "cost_output_usd_per_million": 50.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "claude-haiku-4-5",
      "label": "Claude Haiku 4.5 (latest)",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 5.0,
      "context_window": 200000,
      "max_output_tokens": 64000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "claude-haiku-4-5-20251001",
      "label": "Claude Haiku 4.5",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 5.0,
      "context_window": 200000,
      "max_output_tokens": 64000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "claude-opus-4-5",
      "label": "Claude Opus 4.5 (latest)",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 25.0,
      "context_window": 200000,
      "max_output_tokens": 64000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "claude-opus-4-5-20251101",
      "label": "Claude Opus 4.5",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 25.0,
      "context_window": 200000,
      "max_output_tokens": 64000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "claude-opus-4-6",
      "label": "Claude Opus 4.6",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 25.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "claude-opus-4-7",
      "label": "Claude Opus 4.7",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 25.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "claude-opus-4-8",
      "label": "Claude Opus 4.8",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 25.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "claude-opus-5",
      "label": "Claude Opus 5",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 25.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "claude-opus-5-5",
      "label": "Claude Opus 5.5",
      "cost_input_usd_per_million": 4.0,
      "cost_output_usd_per_million": 20.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "claude-sonnet-4-5",
      "label": "Claude Sonnet 4.5 (latest)",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 15.0,
      "context_window": 1000000,
      "max_output_tokens": 64000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "claude-sonnet-4-5-20250929",
      "label": "Claude Sonnet 4.5",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 15.0,
      "context_window": 1000000,
      "max_output_tokens": 64000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "claude-sonnet-4-6",
      "label": "Claude Sonnet 4.6",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 15.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "claude-sonnet-5",
      "label": "Claude Sonnet 5",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 10.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "claude-sonnet-5-5",
      "label": "Claude Sonnet 5.5",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 10.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    }
  ],
  "deepseek": [
    {
      "id": "deepseek-flash",
      "label": "DeepSeek V4.1 Flash",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.6,
      "context_window": 1000000,
      "max_output_tokens": 393216,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek-v4-flash",
      "label": "DeepSeek V4 Flash",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.6,
      "context_window": 1000000,
      "max_output_tokens": 393216,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek-v4-flash-vision-exp",
      "label": "DeepSeek V4 Flash Vision Exp",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.6,
      "context_window": 1000000,
      "max_output_tokens": 393216,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek-v4-pro",
      "label": "DeepSeek V4 Pro",
      "cost_input_usd_per_million": 0.66,
      "cost_output_usd_per_million": 1.98,
      "context_window": 1000000,
      "max_output_tokens": 393216,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    }
  ],
  "fireworks-ai": [
    {
      "id": "accounts/fireworks/models/deepseek-v4p1-flash",
      "label": "DeepSeek V4.1 Flash",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.2,
      "context_window": 1000000,
      "max_output_tokens": 384000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "accounts/fireworks/models/ember-1",
      "label": "Ember-1",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 15.0,
      "context_window": 1048576,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "accounts/fireworks/models/glm-5p3",
      "label": "GLM 5.3",
      "cost_input_usd_per_million": 1.4,
      "cost_output_usd_per_million": 4.4,
      "context_window": 1048573,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "accounts/fireworks/models/glm-5p3-flash",
      "label": "GLM 5.3 Flash",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.5,
      "context_window": 1048573,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "accounts/fireworks/models/gpt-oss-120b",
      "label": "GPT OSS 120B",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.6,
      "context_window": 131072,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "accounts/fireworks/models/inkling",
      "label": "Inkling",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 4.05,
      "context_window": 1048576,
      "max_output_tokens": 1048576,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "accounts/fireworks/models/kimi-k3",
      "label": "Kimi K3",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 15.0,
      "context_window": 1048576,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "flagship"
    },
    {
      "id": "accounts/fireworks/models/minimax-m3",
      "label": "MiniMax-M3",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.2,
      "context_window": 512000,
      "max_output_tokens": 512000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "accounts/fireworks/models/nemotron-3-ultra-nvfp4",
      "label": "Nemotron 3 Ultra 550B A55B",
      "cost_input_usd_per_million": 0.6,
      "cost_output_usd_per_million": 2.4,
      "context_window": 262144,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "accounts/fireworks/models/nemotron-lightning-3p5-30b-a3b",
      "label": "Nemotron 3.5 Lightning 30B A3B",
      "cost_input_usd_per_million": 0.05,
      "cost_output_usd_per_million": 0.2,
      "context_window": 262144,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "accounts/fireworks/models/qwen3p8-2p4t-a95b",
      "label": "Qwen3.8 2.4T A95B",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 262144,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "accounts/fireworks/models/qwen3p8-max",
      "label": "Qwen3.8 Max",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 262144,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "accounts/fireworks/routers/deepseek-flash-latest",
      "label": "DeepSeek Flash Latest",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.2,
      "context_window": 1000000,
      "max_output_tokens": 384000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "accounts/fireworks/routers/glm-5p3-fast",
      "label": "GLM 5.3 Fast",
      "cost_input_usd_per_million": 2.1,
      "cost_output_usd_per_million": 6.6,
      "context_window": 1048572,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "accounts/fireworks/routers/glm-fast-latest",
      "label": "GLM 5.3 Fast (Latest)",
      "cost_input_usd_per_million": 2.1,
      "cost_output_usd_per_million": 6.6,
      "context_window": 1048572,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "accounts/fireworks/routers/glm-flash-latest",
      "label": "GLM Flash Latest (GLM 5.3 Flash)",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.5,
      "context_window": 1048573,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "accounts/fireworks/routers/glm-latest",
      "label": "GLM Latest",
      "cost_input_usd_per_million": 1.4,
      "cost_output_usd_per_million": 4.4,
      "context_window": 1048573,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "accounts/fireworks/routers/kimi-fast-latest",
      "label": "Kimi Fast Latest",
      "cost_input_usd_per_million": 4.5,
      "cost_output_usd_per_million": 22.5,
      "context_window": 1048576,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "flagship"
    },
    {
      "id": "accounts/fireworks/routers/kimi-k3-fast",
      "label": "Kimi K3 Fast",
      "cost_input_usd_per_million": 4.5,
      "cost_output_usd_per_million": 22.5,
      "context_window": 1048576,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "flagship"
    },
    {
      "id": "accounts/fireworks/routers/kimi-latest",
      "label": "Kimi Latest",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 15.0,
      "context_window": 1048576,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "flagship"
    },
    {
      "id": "accounts/fireworks/routers/minimax-latest",
      "label": "MiniMax Latest",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.2,
      "context_window": 512000,
      "max_output_tokens": 512000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "accounts/fireworks/routers/qwen-max-latest",
      "label": "Qwen Max Latest (Qwen3.8 Max)",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 262144,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    }
  ],
  "google": [
    {
      "id": "deep-research-max-preview-04-2026",
      "label": "Deep Research Max Preview (Apr-21-2026)",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 12.0,
      "context_window": 131072,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "deep-research-preview-04-2026",
      "label": "Deep Research Preview (Apr-21-2026)",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 12.0,
      "context_window": 131072,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-2.5-computer-use-preview-10-2025",
      "label": "Gemini 2.5 Computer Use Preview 10-2025",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 10.0,
      "context_window": 128000,
      "max_output_tokens": 64000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-2.5-flash",
      "label": "Gemini 2.5 Flash",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 2.5,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "audio",
        "video",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-2.5-flash-image",
      "label": "Nano Banana",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 30.0,
      "context_window": 32768,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-2.5-flash-lite",
      "label": "Gemini 2.5 Flash-Lite",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.4,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "audio",
        "video",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-2.5-flash-preview-tts",
      "label": "Gemini 2.5 Flash Preview TTS",
      "cost_input_usd_per_million": 0.5,
      "cost_output_usd_per_million": 10.0,
      "context_window": 8192,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "audio"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-2.5-pro",
      "label": "Gemini 2.5 Pro",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 10.0,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "audio",
        "video",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-2.5-pro-preview-tts",
      "label": "Gemini 2.5 Pro Preview TTS",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 20.0,
      "context_window": 8192,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "audio"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-3-flash-preview",
      "label": "Gemini 3 Flash Preview",
      "cost_input_usd_per_million": 0.5,
      "cost_output_usd_per_million": 3.0,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-3-pro-image",
      "label": "Nano Banana Pro",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 120.0,
      "context_window": 65536,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-3-pro-image-preview",
      "label": "Nano Banana Pro",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 120.0,
      "context_window": 131072,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-3.1-flash-image",
      "label": "Nano Banana 2",
      "cost_input_usd_per_million": 0.5,
      "cost_output_usd_per_million": 60.0,
      "context_window": 131072,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image",
        "video",
        "pdf"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-3.1-flash-image-preview",
      "label": "Nano Banana 2",
      "cost_input_usd_per_million": 0.5,
      "cost_output_usd_per_million": 60.0,
      "context_window": 65536,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-3.1-flash-lite",
      "label": "Gemini 3.1 Flash Lite",
      "cost_input_usd_per_million": 0.25,
      "cost_output_usd_per_million": 1.5,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-3.1-flash-lite-image",
      "label": "Nano Banana 2 Lite",
      "cost_input_usd_per_million": 0.25,
      "cost_output_usd_per_million": 30.0,
      "context_window": 65536,
      "max_output_tokens": 4096,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-3.1-flash-lite-preview",
      "label": "Gemini 3.1 Flash Lite Preview",
      "cost_input_usd_per_million": 0.25,
      "cost_output_usd_per_million": 1.5,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-3.1-flash-live-preview",
      "label": "Gemini 3.1 Flash Live Preview",
      "cost_input_usd_per_million": 0.75,
      "cost_output_usd_per_million": 4.5,
      "context_window": 131072,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio"
      ],
      "modalities_output": [
        "text",
        "audio"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-3.1-flash-tts-preview",
      "label": "Gemini 3.1 Flash TTS Preview",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 20.0,
      "context_window": 8192,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "audio"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-3.1-pro-preview",
      "label": "Gemini 3.1 Pro Preview",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 12.0,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-3.1-pro-preview-customtools",
      "label": "Gemini 3.1 Pro Preview Custom Tools",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 12.0,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-3.5-flash",
      "label": "Gemini 3.5 Flash",
      "cost_input_usd_per_million": 1.5,
      "cost_output_usd_per_million": 9.0,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-3.5-flash-lite",
      "label": "Gemini 3.5 Flash Lite",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 2.5,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-3.5-live-translate-preview",
      "label": "Gemini 3.5 Live Translate Preview",
      "cost_input_usd_per_million": 3.5,
      "cost_output_usd_per_million": 21.0,
      "context_window": 16384,
      "max_output_tokens": 32768,
      "modalities_input": [
        "audio"
      ],
      "modalities_output": [
        "audio",
        "text"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "gemini-3.6-flash",
      "label": "Gemini 3.6 Flash",
      "cost_input_usd_per_million": 0.75,
      "cost_output_usd_per_million": 3.75,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-3.7-flash",
      "label": "Gemini 3.7 Flash",
      "cost_input_usd_per_million": 0.75,
      "cost_output_usd_per_million": 3.75,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-3.8-flash",
      "label": "Gemini 3.8 Flash",
      "cost_input_usd_per_million": 0.75,
      "cost_output_usd_per_million": 3.75,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-embedding-001",
      "label": "Gemini Embedding 001",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.0,
      "context_window": 2048,
      "max_output_tokens": 1,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-embedding-2",
      "label": "Gemini Embedding 2",
      "cost_input_usd_per_million": 0.2,
      "cost_output_usd_per_million": 0.0,
      "context_window": 8192,
      "max_output_tokens": 1,
      "modalities_input": [
        "text",
        "image",
        "audio",
        "video",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-flash-latest",
      "label": "Gemini Flash Latest",
      "cost_input_usd_per_million": 0.75,
      "cost_output_usd_per_million": 3.75,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-flash-lite-latest",
      "label": "Gemini Flash-Lite Latest",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 2.5,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemini-omni-flash-preview",
      "label": "Gemini Omni Flash Preview",
      "cost_input_usd_per_million": 1.5,
      "cost_output_usd_per_million": 17.5,
      "context_window": 131072,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "video"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gemma-4-26b-a4b-it",
      "label": "Gemma 4 26B A4B IT",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "gemma-4-31b-it",
      "label": "Gemma 4 31B IT",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "lyria-3-clip-preview",
      "label": "Lyria 3 Clip Preview",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text",
        "audio"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "free"
    },
    {
      "id": "lyria-3-pro-preview",
      "label": "Lyria 3 Pro Preview",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text",
        "audio"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "free"
    },
    {
      "id": "veo-3.1-fast-generate-preview",
      "label": "Veo 3.1 fast",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 480,
      "max_output_tokens": 8192,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "video"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "veo-3.1-generate-preview",
      "label": "Veo 3.1",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 480,
      "max_output_tokens": 8192,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "video"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "veo-3.1-lite-generate-preview",
      "label": "Veo 3.1 lite",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 480,
      "max_output_tokens": 8192,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "video"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    }
  ],
  "groq": [
    {
      "id": "allam-2-7b",
      "label": "ALLaM-2-7b",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 4096,
      "max_output_tokens": 4096,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "free"
    },
    {
      "id": "canopylabs/orpheus-arabic-saudi",
      "label": "Canopy Labs Orpheus Arabic Saudi",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 4000,
      "max_output_tokens": 50000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "audio"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "canopylabs/orpheus-v1-english",
      "label": "Canopy Labs Orpheus V1 English",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 4000,
      "max_output_tokens": 50000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "audio"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "groq/compound",
      "label": "Compound",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 131072,
      "max_output_tokens": 8192,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "groq/compound-mini",
      "label": "Compound Mini",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 131072,
      "max_output_tokens": 8192,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "llama-3.1-8b-instant",
      "label": "Llama 3.1 8B",
      "cost_input_usd_per_million": 0.05,
      "cost_output_usd_per_million": 0.08,
      "context_window": 131072,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "llama-3.3-70b-versatile",
      "label": "Llama 3.3 70B",
      "cost_input_usd_per_million": 0.59,
      "cost_output_usd_per_million": 0.79,
      "context_window": 131072,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "meta-llama/llama-prompt-guard-2-22m",
      "label": "Llama Prompt Guard 2 22M",
      "cost_input_usd_per_million": 0.03,
      "cost_output_usd_per_million": 0.03,
      "context_window": 512,
      "max_output_tokens": 512,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "meta-llama/llama-prompt-guard-2-86m",
      "label": "Prompt Guard 2 86M",
      "cost_input_usd_per_million": 0.04,
      "cost_output_usd_per_million": 0.04,
      "context_window": 512,
      "max_output_tokens": 512,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "openai/gpt-oss-120b",
      "label": "GPT OSS 120B",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.6,
      "context_window": 131072,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "openai/gpt-oss-20b",
      "label": "GPT OSS 20B",
      "cost_input_usd_per_million": 0.075,
      "cost_output_usd_per_million": 0.3,
      "context_window": 131072,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "openai/gpt-oss-safeguard-20b",
      "label": "Safety GPT OSS 20B",
      "cost_input_usd_per_million": 0.075,
      "cost_output_usd_per_million": 0.3,
      "context_window": 131072,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3.6-27b",
      "label": "Qwen3.6 27B",
      "cost_input_usd_per_million": 0.6,
      "cost_output_usd_per_million": 3.0,
      "context_window": 131072,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3.8-27b",
      "label": "Qwen3.8 27B",
      "cost_input_usd_per_million": 0.8,
      "cost_output_usd_per_million": 4.0,
      "context_window": 131042,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "whisper-large-v3",
      "label": "Whisper",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": null,
      "max_output_tokens": null,
      "modalities_input": [
        "audio"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "whisper-large-v3-turbo",
      "label": "Whisper Large V3 Turbo",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": null,
      "max_output_tokens": null,
      "modalities_input": [
        "audio"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    }
  ],
  "ollama-cloud": [
    {
      "id": "deepseek-v4-flash",
      "label": "deepseek-v4-flash",
      "cost_input_usd_per_million": 0.22,
      "cost_output_usd_per_million": 0.66,
      "context_window": 1048576,
      "max_output_tokens": 1048576,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek-v4-flash:0731",
      "label": "DeepSeek V4 Flash 0731",
      "cost_input_usd_per_million": 0.22,
      "cost_output_usd_per_million": 0.66,
      "context_window": 1048576,
      "max_output_tokens": 1048576,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek-v4-pro",
      "label": "deepseek-v4-pro",
      "cost_input_usd_per_million": 0.66,
      "cost_output_usd_per_million": 1.98,
      "context_window": 1048576,
      "max_output_tokens": 1048576,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek-v4-pro:0813",
      "label": "DeepSeek V4 Pro 0813",
      "cost_input_usd_per_million": 0.66,
      "cost_output_usd_per_million": 1.98,
      "context_window": 1048576,
      "max_output_tokens": 1048576,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek-v4.1-flash",
      "label": "DeepSeek V4.1 Flash",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.6,
      "context_window": 1048576,
      "max_output_tokens": 384000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "gemma4:31b",
      "label": "gemma4:31b",
      "cost_input_usd_per_million": 0.14,
      "cost_output_usd_per_million": 0.4,
      "context_window": 262144,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "glm-5.1",
      "label": "glm-5.1",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 3.2,
      "context_window": 202752,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "glm-5.2",
      "label": "GLM-5.2",
      "cost_input_usd_per_million": 1.4,
      "cost_output_usd_per_million": 4.4,
      "context_window": 976000,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "glm-5.3",
      "label": "GLM-5.3",
      "cost_input_usd_per_million": 1.4,
      "cost_output_usd_per_million": 4.4,
      "context_window": 1048576,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "glm-5.3-flash",
      "label": "GLM-5.3-Flash",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.5,
      "context_window": 1000000,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image",
        "video",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "gpt-oss:120b",
      "label": "gpt-oss:120b",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.6,
      "context_window": 131072,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "gpt-oss:20b",
      "label": "gpt-oss:20b",
      "cost_input_usd_per_million": 0.07,
      "cost_output_usd_per_million": 0.3,
      "context_window": 131072,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "kimi-k2.5",
      "label": "kimi-k2.5",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 262144,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "kimi-k2.6",
      "label": "kimi-k2.6",
      "cost_input_usd_per_million": 0.95,
      "cost_output_usd_per_million": 4.0,
      "context_window": 262144,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "kimi-k2.7-code",
      "label": "kimi-k2.7-code",
      "cost_input_usd_per_million": 0.95,
      "cost_output_usd_per_million": 4.0,
      "context_window": 262144,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "kimi-k3",
      "label": "kimi-k3",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 15.0,
      "context_window": 1048576,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "flagship"
    },
    {
      "id": "minimax-m2.5",
      "label": "minimax-m2.5",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 204800,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "minimax-m2.7",
      "label": "minimax-m2.7",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.2,
      "context_window": 196608,
      "max_output_tokens": 196608,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "minimax-m3",
      "label": "minimax-m3",
      "cost_input_usd_per_million": 0.6,
      "cost_output_usd_per_million": 2.4,
      "context_window": 512000,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "mistral-large-3:675b",
      "label": "mistral-large-3:675b",
      "cost_input_usd_per_million": 0.5,
      "cost_output_usd_per_million": 1.5,
      "context_window": 262144,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "nemotron-3-nano:30b",
      "label": "nemotron-3-nano:30b",
      "cost_input_usd_per_million": 0.06,
      "cost_output_usd_per_million": 0.24,
      "context_window": 1048576,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "nemotron-3-super",
      "label": "nemotron-3-super",
      "cost_input_usd_per_million": 0.015,
      "cost_output_usd_per_million": 0.6,
      "context_window": 262144,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "nemotron-3-ultra",
      "label": "nemotron-3-ultra",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 3.0,
      "context_window": 262144,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen3.5:397b",
      "label": "qwen3.5:397b",
      "cost_input_usd_per_million": 0.6,
      "cost_output_usd_per_million": 3.6,
      "context_window": 262144,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    }
  ],
  "openai": [
    {
      "id": "chatgpt-image-latest",
      "label": "chatgpt-image-latest",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": null,
      "max_output_tokens": null,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-3.5-turbo",
      "label": "GPT-3.5-turbo",
      "cost_input_usd_per_million": 0.5,
      "cost_output_usd_per_million": 1.5,
      "context_window": 16385,
      "max_output_tokens": 4096,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-4",
      "label": "GPT-4",
      "cost_input_usd_per_million": 30.0,
      "cost_output_usd_per_million": 60.0,
      "context_window": 8192,
      "max_output_tokens": 8192,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "gpt-4-turbo",
      "label": "GPT-4 Turbo",
      "cost_input_usd_per_million": 10.0,
      "cost_output_usd_per_million": 30.0,
      "context_window": 128000,
      "max_output_tokens": 4096,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "gpt-4.1",
      "label": "GPT-4.1",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 8.0,
      "context_window": 1047576,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-4.1-mini",
      "label": "GPT-4.1 mini",
      "cost_input_usd_per_million": 0.4,
      "cost_output_usd_per_million": 1.6,
      "context_window": 1047576,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-4.1-nano",
      "label": "GPT-4.1 nano",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.4,
      "context_window": 1047576,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-4o",
      "label": "GPT-4o",
      "cost_input_usd_per_million": 2.5,
      "cost_output_usd_per_million": 10.0,
      "context_window": 128000,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-4o-2024-05-13",
      "label": "GPT-4o (2024-05-13)",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 15.0,
      "context_window": 128000,
      "max_output_tokens": 4096,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "gpt-4o-2024-08-06",
      "label": "GPT-4o (2024-08-06)",
      "cost_input_usd_per_million": 2.5,
      "cost_output_usd_per_million": 10.0,
      "context_window": 128000,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-4o-2024-11-20",
      "label": "GPT-4o (2024-11-20)",
      "cost_input_usd_per_million": 2.5,
      "cost_output_usd_per_million": 10.0,
      "context_window": 128000,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-4o-mini",
      "label": "GPT-4o mini",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.6,
      "context_window": 128000,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-5",
      "label": "GPT-5",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 10.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-5-mini",
      "label": "GPT-5 Mini",
      "cost_input_usd_per_million": 0.25,
      "cost_output_usd_per_million": 2.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-5-nano",
      "label": "GPT-5 Nano",
      "cost_input_usd_per_million": 0.05,
      "cost_output_usd_per_million": 0.4,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-5-pro",
      "label": "GPT-5 Pro",
      "cost_input_usd_per_million": 15.0,
      "cost_output_usd_per_million": 120.0,
      "context_window": 400000,
      "max_output_tokens": 272000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "gpt-5.1",
      "label": "GPT-5.1",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 10.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-5.2",
      "label": "GPT-5.2",
      "cost_input_usd_per_million": 1.75,
      "cost_output_usd_per_million": 14.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-5.2-chat-latest",
      "label": "GPT-5.2 Chat",
      "cost_input_usd_per_million": 1.75,
      "cost_output_usd_per_million": 14.0,
      "context_window": 128000,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-5.2-pro",
      "label": "GPT-5.2 Pro",
      "cost_input_usd_per_million": 21.0,
      "cost_output_usd_per_million": 168.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "gpt-5.3-chat-latest",
      "label": "GPT-5.3 Chat (latest)",
      "cost_input_usd_per_million": 1.75,
      "cost_output_usd_per_million": 14.0,
      "context_window": 128000,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-5.3-codex",
      "label": "GPT-5.3 Codex",
      "cost_input_usd_per_million": 1.75,
      "cost_output_usd_per_million": 14.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-5.3-codex-spark",
      "label": "GPT-5.3 Codex Spark",
      "cost_input_usd_per_million": 1.75,
      "cost_output_usd_per_million": 14.0,
      "context_window": 128000,
      "max_output_tokens": 32000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-5.4",
      "label": "GPT-5.4",
      "cost_input_usd_per_million": 2.5,
      "cost_output_usd_per_million": 15.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-5.4-mini",
      "label": "GPT-5.4 mini",
      "cost_input_usd_per_million": 0.75,
      "cost_output_usd_per_million": 4.5,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-5.4-nano",
      "label": "GPT-5.4 nano",
      "cost_input_usd_per_million": 0.2,
      "cost_output_usd_per_million": 1.25,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-5.4-pro",
      "label": "GPT-5.4 Pro",
      "cost_input_usd_per_million": 30.0,
      "cost_output_usd_per_million": 180.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "gpt-5.5",
      "label": "GPT-5.5",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 30.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "gpt-5.5-pro",
      "label": "GPT-5.5 Pro",
      "cost_input_usd_per_million": 30.0,
      "cost_output_usd_per_million": 180.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "gpt-5.6",
      "label": "GPT-5.6",
      "cost_input_usd_per_million": 4.0,
      "cost_output_usd_per_million": 20.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "gpt-5.6-luna",
      "label": "GPT-5.6 Luna",
      "cost_input_usd_per_million": 0.2,
      "cost_output_usd_per_million": 1.2,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-5.6-sol",
      "label": "GPT-5.6 Sol",
      "cost_input_usd_per_million": 4.0,
      "cost_output_usd_per_million": 20.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "gpt-5.6-terra",
      "label": "GPT-5.6 Terra",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 12.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-6-astra",
      "label": "GPT-6 Astra",
      "cost_input_usd_per_million": 10.0,
      "cost_output_usd_per_million": 50.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "gpt-6-luna",
      "label": "GPT-6 Luna",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.5,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-6-sol",
      "label": "GPT-6 Sol",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 10.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-6.1-sol",
      "label": "GPT-6.1 Sol",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 10.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-daybreak-blue-latest",
      "label": "Daybreak Blue",
      "cost_input_usd_per_million": 4.0,
      "cost_output_usd_per_million": 20.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "gpt-daybreak-red-latest",
      "label": "Daybreak Red",
      "cost_input_usd_per_million": 12.5,
      "cost_output_usd_per_million": 75.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "gpt-image-1",
      "label": "gpt-image-1",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": null,
      "max_output_tokens": null,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "image"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-image-1-mini",
      "label": "gpt-image-1-mini",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": null,
      "max_output_tokens": null,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-image-1.5",
      "label": "gpt-image-1.5",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": null,
      "max_output_tokens": null,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "gpt-image-2",
      "label": "gpt-image-2",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 30.0,
      "context_window": null,
      "max_output_tokens": null,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "image"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "gpt-realtime-2.1",
      "label": "GPT-Realtime-2.1",
      "cost_input_usd_per_million": 4.0,
      "cost_output_usd_per_million": 24.0,
      "context_window": 128000,
      "max_output_tokens": 32000,
      "modalities_input": [
        "text",
        "audio",
        "image"
      ],
      "modalities_output": [
        "text",
        "audio"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "o1",
      "label": "o1",
      "cost_input_usd_per_million": 15.0,
      "cost_output_usd_per_million": 60.0,
      "context_window": 200000,
      "max_output_tokens": 100000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "o1-pro",
      "label": "o1-pro",
      "cost_input_usd_per_million": 150.0,
      "cost_output_usd_per_million": 600.0,
      "context_window": 200000,
      "max_output_tokens": 100000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "o3",
      "label": "o3",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 8.0,
      "context_window": 200000,
      "max_output_tokens": 100000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "o3-mini",
      "label": "o3-mini",
      "cost_input_usd_per_million": 1.1,
      "cost_output_usd_per_million": 4.4,
      "context_window": 200000,
      "max_output_tokens": 100000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "o3-pro",
      "label": "o3-pro",
      "cost_input_usd_per_million": 20.0,
      "cost_output_usd_per_million": 80.0,
      "context_window": 200000,
      "max_output_tokens": 100000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "o4-mini",
      "label": "o4-mini",
      "cost_input_usd_per_million": 1.1,
      "cost_output_usd_per_million": 4.4,
      "context_window": 200000,
      "max_output_tokens": 100000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "text-embedding-3-large",
      "label": "text-embedding-3-large",
      "cost_input_usd_per_million": 0.13,
      "cost_output_usd_per_million": 0.0,
      "context_window": 8191,
      "max_output_tokens": 3072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "text-embedding-3-small",
      "label": "text-embedding-3-small",
      "cost_input_usd_per_million": 0.02,
      "cost_output_usd_per_million": 0.0,
      "context_window": 8191,
      "max_output_tokens": 1536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "text-embedding-ada-002",
      "label": "text-embedding-ada-002",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.0,
      "context_window": 8192,
      "max_output_tokens": 1536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    }
  ],
  "openrouter": [
    {
      "id": "aion-labs/aion-2.0",
      "label": "Aion-2.0",
      "cost_input_usd_per_million": 0.8,
      "cost_output_usd_per_million": 1.6,
      "context_window": 131072,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "aion-labs/aion-3.0",
      "label": "Aion-3.0",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 131072,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "aion-labs/aion-3.0-mini",
      "label": "Aion-3.0-Mini",
      "cost_input_usd_per_million": 0.7,
      "cost_output_usd_per_million": 1.4,
      "context_window": 131072,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "aion-labs/aion-3.5",
      "label": "Aion 3.5",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "aion-labs/aion-3.5-mini",
      "label": "Aion 3.5 Mini",
      "cost_input_usd_per_million": 0.7,
      "cost_output_usd_per_million": 1.4,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "aion-labs/aion-rp-llama-3.1-8b",
      "label": "Aion-RP 1.0 (8B)",
      "cost_input_usd_per_million": 0.8,
      "cost_output_usd_per_million": 1.6,
      "context_window": 32768,
      "max_output_tokens": 29491,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "amazon/nova-2-lite-v1",
      "label": "Nova 2 Lite",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 2.5,
      "context_window": 1000000,
      "max_output_tokens": 65535,
      "modalities_input": [
        "text",
        "image",
        "video",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "amazon/nova-lite-v1",
      "label": "Nova Lite 1.0",
      "cost_input_usd_per_million": 0.06,
      "cost_output_usd_per_million": 0.24,
      "context_window": 300000,
      "max_output_tokens": 5120,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "amazon/nova-micro-v1",
      "label": "Nova Micro 1.0",
      "cost_input_usd_per_million": 0.035,
      "cost_output_usd_per_million": 0.14,
      "context_window": 128000,
      "max_output_tokens": 5120,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "amazon/nova-premier-v1",
      "label": "Nova Premier 1.0",
      "cost_input_usd_per_million": 2.5,
      "cost_output_usd_per_million": 12.5,
      "context_window": 1000000,
      "max_output_tokens": 32000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "amazon/nova-pro-v1",
      "label": "Nova Pro 1.0",
      "cost_input_usd_per_million": 0.8,
      "cost_output_usd_per_million": 3.2,
      "context_window": 300000,
      "max_output_tokens": 5120,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "anthracite-org/magnum-v4-72b",
      "label": "Magnum v4 72B",
      "cost_input_usd_per_million": 2.5,
      "cost_output_usd_per_million": 5.0,
      "context_window": 32768,
      "max_output_tokens": 4096,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "anthropic/claude-fable-5",
      "label": "Claude Fable 5",
      "cost_input_usd_per_million": 10.0,
      "cost_output_usd_per_million": 50.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "anthropic/claude-fable-5.1",
      "label": "Claude Fable 5.1",
      "cost_input_usd_per_million": 10.0,
      "cost_output_usd_per_million": 50.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "anthropic/claude-haiku-4.5",
      "label": "Claude Haiku 4.5 (latest)",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 5.0,
      "context_window": 200000,
      "max_output_tokens": 64000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "anthropic/claude-opus-4.1",
      "label": "Claude Opus 4.1 (latest)",
      "cost_input_usd_per_million": 15.0,
      "cost_output_usd_per_million": 75.0,
      "context_window": 200000,
      "max_output_tokens": 32000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "anthropic/claude-opus-4.5",
      "label": "Claude Opus 4.5 (latest)",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 25.0,
      "context_window": 200000,
      "max_output_tokens": 64000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "anthropic/claude-opus-4.6",
      "label": "Claude Opus 4.6",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 25.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "anthropic/claude-opus-4.7",
      "label": "Claude Opus 4.7",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 25.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "anthropic/claude-opus-4.8",
      "label": "Claude Opus 4.8",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 25.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "anthropic/claude-opus-5",
      "label": "Claude Opus 5",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 25.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "anthropic/claude-opus-5.5",
      "label": "Claude Opus 5.5",
      "cost_input_usd_per_million": 4.0,
      "cost_output_usd_per_million": 20.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "anthropic/claude-sonnet-4",
      "label": "Claude Sonnet 4",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 15.0,
      "context_window": 200000,
      "max_output_tokens": 64000,
      "modalities_input": [
        "image",
        "text",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "anthropic/claude-sonnet-4.5",
      "label": "Claude Sonnet 4.5 (latest)",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 15.0,
      "context_window": 1000000,
      "max_output_tokens": 64000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "anthropic/claude-sonnet-4.6",
      "label": "Claude Sonnet 4.6",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 15.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "anthropic/claude-sonnet-5",
      "label": "Claude Sonnet 5",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 10.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "anthropic/claude-sonnet-5.5",
      "label": "Claude Sonnet 5.5",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 10.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "apodex/apodex-1.1-mini:free",
      "label": "Apodex 1.1 Mini (free)",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": "free"
    },
    {
      "id": "arcee-ai/trinity-large-thinking",
      "label": "Trinity Large Thinking",
      "cost_input_usd_per_million": 0.25,
      "cost_output_usd_per_million": 0.8,
      "context_window": 262144,
      "max_output_tokens": 80000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "baidu/ernie-4.5-vl-424b-a47b",
      "label": "ERNIE 4.5 VL 424B A47B ",
      "cost_input_usd_per_million": 0.42,
      "cost_output_usd_per_million": 1.25,
      "context_window": 123000,
      "max_output_tokens": 16000,
      "modalities_input": [
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "bytedance-seed/seed-1.6",
      "label": "Seed 1.6",
      "cost_input_usd_per_million": 0.25,
      "cost_output_usd_per_million": 2.0,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "image",
        "text",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "bytedance-seed/seed-1.6-flash",
      "label": "Seed 1.6 Flash",
      "cost_input_usd_per_million": 0.075,
      "cost_output_usd_per_million": 0.3,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "image",
        "text",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "bytedance-seed/seed-2-1-turbo",
      "label": "Seed 2.1 Turbo",
      "cost_input_usd_per_million": 0.5,
      "cost_output_usd_per_million": 2.5,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "bytedance-seed/seed-2.0-code",
      "label": "Seed 2.0 Code",
      "cost_input_usd_per_million": 0.5,
      "cost_output_usd_per_million": 3.0,
      "context_window": 262144,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "bytedance-seed/seed-2.0-lite",
      "label": "Seed 2.0 Lite",
      "cost_input_usd_per_million": 0.25,
      "cost_output_usd_per_million": 2.0,
      "context_window": 262144,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "bytedance-seed/seed-2.0-mini",
      "label": "Seed 2.0 Mini",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.4,
      "context_window": 262144,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "bytedance/ui-tars-1.5-7b",
      "label": "UI-TARS 7B ",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.2,
      "context_window": 128000,
      "max_output_tokens": 2048,
      "modalities_input": [
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "cognitivecomputations/dolphin-mistral-24b-venice-edition",
      "label": "Uncensored",
      "cost_input_usd_per_million": 0.2,
      "cost_output_usd_per_million": 0.9,
      "context_window": 128000,
      "max_output_tokens": 8192,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "cohere/command-a",
      "label": "Command A",
      "cost_input_usd_per_million": 2.5,
      "cost_output_usd_per_million": 10.0,
      "context_window": 256000,
      "max_output_tokens": 8192,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "cohere/command-a-plus",
      "label": "Command A+",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.5,
      "context_window": 192000,
      "max_output_tokens": 64000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "cohere/command-r-08-2024",
      "label": "Command R",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.6,
      "context_window": 128000,
      "max_output_tokens": 4000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "cohere/command-r-plus-08-2024",
      "label": "Command R+",
      "cost_input_usd_per_million": 2.5,
      "cost_output_usd_per_million": 10.0,
      "context_window": 128000,
      "max_output_tokens": 4000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "cohere/command-r7b-12-2024",
      "label": "Command R7B",
      "cost_input_usd_per_million": 0.0375,
      "cost_output_usd_per_million": 0.15,
      "context_window": 128000,
      "max_output_tokens": 4000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "cohere/north-mini-code:free",
      "label": "North Mini Code (free)",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 256000,
      "max_output_tokens": 64000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "free"
    },
    {
      "id": "deepseek/deepseek-chat",
      "label": "DeepSeek Chat",
      "cost_input_usd_per_million": 0.2574,
      "cost_output_usd_per_million": 1.0287,
      "context_window": 163840,
      "max_output_tokens": 16000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek/deepseek-chat-v3-0324",
      "label": "DeepSeek V3 0324",
      "cost_input_usd_per_million": 0.29,
      "cost_output_usd_per_million": 1.14,
      "context_window": 163840,
      "max_output_tokens": 115200,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek/deepseek-chat-v3.1",
      "label": "DeepSeek V3.1",
      "cost_input_usd_per_million": 0.25,
      "cost_output_usd_per_million": 0.95,
      "context_window": 163840,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek/deepseek-r1",
      "label": "DeepSeek-R1",
      "cost_input_usd_per_million": 0.7,
      "cost_output_usd_per_million": 2.5,
      "context_window": 64000,
      "max_output_tokens": 16000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek/deepseek-r1-0528",
      "label": "R1 0528",
      "cost_input_usd_per_million": 0.5,
      "cost_output_usd_per_million": 2.15,
      "context_window": 163840,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek/deepseek-v3.1-terminus",
      "label": "DeepSeek V3.1 Terminus",
      "cost_input_usd_per_million": 0.27,
      "cost_output_usd_per_million": 1.0,
      "context_window": 163840,
      "max_output_tokens": 147456,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek/deepseek-v3.2",
      "label": "DeepSeek V3.2",
      "cost_input_usd_per_million": 0.28,
      "cost_output_usd_per_million": 0.42,
      "context_window": 163840,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek/deepseek-v3.2-exp",
      "label": "DeepSeek V3.2 Exp",
      "cost_input_usd_per_million": 0.27,
      "cost_output_usd_per_million": 0.41,
      "context_window": 163840,
      "max_output_tokens": 147456,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek/deepseek-v4-flash",
      "label": "DeepSeek V4 Flash",
      "cost_input_usd_per_million": 0.028,
      "cost_output_usd_per_million": 0.056,
      "context_window": 1048576,
      "max_output_tokens": 384000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek/deepseek-v4-flash-0731",
      "label": "DeepSeek V4 Flash 0731",
      "cost_input_usd_per_million": 0.0115,
      "cost_output_usd_per_million": 1.28,
      "context_window": 1048576,
      "max_output_tokens": 943718,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek/deepseek-v4-flash-vision-exp",
      "label": "DeepSeek V4 Flash Vision Exp",
      "cost_input_usd_per_million": 0.2156,
      "cost_output_usd_per_million": 0.6468,
      "context_window": 1048576,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek/deepseek-v4-pro",
      "label": "DeepSeek V4 Pro",
      "cost_input_usd_per_million": 0.2088,
      "cost_output_usd_per_million": 0.4176,
      "context_window": 1048576,
      "max_output_tokens": 384000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek/deepseek-v4-pro-0813",
      "label": "DeepSeek V4 Pro 0813",
      "cost_input_usd_per_million": 0.66,
      "cost_output_usd_per_million": 1.98,
      "context_window": 1048576,
      "max_output_tokens": 393216,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek/deepseek-v4.1-flash",
      "label": "DeepSeek V4.1 Flash",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.2,
      "context_window": 1048576,
      "max_output_tokens": 943718,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "dots-studio/dots-3-note-preview:free",
      "label": "Dots3-Note Preview (free)",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 512000,
      "max_output_tokens": 460800,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "free"
    },
    {
      "id": "fireworks/ember-1",
      "label": "Ember-1",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 15.0,
      "context_window": 1048576,
      "max_output_tokens": 943718,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "google/gemini-2.5-flash",
      "label": "Gemini 2.5 Flash",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 2.5,
      "context_window": 1048576,
      "max_output_tokens": 65535,
      "modalities_input": [
        "text",
        "image",
        "audio",
        "video",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-2.5-flash-image",
      "label": "Nano Banana",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 2.5,
      "context_window": 32768,
      "max_output_tokens": 8192,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-2.5-flash-lite",
      "label": "Gemini 2.5 Flash-Lite",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.4,
      "context_window": 1048576,
      "max_output_tokens": 65535,
      "modalities_input": [
        "text",
        "image",
        "audio",
        "video",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-2.5-pro",
      "label": "Gemini 2.5 Pro",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 10.0,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "audio",
        "video",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-2.5-pro-preview",
      "label": "Gemini 2.5 Pro Preview 06-05",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 10.0,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "pdf",
        "image",
        "text",
        "audio"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-3-flash-preview",
      "label": "Gemini 3 Flash Preview",
      "cost_input_usd_per_million": 0.5,
      "cost_output_usd_per_million": 3.0,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-3-pro-image",
      "label": "Nano Banana Pro",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 12.0,
      "context_window": 131072,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-3-pro-image-preview",
      "label": "Nano Banana Pro Preview",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 12.0,
      "context_window": 65536,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-3.1-flash-image",
      "label": "Nano Banana 2",
      "cost_input_usd_per_million": 0.5,
      "cost_output_usd_per_million": 3.0,
      "context_window": 131072,
      "max_output_tokens": 32768,
      "modalities_input": [
        "image",
        "text"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-3.1-flash-image-preview",
      "label": "Nano Banana 2 Preview",
      "cost_input_usd_per_million": 0.5,
      "cost_output_usd_per_million": 3.0,
      "context_window": 65536,
      "max_output_tokens": 58982,
      "modalities_input": [
        "image",
        "text"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-3.1-flash-lite",
      "label": "Gemini 3.1 Flash Lite",
      "cost_input_usd_per_million": 0.25,
      "cost_output_usd_per_million": 1.5,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-3.1-flash-lite-image",
      "label": "Nano Banana 2 Lite",
      "cost_input_usd_per_million": 0.25,
      "cost_output_usd_per_million": 1.5,
      "context_window": 65536,
      "max_output_tokens": 58982,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-3.1-flash-lite-preview",
      "label": "Gemini 3.1 Flash Lite Preview",
      "cost_input_usd_per_million": 0.25,
      "cost_output_usd_per_million": 1.5,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-3.1-pro-preview",
      "label": "Gemini 3.1 Pro Preview",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 12.0,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-3.1-pro-preview-customtools",
      "label": "Gemini 3.1 Pro Preview Custom Tools",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 12.0,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-3.5-flash",
      "label": "Gemini 3.5 Flash",
      "cost_input_usd_per_million": 1.5,
      "cost_output_usd_per_million": 9.0,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-3.5-flash-lite",
      "label": "Gemini 3.5 Flash Lite",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 2.5,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-3.6-flash",
      "label": "Gemini 3.6 Flash",
      "cost_input_usd_per_million": 0.75,
      "cost_output_usd_per_million": 3.75,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-3.7-flash",
      "label": "Gemini 3.7 Flash",
      "cost_input_usd_per_million": 0.75,
      "cost_output_usd_per_million": 3.75,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemini-3.8-flash",
      "label": "Gemini 3.8 Flash",
      "cost_input_usd_per_million": 0.75,
      "cost_output_usd_per_million": 3.75,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "google/gemma-2-27b-it",
      "label": "Gemma 2 27B",
      "cost_input_usd_per_million": 0.65,
      "cost_output_usd_per_million": 0.65,
      "context_window": 8192,
      "max_output_tokens": 2048,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "google/gemma-3-12b-it",
      "label": "Gemma 3 12B IT",
      "cost_input_usd_per_million": 0.05,
      "cost_output_usd_per_million": 0.15,
      "context_window": 131072,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "google/gemma-3-27b-it",
      "label": "Gemma 3 27B IT",
      "cost_input_usd_per_million": 0.08,
      "cost_output_usd_per_million": 0.45,
      "context_window": 131072,
      "max_output_tokens": 117964,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "google/gemma-3-4b-it",
      "label": "Gemma 3 4B IT",
      "cost_input_usd_per_million": 0.05,
      "cost_output_usd_per_million": 0.1,
      "context_window": 131072,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "google/gemma-4-26b-a4b-it",
      "label": "Gemma 4 26B A4B IT",
      "cost_input_usd_per_million": 0.0675,
      "cost_output_usd_per_million": 0.225,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "image",
        "text",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "google/gemma-4-26b-a4b-it:free",
      "label": "Gemma 4 26B A4B  (free)",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "image",
        "text",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "free"
    },
    {
      "id": "google/gemma-4-31b-it",
      "label": "Gemma 4 31B IT",
      "cost_input_usd_per_million": 0.09,
      "cost_output_usd_per_million": 0.34,
      "context_window": 262144,
      "max_output_tokens": 16384,
      "modalities_input": [
        "image",
        "text",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "google/gemma-4-31b-it:free",
      "label": "Gemma 4 31B (free)",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "image",
        "text",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "free"
    },
    {
      "id": "google/lyria-3-clip-preview",
      "label": "Lyria 3 Clip Preview",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text",
        "audio"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "free"
    },
    {
      "id": "google/lyria-3-pro-preview",
      "label": "Lyria 3 Pro Preview",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text",
        "audio"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "free"
    },
    {
      "id": "gryphe/mythomax-l2-13b",
      "label": "MythoMax 13B",
      "cost_input_usd_per_million": 0.08,
      "cost_output_usd_per_million": 0.11,
      "context_window": 8192,
      "max_output_tokens": 3686,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "ibm-granite/granite-4.0-h-micro",
      "label": "Granite 4.0 Micro",
      "cost_input_usd_per_million": 0.017,
      "cost_output_usd_per_million": 0.112,
      "context_window": 131000,
      "max_output_tokens": 117900,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "ibm-granite/granite-4.2-8b",
      "label": "Granite 4.2 8B",
      "cost_input_usd_per_million": 0.06,
      "cost_output_usd_per_million": 0.25,
      "context_window": 131072,
      "max_output_tokens": 117964,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "inception/mercury-2",
      "label": "Mercury 2",
      "cost_input_usd_per_million": 0.25,
      "cost_output_usd_per_million": 0.75,
      "context_window": 128000,
      "max_output_tokens": 50000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "inception/mercury-2.5",
      "label": "Mercury 2.5",
      "cost_input_usd_per_million": 0.04,
      "cost_output_usd_per_million": 0.15,
      "context_window": 260000,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "inclusionai/ling-3.0-flash",
      "label": "Ling 3.0 Flash",
      "cost_input_usd_per_million": 0.021,
      "cost_output_usd_per_million": 0.063,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "inclusionai/ling-3.0-flash-fin",
      "label": "Ling 3.0 Flash Fin",
      "cost_input_usd_per_million": 0.042,
      "cost_output_usd_per_million": 0.1232,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "inclusionai/ling-3.0-flash-sante:free",
      "label": "Ling 3.0 Flash Sante (free)",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": "free"
    },
    {
      "id": "inclusionai/ling-3.0-flash-vl",
      "label": "Ling 3.0 Flash VL",
      "cost_input_usd_per_million": 0.021,
      "cost_output_usd_per_million": 0.0616,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "inclusionai/ling-3.1-flash",
      "label": "Ling 3.1 Flash",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": "free"
    },
    {
      "id": "inference-net/schematron-v2-small",
      "label": "Schematron V2 Small",
      "cost_input_usd_per_million": 0.05,
      "cost_output_usd_per_million": 0.23,
      "context_window": 128000,
      "max_output_tokens": 4096,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "inference-net/schematron-v2-turbo",
      "label": "Schematron V2 Turbo",
      "cost_input_usd_per_million": 0.03,
      "cost_output_usd_per_million": 0.15,
      "context_window": 128000,
      "max_output_tokens": 8192,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "kwaipilot/kat-coder-pro-v2.5",
      "label": "KAT-Coder-Pro V2.5",
      "cost_input_usd_per_million": 0.74,
      "cost_output_usd_per_million": 2.96,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "liquid/lfm-2.5-2.6b:free",
      "label": "LFM2.5-2.6B (free)",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 65536,
      "max_output_tokens": 8192,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "free"
    },
    {
      "id": "mancer/weaver",
      "label": "Weaver (alpha)",
      "cost_input_usd_per_million": 0.4,
      "cost_output_usd_per_million": 0.75,
      "context_window": 8000,
      "max_output_tokens": 6000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "meituan/longcat-2.0",
      "label": "LongCat 2.0",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.2,
      "context_window": 1048756,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "meta-llama/llama-3.1-70b-instruct",
      "label": "Llama-3.1-70B-Instruct",
      "cost_input_usd_per_million": 0.4,
      "cost_output_usd_per_million": 0.4,
      "context_window": 131072,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "meta-llama/llama-3.1-8b-instruct",
      "label": "Llama-3.1-8B-Instruct",
      "cost_input_usd_per_million": 0.05,
      "cost_output_usd_per_million": 0.08,
      "context_window": 131072,
      "max_output_tokens": 117964,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "meta-llama/llama-3.2-1b-instruct",
      "label": "Llama 3.2 1B Instruct",
      "cost_input_usd_per_million": 0.027,
      "cost_output_usd_per_million": 0.201,
      "context_window": 60000,
      "max_output_tokens": 54000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "meta-llama/llama-3.2-3b-instruct",
      "label": "Llama 3.2 3B Instruct",
      "cost_input_usd_per_million": 0.05,
      "cost_output_usd_per_million": 0.33,
      "context_window": 131072,
      "max_output_tokens": 117964,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "meta-llama/llama-3.3-70b-instruct",
      "label": "Llama-3.3-70B-Instruct",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.32,
      "context_window": 131072,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "meta-llama/llama-4-maverick",
      "label": "Llama 4 Maverick",
      "cost_input_usd_per_million": 0.1875,
      "cost_output_usd_per_million": 0.6525,
      "context_window": 1048576,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "meta-llama/llama-4-scout",
      "label": "Llama 4 Scout",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.3,
      "context_window": 1310720,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "meta-llama/llama-guard-4-12b",
      "label": "Llama Guard 4 12B",
      "cost_input_usd_per_million": 0.18,
      "cost_output_usd_per_million": 0.18,
      "context_window": 163840,
      "max_output_tokens": 16384,
      "modalities_input": [
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "meta/muse-glimmer-30b",
      "label": "Muse Glimmer 30B",
      "cost_input_usd_per_million": 0.35,
      "cost_output_usd_per_million": 1.5,
      "context_window": 131072,
      "max_output_tokens": 117964,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "meta/muse-spark-1.1",
      "label": "Muse Spark 1.1",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 4.25,
      "context_window": 1048576,
      "max_output_tokens": 943718,
      "modalities_input": [
        "text",
        "image",
        "pdf",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "meta/muse-spark-1.2",
      "label": "Muse Spark 1.2",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 4.25,
      "context_window": 1048576,
      "max_output_tokens": 943718,
      "modalities_input": [
        "text",
        "image",
        "video",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "meta/muse-spark-1.2-contributor",
      "label": "Muse Spark 1.2 Contributor",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.2,
      "context_window": 1048576,
      "max_output_tokens": 943718,
      "modalities_input": [
        "text",
        "image",
        "video",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "meta/muse-spark-1.3",
      "label": "Muse Spark 1.3",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 4.25,
      "context_window": 1048576,
      "max_output_tokens": 943718,
      "modalities_input": [
        "text",
        "image",
        "video",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "meta/muse-spark-1.3-contributor",
      "label": "Muse Spark 1.3 Contributor",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.2,
      "context_window": 1048576,
      "max_output_tokens": 943718,
      "modalities_input": [
        "text",
        "image",
        "video",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "microsoft/phi-4",
      "label": "Phi 4",
      "cost_input_usd_per_million": 0.07,
      "cost_output_usd_per_million": 0.14,
      "context_window": 16384,
      "max_output_tokens": 14745,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "microsoft/wizardlm-2-8x22b",
      "label": "WizardLM-2 8x22B",
      "cost_input_usd_per_million": 0.62,
      "cost_output_usd_per_million": 0.62,
      "context_window": 65535,
      "max_output_tokens": 8000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "minimax/minimax-01",
      "label": "MiniMax-01",
      "cost_input_usd_per_million": 0.2,
      "cost_output_usd_per_million": 1.1,
      "context_window": 1000192,
      "max_output_tokens": 40000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "minimax/minimax-m1",
      "label": "MiniMax M1",
      "cost_input_usd_per_million": 0.55,
      "cost_output_usd_per_million": 2.2,
      "context_window": 1000000,
      "max_output_tokens": 40000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "minimax/minimax-m2",
      "label": "MiniMax-M2",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.2,
      "context_window": 204800,
      "max_output_tokens": 176947,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "minimax/minimax-m2-her",
      "label": "MiniMax-M2 Her",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.2,
      "context_window": 65536,
      "max_output_tokens": 2048,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "minimax/minimax-m2.1",
      "label": "MiniMax-M2.1",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.2,
      "context_window": 204800,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "minimax/minimax-m2.5",
      "label": "MiniMax-M2.5",
      "cost_input_usd_per_million": 0.27,
      "cost_output_usd_per_million": 1.08,
      "context_window": 204800,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "minimax/minimax-m2.7",
      "label": "MiniMax-M2.7",
      "cost_input_usd_per_million": 0.21,
      "cost_output_usd_per_million": 0.84,
      "context_window": 204800,
      "max_output_tokens": 176947,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "minimax/minimax-m3",
      "label": "MiniMax-M3",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.2,
      "context_window": 1048576,
      "max_output_tokens": 512000,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "mistralai/codestral-2508",
      "label": "Codestral 2508",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 0.9,
      "context_window": 256000,
      "max_output_tokens": 204800,
      "modalities_input": [
        "text",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "mistralai/devstral-2512",
      "label": "Devstral 2",
      "cost_input_usd_per_million": 0.4,
      "cost_output_usd_per_million": 2.0,
      "context_window": 262144,
      "max_output_tokens": 209715,
      "modalities_input": [
        "text",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "mistralai/ministral-14b-2512",
      "label": "Ministral 3 14B 2512",
      "cost_input_usd_per_million": 0.2,
      "cost_output_usd_per_million": 0.2,
      "context_window": 262144,
      "max_output_tokens": 209715,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "mistralai/ministral-3b-2512",
      "label": "Ministral 3 3B 2512",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.1,
      "context_window": 131072,
      "max_output_tokens": 104857,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "mistralai/ministral-8b-2512",
      "label": "Ministral 3 8B 2512",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.15,
      "context_window": 262144,
      "max_output_tokens": 209715,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "mistralai/mistral-large",
      "label": "Mistral Large",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 128000,
      "max_output_tokens": 102400,
      "modalities_input": [
        "text",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "mistralai/mistral-large-2407",
      "label": "Mistral Large 2407",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 131072,
      "max_output_tokens": 104857,
      "modalities_input": [
        "text",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "mistralai/mistral-large-2512",
      "label": "Mistral Large 3",
      "cost_input_usd_per_million": 0.5,
      "cost_output_usd_per_million": 1.5,
      "context_window": 262144,
      "max_output_tokens": 209715,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "mistralai/mistral-medium-3",
      "label": "Mistral Medium 3",
      "cost_input_usd_per_million": 0.4,
      "cost_output_usd_per_million": 2.0,
      "context_window": 131072,
      "max_output_tokens": 104857,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "mistralai/mistral-medium-3-5",
      "label": "Mistral Medium 3.5",
      "cost_input_usd_per_million": 1.5,
      "cost_output_usd_per_million": 7.5,
      "context_window": 262144,
      "max_output_tokens": 209715,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "mistralai/mistral-medium-3.1",
      "label": "Mistral Medium 3.1",
      "cost_input_usd_per_million": 0.4,
      "cost_output_usd_per_million": 2.0,
      "context_window": 131072,
      "max_output_tokens": 104857,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "mistralai/mistral-nemo",
      "label": "Mistral Nemo",
      "cost_input_usd_per_million": 0.019,
      "cost_output_usd_per_million": 0.03,
      "context_window": 131072,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "mistralai/mistral-saba",
      "label": "Saba",
      "cost_input_usd_per_million": 0.2,
      "cost_output_usd_per_million": 0.6,
      "context_window": 32768,
      "max_output_tokens": 26214,
      "modalities_input": [
        "text",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "mistralai/mistral-small-24b-instruct-2501",
      "label": "Mistral Small 3",
      "cost_input_usd_per_million": 0.05,
      "cost_output_usd_per_million": 0.08,
      "context_window": 32768,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "mistralai/mistral-small-2603",
      "label": "Mistral Small 4",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.6,
      "context_window": 262144,
      "max_output_tokens": 209715,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "mistralai/mistral-small-3.1-24b-instruct",
      "label": "Mistral Small 3.1 24B",
      "cost_input_usd_per_million": 0.351,
      "cost_output_usd_per_million": 0.555,
      "context_window": 128000,
      "max_output_tokens": 102400,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "mistralai/mistral-small-3.2-24b-instruct",
      "label": "Mistral Small 3.2 24B",
      "cost_input_usd_per_million": 0.09375,
      "cost_output_usd_per_million": 0.25,
      "context_window": 256000,
      "max_output_tokens": 16384,
      "modalities_input": [
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "mistralai/mixtral-8x22b-instruct",
      "label": "Mixtral 8x22B Instruct",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 65536,
      "max_output_tokens": 52428,
      "modalities_input": [
        "text",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "mistralai/voxtral-small-24b-2507",
      "label": "Voxtral Small 24B 2507",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.3,
      "context_window": 32768,
      "max_output_tokens": 26214,
      "modalities_input": [
        "text",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "moonshotai/kimi-k2",
      "label": "Kimi K2 0711",
      "cost_input_usd_per_million": 0.57,
      "cost_output_usd_per_million": 2.3,
      "context_window": 131072,
      "max_output_tokens": 98304,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "moonshotai/kimi-k2-0905",
      "label": "Kimi K2 0905",
      "cost_input_usd_per_million": 0.6,
      "cost_output_usd_per_million": 2.5,
      "context_window": 262144,
      "max_output_tokens": 98304,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "moonshotai/kimi-k2-thinking",
      "label": "Kimi K2 Thinking",
      "cost_input_usd_per_million": 0.6,
      "cost_output_usd_per_million": 2.5,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "moonshotai/kimi-k2.5",
      "label": "Kimi K2.5",
      "cost_input_usd_per_million": 0.45,
      "cost_output_usd_per_million": 2.25,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "moonshotai/kimi-k2.6",
      "label": "Kimi K2.6",
      "cost_input_usd_per_million": 0.43415,
      "cost_output_usd_per_million": 1.828,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "moonshotai/kimi-k2.7-code",
      "label": "Kimi K2.7 Code",
      "cost_input_usd_per_million": 0.6712,
      "cost_output_usd_per_million": 3.35,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "moonshotai/kimi-k3",
      "label": "Kimi K3",
      "cost_input_usd_per_million": 2.7,
      "cost_output_usd_per_million": 13.5,
      "context_window": 1048576,
      "max_output_tokens": 943718,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "morph/morph-v3-fast",
      "label": "Morph V3 Fast",
      "cost_input_usd_per_million": 0.8,
      "cost_output_usd_per_million": 1.2,
      "context_window": 81920,
      "max_output_tokens": 38000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "morph/morph-v3-large",
      "label": "Morph V3 Large",
      "cost_input_usd_per_million": 0.9,
      "cost_output_usd_per_million": 1.9,
      "context_window": 262144,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "nex-agi/nex-n2.5-mini",
      "label": "Nex-N2.5-Mini",
      "cost_input_usd_per_million": 0.025,
      "cost_output_usd_per_million": 0.1,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "nex-agi/nex-n2.5-pro",
      "label": "Nex-N2.5-Pro",
      "cost_input_usd_per_million": 0.075,
      "cost_output_usd_per_million": 0.25,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "nousresearch/hermes-3-llama-3.1-405b",
      "label": "Hermes 3 405B Instruct",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 1.0,
      "context_window": 131072,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "nousresearch/hermes-3-llama-3.1-70b",
      "label": "Hermes 3 70B Instruct",
      "cost_input_usd_per_million": 0.7,
      "cost_output_usd_per_million": 0.7,
      "context_window": 131072,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "nousresearch/hermes-4-405b",
      "label": "Hermes 4 405B",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 3.0,
      "context_window": 131072,
      "max_output_tokens": 117964,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "nvidia/nemotron-3-nano-30b-a3b",
      "label": "Nemotron 3 Nano 30B A3B",
      "cost_input_usd_per_million": 0.05,
      "cost_output_usd_per_million": 0.2,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
      "label": "Nemotron 3 Nano Omni (free)",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 256000,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "free"
    },
    {
      "id": "nvidia/nemotron-3-super-120b-a12b",
      "label": "Nemotron 3 Super 120B A12B",
      "cost_input_usd_per_million": 0.08,
      "cost_output_usd_per_million": 0.45,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "nvidia/nemotron-3-super-120b-a12b:free",
      "label": "Nemotron 3 Super (free)",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "free"
    },
    {
      "id": "nvidia/nemotron-3-ultra-550b-a55b",
      "label": "Nemotron 3 Ultra 550B A55B",
      "cost_input_usd_per_million": 0.5,
      "cost_output_usd_per_million": 2.2,
      "context_window": 262144,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "nvidia/nemotron-3-ultra-550b-a55b:free",
      "label": "Nemotron 3 Ultra (free)",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 1000000,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "free"
    },
    {
      "id": "nvidia/nemotron-3.5-content-safety",
      "label": "Nemotron 3.5 Content Safety",
      "cost_input_usd_per_million": 0.2,
      "cost_output_usd_per_million": 0.2,
      "context_window": 131072,
      "max_output_tokens": 117964,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "nvidia/nemotron-3.5-content-safety:free",
      "label": "Nemotron 3.5 Content Safety (free)",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 128000,
      "max_output_tokens": 8192,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "free"
    },
    {
      "id": "nvidia/nemotron-3.5-lightning",
      "label": "Nemotron 3.5 Lightning 30B A3B",
      "cost_input_usd_per_million": 0.06,
      "cost_output_usd_per_million": 0.16,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "nvidia/nemotron-3.5-lightning:free",
      "label": "Nemotron 3.5 Lightning (free)",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 1000000,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "free"
    },
    {
      "id": "openai/gpt-3.5-turbo",
      "label": "GPT-3.5-turbo",
      "cost_input_usd_per_million": 0.5,
      "cost_output_usd_per_million": 1.5,
      "context_window": 16385,
      "max_output_tokens": 4096,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-3.5-turbo-0613",
      "label": "GPT-3.5 Turbo (older v0613)",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 2.0,
      "context_window": 4095,
      "max_output_tokens": 3685,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-3.5-turbo-16k",
      "label": "GPT-3.5 Turbo 16k",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 4.0,
      "context_window": 16385,
      "max_output_tokens": 4096,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/gpt-3.5-turbo-instruct",
      "label": "GPT-3.5 Turbo Instruct",
      "cost_input_usd_per_million": 1.5,
      "cost_output_usd_per_million": 2.0,
      "context_window": 4095,
      "max_output_tokens": 3685,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-4",
      "label": "GPT-4",
      "cost_input_usd_per_million": 30.0,
      "cost_output_usd_per_million": 60.0,
      "context_window": 8191,
      "max_output_tokens": 4096,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/gpt-4-turbo",
      "label": "GPT-4 Turbo",
      "cost_input_usd_per_million": 10.0,
      "cost_output_usd_per_million": 30.0,
      "context_window": 128000,
      "max_output_tokens": 4096,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/gpt-4.1",
      "label": "GPT-4.1",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 8.0,
      "context_window": 1047576,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-4.1-mini",
      "label": "GPT-4.1 mini",
      "cost_input_usd_per_million": 0.4,
      "cost_output_usd_per_million": 1.6,
      "context_window": 1047576,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-4.1-nano",
      "label": "GPT-4.1 nano",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.4,
      "context_window": 1047576,
      "max_output_tokens": 32768,
      "modalities_input": [
        "image",
        "text",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-4o",
      "label": "GPT-4o",
      "cost_input_usd_per_million": 2.5,
      "cost_output_usd_per_million": 10.0,
      "context_window": 128000,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-4o-2024-05-13",
      "label": "GPT-4o (2024-05-13)",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 15.0,
      "context_window": 128000,
      "max_output_tokens": 4096,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/gpt-4o-2024-08-06",
      "label": "GPT-4o (2024-08-06)",
      "cost_input_usd_per_million": 2.5,
      "cost_output_usd_per_million": 10.0,
      "context_window": 128000,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-4o-2024-11-20",
      "label": "GPT-4o (2024-11-20)",
      "cost_input_usd_per_million": 2.5,
      "cost_output_usd_per_million": 10.0,
      "context_window": 128000,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-4o-mini",
      "label": "GPT-4o mini",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.6,
      "context_window": 128000,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-4o-mini-2024-07-18",
      "label": "GPT-4o-mini (2024-07-18)",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.6,
      "context_window": 128000,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5",
      "label": "GPT-5",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 10.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5-image",
      "label": "GPT-5 Image",
      "cost_input_usd_per_million": 10.0,
      "cost_output_usd_per_million": 10.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "image",
        "text",
        "pdf"
      ],
      "modalities_output": [
        "image",
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/gpt-5-image-mini",
      "label": "GPT-5 Image Mini",
      "cost_input_usd_per_million": 2.5,
      "cost_output_usd_per_million": 2.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "pdf",
        "image",
        "text"
      ],
      "modalities_output": [
        "image",
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5-mini",
      "label": "GPT-5 Mini",
      "cost_input_usd_per_million": 0.25,
      "cost_output_usd_per_million": 2.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5-nano",
      "label": "GPT-5 Nano",
      "cost_input_usd_per_million": 0.05,
      "cost_output_usd_per_million": 0.4,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5-pro",
      "label": "GPT-5 Pro",
      "cost_input_usd_per_million": 15.0,
      "cost_output_usd_per_million": 120.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "image",
        "text",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/gpt-5.1",
      "label": "GPT-5.1",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 10.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "image",
        "text",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5.1-codex",
      "label": "GPT-5.1 Codex",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 10.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5.1-codex-max",
      "label": "GPT-5.1 Codex Max",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 10.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5.1-codex-mini",
      "label": "GPT-5.1 Codex mini",
      "cost_input_usd_per_million": 0.25,
      "cost_output_usd_per_million": 2.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5.2",
      "label": "GPT-5.2",
      "cost_input_usd_per_million": 1.75,
      "cost_output_usd_per_million": 14.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "pdf",
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5.2-chat",
      "label": "GPT-5.2 Chat",
      "cost_input_usd_per_million": 1.75,
      "cost_output_usd_per_million": 14.0,
      "context_window": 128000,
      "max_output_tokens": 32000,
      "modalities_input": [
        "pdf",
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5.2-codex",
      "label": "GPT-5.2 Codex",
      "cost_input_usd_per_million": 1.75,
      "cost_output_usd_per_million": 14.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5.2-pro",
      "label": "GPT-5.2 Pro",
      "cost_input_usd_per_million": 21.0,
      "cost_output_usd_per_million": 168.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "image",
        "text",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/gpt-5.3-codex",
      "label": "GPT-5.3 Codex",
      "cost_input_usd_per_million": 1.75,
      "cost_output_usd_per_million": 14.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5.4",
      "label": "GPT-5.4",
      "cost_input_usd_per_million": 2.5,
      "cost_output_usd_per_million": 15.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5.4-image-2",
      "label": "GPT-5.4 Image 2",
      "cost_input_usd_per_million": 8.0,
      "cost_output_usd_per_million": 15.0,
      "context_window": 272000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "image",
        "text",
        "pdf"
      ],
      "modalities_output": [
        "image",
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/gpt-5.4-mini",
      "label": "GPT-5.4 mini",
      "cost_input_usd_per_million": 0.75,
      "cost_output_usd_per_million": 4.5,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "pdf",
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5.4-nano",
      "label": "GPT-5.4 nano",
      "cost_input_usd_per_million": 0.2,
      "cost_output_usd_per_million": 1.25,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "pdf",
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5.4-pro",
      "label": "GPT-5.4 Pro",
      "cost_input_usd_per_million": 30.0,
      "cost_output_usd_per_million": 180.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/gpt-5.5",
      "label": "GPT-5.5",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 30.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/gpt-5.5-pro",
      "label": "GPT-5.5 Pro",
      "cost_input_usd_per_million": 30.0,
      "cost_output_usd_per_million": 180.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/gpt-5.6-luna",
      "label": "GPT-5.6 Luna",
      "cost_input_usd_per_million": 0.2,
      "cost_output_usd_per_million": 1.2,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5.6-luna-pro",
      "label": "GPT-5.6 Luna Pro",
      "cost_input_usd_per_million": 0.2,
      "cost_output_usd_per_million": 1.2,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5.6-sol",
      "label": "GPT-5.6 Sol",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 10.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5.6-sol-pro",
      "label": "GPT-5.6 Sol Pro",
      "cost_input_usd_per_million": 4.0,
      "cost_output_usd_per_million": 20.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/gpt-5.6-terra",
      "label": "GPT-5.6 Terra",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 12.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-5.6-terra-pro",
      "label": "GPT-5.6 Terra Pro",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 12.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-6-astra",
      "label": "GPT-6 Astra",
      "cost_input_usd_per_million": 10.0,
      "cost_output_usd_per_million": 50.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/gpt-6-astra-pro",
      "label": "GPT-6 Astra Pro",
      "cost_input_usd_per_million": 10.0,
      "cost_output_usd_per_million": 50.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "pdf",
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/gpt-6-luna",
      "label": "GPT-6 Luna",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.5,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-6-luna-pro",
      "label": "GPT-6 Luna Pro",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.5,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "pdf",
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-6-sol",
      "label": "GPT-6 Sol",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 10.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-6-sol-pro",
      "label": "GPT-6 Sol Pro",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 10.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "pdf",
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-6.1-sol",
      "label": "GPT-6.1 Sol",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 10.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-6.1-sol-pro",
      "label": "GPT-6.1 Sol Pro",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 10.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "pdf",
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-audio",
      "label": "GPT Audio",
      "cost_input_usd_per_million": 2.5,
      "cost_output_usd_per_million": 10.0,
      "context_window": 128000,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "audio"
      ],
      "modalities_output": [
        "text",
        "audio"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-audio-mini",
      "label": "GPT Audio Mini",
      "cost_input_usd_per_million": 0.6,
      "cost_output_usd_per_million": 2.4,
      "context_window": 128000,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "audio"
      ],
      "modalities_output": [
        "text",
        "audio"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/gpt-chat-latest",
      "label": "GPT Chat Latest",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 30.0,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/gpt-oss-120b",
      "label": "GPT OSS 120B",
      "cost_input_usd_per_million": 0.037,
      "cost_output_usd_per_million": 0.17,
      "context_window": 131072,
      "max_output_tokens": 117964,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "openai/gpt-oss-20b",
      "label": "GPT OSS 20B",
      "cost_input_usd_per_million": 0.018,
      "cost_output_usd_per_million": 0.09,
      "context_window": 131072,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "openai/gpt-oss-safeguard-20b",
      "label": "GPT OSS Safeguard 20B",
      "cost_input_usd_per_million": 0.075,
      "cost_output_usd_per_million": 0.3,
      "context_window": 131072,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "openai/o1",
      "label": "o1",
      "cost_input_usd_per_million": 15.0,
      "cost_output_usd_per_million": 60.0,
      "context_window": 200000,
      "max_output_tokens": 100000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/o1-pro",
      "label": "o1-pro",
      "cost_input_usd_per_million": 150.0,
      "cost_output_usd_per_million": 600.0,
      "context_window": 200000,
      "max_output_tokens": 100000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/o3",
      "label": "o3",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 8.0,
      "context_window": 200000,
      "max_output_tokens": 100000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/o3-mini",
      "label": "o3-mini",
      "cost_input_usd_per_million": 1.1,
      "cost_output_usd_per_million": 4.4,
      "context_window": 200000,
      "max_output_tokens": 100000,
      "modalities_input": [
        "text",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/o3-mini-high",
      "label": "o3 Mini High",
      "cost_input_usd_per_million": 1.1,
      "cost_output_usd_per_million": 4.4,
      "context_window": 200000,
      "max_output_tokens": 100000,
      "modalities_input": [
        "text",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/o3-pro",
      "label": "o3-pro",
      "cost_input_usd_per_million": 20.0,
      "cost_output_usd_per_million": 80.0,
      "context_window": 200000,
      "max_output_tokens": 100000,
      "modalities_input": [
        "text",
        "pdf",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "openai/o4-mini",
      "label": "o4-mini",
      "cost_input_usd_per_million": 1.1,
      "cost_output_usd_per_million": 4.4,
      "context_window": 200000,
      "max_output_tokens": 100000,
      "modalities_input": [
        "image",
        "text",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openai/o4-mini-high",
      "label": "o4 Mini High",
      "cost_input_usd_per_million": 1.1,
      "cost_output_usd_per_million": 4.4,
      "context_window": 200000,
      "max_output_tokens": 100000,
      "modalities_input": [
        "image",
        "text",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openrouter/auto",
      "label": "Auto Router",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 2000000,
      "max_output_tokens": 2000000,
      "modalities_input": [
        "text",
        "image",
        "audio",
        "pdf",
        "video"
      ],
      "modalities_output": [
        "text",
        "image"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openrouter/bodybuilder",
      "label": "Body Builder (beta)",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 128000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openrouter/free",
      "label": "Free Models Router",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 200000,
      "max_output_tokens": 8000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "free"
    },
    {
      "id": "openrouter/fusion",
      "label": "Fusion",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "openrouter/pareto-code",
      "label": "Pareto Code Router",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 2000000,
      "max_output_tokens": 200000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "perceptron/perceptron-mk1",
      "label": "Perceptron Mk1",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 1.5,
      "context_window": 32768,
      "max_output_tokens": 8192,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "perceptron/perceptron-mk1.5",
      "label": "Perceptron Mk1.5",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 1.5,
      "context_window": 36864,
      "max_output_tokens": 8192,
      "modalities_input": [
        "text",
        "image",
        "video",
        "audio"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "perplexity/sonar",
      "label": "Sonar",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 1.0,
      "context_window": 127072,
      "max_output_tokens": 114364,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "perplexity/sonar-deep-research",
      "label": "Sonar Deep Research",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 8.0,
      "context_window": 128000,
      "max_output_tokens": 115200,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "perplexity/sonar-pro",
      "label": "Sonar Pro",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 15.0,
      "context_window": 200000,
      "max_output_tokens": 8000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "perplexity/sonar-pro-search",
      "label": "Sonar Pro Search",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 15.0,
      "context_window": 200000,
      "max_output_tokens": 8000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "perplexity/sonar-reasoning-pro",
      "label": "Sonar Reasoning Pro",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 8.0,
      "context_window": 128000,
      "max_output_tokens": 115200,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "poolside/laguna-s-2.1",
      "label": "Laguna S 2.1",
      "cost_input_usd_per_million": 0.09,
      "cost_output_usd_per_million": 0.18,
      "context_window": 1048576,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "poolside/laguna-s-2.1:free",
      "label": "Laguna S 2.1 (free)",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "free"
    },
    {
      "id": "poolside/laguna-xs-2.1",
      "label": "Laguna XS 2.1",
      "cost_input_usd_per_million": 0.06,
      "cost_output_usd_per_million": 0.12,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "poolside/laguna-xs-2.1:free",
      "label": "Laguna XS 2.1 (free)",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "free"
    },
    {
      "id": "prism-ml/ternary-bonsai-2-27b",
      "label": "Ternary Bonsai 2 27B",
      "cost_input_usd_per_million": 0.075,
      "cost_output_usd_per_million": 0.5,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen-2.5-72b-instruct",
      "label": "Qwen2.5 72B Instruct",
      "cost_input_usd_per_million": 0.36,
      "cost_output_usd_per_million": 0.4,
      "context_window": 32768,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen-2.5-7b-instruct",
      "label": "Qwen2.5 7B Instruct",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.2,
      "context_window": 32768,
      "max_output_tokens": 29491,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen-2.5-coder-32b-instruct",
      "label": "Qwen2.5 Coder 32B Instruct",
      "cost_input_usd_per_million": 0.66,
      "cost_output_usd_per_million": 1.0,
      "context_window": 32768,
      "max_output_tokens": 29491,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen-plus",
      "label": "Qwen Plus",
      "cost_input_usd_per_million": 0.26,
      "cost_output_usd_per_million": 0.78,
      "context_window": 1000000,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "qwen/qwen-plus-2025-07-28",
      "label": "Qwen Plus 0728",
      "cost_input_usd_per_million": 0.26,
      "cost_output_usd_per_million": 0.78,
      "context_window": 1000000,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "qwen/qwen2.5-vl-72b-instruct",
      "label": "Qwen2.5 VL 72B Instruct",
      "cost_input_usd_per_million": 0.8,
      "cost_output_usd_per_million": 1.0,
      "context_window": 128000,
      "max_output_tokens": 115200,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-14b",
      "label": "Qwen3 14B",
      "cost_input_usd_per_million": 0.12,
      "cost_output_usd_per_million": 0.24,
      "context_window": 131072,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-235b-a22b",
      "label": "Qwen3 235B-A22B",
      "cost_input_usd_per_million": 0.455,
      "cost_output_usd_per_million": 1.82,
      "context_window": 131072,
      "max_output_tokens": 8192,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-235b-a22b-2507",
      "label": "Qwen3 235B A22B Instruct 2507",
      "cost_input_usd_per_million": 0.0875,
      "cost_output_usd_per_million": 0.35,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-235b-a22b-thinking-2507",
      "label": "Qwen3 235B A22B Thinking 2507",
      "cost_input_usd_per_million": 0.23,
      "cost_output_usd_per_million": 2.3,
      "context_window": 131072,
      "max_output_tokens": 117964,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-30b-a3b",
      "label": "Qwen3 30B A3B",
      "cost_input_usd_per_million": 0.12,
      "cost_output_usd_per_million": 0.5,
      "context_window": 131072,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-30b-a3b-instruct-2507",
      "label": "Qwen3 30B A3B Instruct 2507",
      "cost_input_usd_per_million": 0.04815,
      "cost_output_usd_per_million": 0.19305,
      "context_window": 262144,
      "max_output_tokens": 32000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-30b-a3b-thinking-2507",
      "label": "Qwen3 30B A3B Thinking 2507",
      "cost_input_usd_per_million": 0.2,
      "cost_output_usd_per_million": 2.4,
      "context_window": 81920,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-32b",
      "label": "Qwen3 32B",
      "cost_input_usd_per_million": 0.08,
      "cost_output_usd_per_million": 0.28,
      "context_window": 131072,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-8b",
      "label": "Qwen3 8B",
      "cost_input_usd_per_million": 0.117,
      "cost_output_usd_per_million": 0.455,
      "context_window": 131072,
      "max_output_tokens": 8192,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-coder",
      "label": "Qwen3 Coder 480B A35B",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.0,
      "context_window": 262144,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-coder-30b-a3b-instruct",
      "label": "Qwen3-Coder 30B-A3B Instruct",
      "cost_input_usd_per_million": 0.07,
      "cost_output_usd_per_million": 0.28,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-coder-flash",
      "label": "Qwen3 Coder Flash",
      "cost_input_usd_per_million": 0.195,
      "cost_output_usd_per_million": 0.975,
      "context_window": 1000000,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "qwen/qwen3-coder-next",
      "label": "Qwen3 Coder Next",
      "cost_input_usd_per_million": 0.12,
      "cost_output_usd_per_million": 0.8,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-coder-plus",
      "label": "Qwen3 Coder Plus",
      "cost_input_usd_per_million": 0.65,
      "cost_output_usd_per_million": 3.25,
      "context_window": 1000000,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "qwen/qwen3-max",
      "label": "Qwen3 Max",
      "cost_input_usd_per_million": 0.78,
      "cost_output_usd_per_million": 3.9,
      "context_window": 262144,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "qwen/qwen3-max-thinking",
      "label": "Qwen3 Max Thinking",
      "cost_input_usd_per_million": 0.78,
      "cost_output_usd_per_million": 3.9,
      "context_window": 262144,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "qwen/qwen3-next-80b-a3b-instruct",
      "label": "Qwen3-Next 80B-A3B Instruct",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 1.1,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-next-80b-a3b-thinking",
      "label": "Qwen3-Next 80B-A3B (Thinking)",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 1.2,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-vl-235b-a22b-instruct",
      "label": "Qwen3 VL 235B A22B Instruct",
      "cost_input_usd_per_million": 0.21,
      "cost_output_usd_per_million": 1.9,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-vl-235b-a22b-thinking",
      "label": "Qwen3 VL 235B A22B Thinking",
      "cost_input_usd_per_million": 0.4,
      "cost_output_usd_per_million": 4.0,
      "context_window": 131072,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-vl-30b-a3b-instruct",
      "label": "Qwen3 VL 30B A3B Instruct",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.6,
      "context_window": 262144,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-vl-30b-a3b-thinking",
      "label": "Qwen3 VL 30B A3B Thinking",
      "cost_input_usd_per_million": 0.2,
      "cost_output_usd_per_million": 2.4,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-vl-32b-instruct",
      "label": "Qwen3 VL 32B Instruct",
      "cost_input_usd_per_million": 0.104,
      "cost_output_usd_per_million": 0.416,
      "context_window": 131072,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-vl-8b-instruct",
      "label": "Qwen3 VL 8B Instruct",
      "cost_input_usd_per_million": 0.117,
      "cost_output_usd_per_million": 0.455,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3-vl-8b-thinking",
      "label": "Qwen3 VL 8B Thinking",
      "cost_input_usd_per_million": 0.18,
      "cost_output_usd_per_million": 2.1,
      "context_window": 131072,
      "max_output_tokens": 32768,
      "modalities_input": [
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3.5-122b-a10b",
      "label": "Qwen3.5 122B-A10B",
      "cost_input_usd_per_million": 0.26,
      "cost_output_usd_per_million": 2.08,
      "context_window": 262144,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3.5-27b",
      "label": "Qwen3.5 27B",
      "cost_input_usd_per_million": 0.195,
      "cost_output_usd_per_million": 1.56,
      "context_window": 262144,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3.5-35b-a3b",
      "label": "Qwen3.5 35B-A3B",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 1.0,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3.5-397b-a17b",
      "label": "Qwen3.5 397B-A17B",
      "cost_input_usd_per_million": 0.55,
      "cost_output_usd_per_million": 3.5,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3.5-9b",
      "label": "Qwen3.5 9B",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.15,
      "context_window": 262144,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3.5-flash-02-23",
      "label": "Qwen3.5-Flash",
      "cost_input_usd_per_million": 0.065,
      "cost_output_usd_per_million": 0.26,
      "context_window": 1000000,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "qwen/qwen3.5-plus-02-15",
      "label": "Qwen3.5 Plus 2026-02-15",
      "cost_input_usd_per_million": 0.26,
      "cost_output_usd_per_million": 1.56,
      "context_window": 1000000,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "qwen/qwen3.5-plus-20260420",
      "label": "Qwen3.5 Plus 2026-04-20",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.8,
      "context_window": 1000000,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "qwen/qwen3.6-27b",
      "label": "Qwen3.6 27B",
      "cost_input_usd_per_million": 0.32,
      "cost_output_usd_per_million": 3.2,
      "context_window": 262144,
      "max_output_tokens": 81920,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3.6-35b-a3b",
      "label": "Qwen3.6 35B-A3B",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 1.0,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3.6-flash",
      "label": "Qwen3.6 Flash",
      "cost_input_usd_per_million": 0.1875,
      "cost_output_usd_per_million": 1.125,
      "context_window": 1000000,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "qwen/qwen3.6-max-preview",
      "label": "Qwen3.6 Max Preview",
      "cost_input_usd_per_million": 1.027,
      "cost_output_usd_per_million": 6.162,
      "context_window": 262144,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "qwen/qwen3.6-plus",
      "label": "Qwen3.6 Plus",
      "cost_input_usd_per_million": 0.325,
      "cost_output_usd_per_million": 1.95,
      "context_window": 1000000,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "qwen/qwen3.7-flash",
      "label": "Qwen3.7 Flash",
      "cost_input_usd_per_million": 0.03,
      "cost_output_usd_per_million": 0.13,
      "context_window": 1000000,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "qwen/qwen3.7-max",
      "label": "Qwen3.7 Max",
      "cost_input_usd_per_million": 1.475,
      "cost_output_usd_per_million": 4.425,
      "context_window": 1000000,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "qwen/qwen3.7-plus",
      "label": "Qwen3.7 Plus",
      "cost_input_usd_per_million": 0.32,
      "cost_output_usd_per_million": 1.28,
      "context_window": 1000000,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "qwen/qwen3.8-2.4t-a95b",
      "label": "Qwen3.8 2.4T A95B",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 1048576,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3.8-27b",
      "label": "Qwen3.8 27B",
      "cost_input_usd_per_million": 0.42,
      "cost_output_usd_per_million": 3.0,
      "context_window": 1000000,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "qwen/qwen3.8-27b:free",
      "label": "Qwen3.8 27B (free)",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "free"
    },
    {
      "id": "qwen/qwen3.8-flash",
      "label": "Qwen3.8 Flash",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.47,
      "context_window": 1000000,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "qwen/qwen3.8-max-0902",
      "label": "Qwen3.8 Max 0902",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 1000000,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "qwen/qwen3.8-max-prime",
      "label": "Qwen 3.8 Max Prime",
      "cost_input_usd_per_million": 4.0,
      "cost_output_usd_per_million": 12.0,
      "context_window": 1000000,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "qwen/qwen3.8-omni-flash",
      "label": "Qwen3.8 Omni Flash",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.47,
      "context_window": 1000000,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image",
        "audio",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "rekaai/reka-edge",
      "label": "Reka Edge",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.1,
      "context_window": 16384,
      "max_output_tokens": 14745,
      "modalities_input": [
        "image",
        "text",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "rekaai/reka-flash-3",
      "label": "Reka Flash 3",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.2,
      "context_window": 65536,
      "max_output_tokens": 58982,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "relace/relace-apply-3",
      "label": "Relace Apply 3",
      "cost_input_usd_per_million": 0.85,
      "cost_output_usd_per_million": 1.25,
      "context_window": 256000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "relace/relace-search",
      "label": "Relace Search",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 3.0,
      "context_window": 256000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "sakana/fugu-max",
      "label": "Fugu Max",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "sakana/fugu-ultra",
      "label": "Fugu Ultra",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 30.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "sakana/fugu-ultra-v2",
      "label": "Fugu Ultra v2",
      "cost_input_usd_per_million": 5.0,
      "cost_output_usd_per_million": 30.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "sakana/sakana-namazu",
      "label": "Sakana Namazu",
      "cost_input_usd_per_million": 0.95,
      "cost_output_usd_per_million": 4.0,
      "context_window": 262144,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "sao10k/l3-lunaris-8b",
      "label": "Llama 3 8B Lunaris",
      "cost_input_usd_per_million": 0.04,
      "cost_output_usd_per_million": 0.05,
      "context_window": 8192,
      "max_output_tokens": 7372,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "sao10k/l3.1-euryale-70b",
      "label": "Llama 3.1 Euryale 70B v2.2",
      "cost_input_usd_per_million": 0.85,
      "cost_output_usd_per_million": 0.85,
      "context_window": 131072,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "sao10k/l3.3-euryale-70b",
      "label": "Llama 3.3 Euryale 70B",
      "cost_input_usd_per_million": 0.65,
      "cost_output_usd_per_million": 0.75,
      "context_window": 131072,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "stealth/space-bunny-alpha",
      "label": "Space Bunny Alpha",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 1000000,
      "max_output_tokens": 524288,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "free"
    },
    {
      "id": "stepfun/step-3.5-flash",
      "label": "Step 3.5 Flash",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.3,
      "context_window": 262144,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "stepfun/step-3.7-flash",
      "label": "Step 3.7 Flash",
      "cost_input_usd_per_million": 0.2,
      "cost_output_usd_per_million": 1.15,
      "context_window": 262144,
      "max_output_tokens": 230400,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "tencent/hunyuan-a13b-instruct",
      "label": "Hunyuan A13B Instruct",
      "cost_input_usd_per_million": 0.14,
      "cost_output_usd_per_million": 0.57,
      "context_window": 131072,
      "max_output_tokens": 117964,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "tencent/hy-mt2-1.8b",
      "label": "Hy-MT2-1.8B",
      "cost_input_usd_per_million": 0.044,
      "cost_output_usd_per_million": 0.177,
      "context_window": 8192,
      "max_output_tokens": 4096,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "tencent/hy-mt2-30b-a3b",
      "label": "Hy-MT2-30B-A3B",
      "cost_input_usd_per_million": 0.074,
      "cost_output_usd_per_million": 0.295,
      "context_window": 8192,
      "max_output_tokens": 4096,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "tencent/hy-mt2-7b",
      "label": "Hy-MT2-7B",
      "cost_input_usd_per_million": 0.074,
      "cost_output_usd_per_million": 0.295,
      "context_window": 8192,
      "max_output_tokens": 4096,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "tencent/hy3",
      "label": "Hy3",
      "cost_input_usd_per_million": 0.0825,
      "cost_output_usd_per_million": 0.33,
      "context_window": 262144,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "tencent/hy3-preview",
      "label": "Hy3 preview",
      "cost_input_usd_per_million": 0.18,
      "cost_output_usd_per_million": 0.6,
      "context_window": 262144,
      "max_output_tokens": 235929,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "tencent/hy4-preview",
      "label": "Hy4 preview",
      "cost_input_usd_per_million": 0.7506,
      "cost_output_usd_per_million": 2.2509,
      "context_window": 1048576,
      "max_output_tokens": 64000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "thedrummer/cydonia-24b-v4.1",
      "label": "Cydonia 24B V4.1",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 0.5,
      "context_window": 131072,
      "max_output_tokens": 117964,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "thedrummer/skyfall-36b-v2",
      "label": "Skyfall 36B V2",
      "cost_input_usd_per_million": 0.55,
      "cost_output_usd_per_million": 0.8,
      "context_window": 32768,
      "max_output_tokens": 29491,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "thedrummer/unslopnemo-12b",
      "label": "UnslopNemo 12B",
      "cost_input_usd_per_million": 0.4,
      "cost_output_usd_per_million": 0.4,
      "context_window": 1024000,
      "max_output_tokens": 819200,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "thinkingmachines/inkling",
      "label": "Inkling",
      "cost_input_usd_per_million": 0.95,
      "cost_output_usd_per_million": 4.05,
      "context_window": 524288,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text",
        "image",
        "audio"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "thinkingmachines/inkling-small",
      "label": "Inkling Small",
      "cost_input_usd_per_million": 0.45,
      "cost_output_usd_per_million": 1.2,
      "context_window": 524288,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text",
        "image",
        "audio"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "thinkingmachines/inkling-small:free",
      "label": "Inkling Small (free)",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 1048576,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text",
        "image",
        "audio"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "free"
    },
    {
      "id": "thinkingmachines/inkling:free",
      "label": "Inkling (free)",
      "cost_input_usd_per_million": 0.0,
      "cost_output_usd_per_million": 0.0,
      "context_window": 1048576,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text",
        "image",
        "audio"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "free"
    },
    {
      "id": "unbiased/pareto",
      "label": "Pareto",
      "cost_input_usd_per_million": 2.5,
      "cost_output_usd_per_million": 7.5,
      "context_window": 262144,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "unbiased/pareto-26.10-preview",
      "label": "Pareto 26.10 Preview",
      "cost_input_usd_per_million": 0.8,
      "cost_output_usd_per_million": 3.2,
      "context_window": 1048576,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "undi95/remm-slerp-l2-13b",
      "label": "ReMM SLERP 13B",
      "cost_input_usd_per_million": 0.35,
      "cost_output_usd_per_million": 0.65,
      "context_window": 6144,
      "max_output_tokens": 5529,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "upstage/solar-mini4",
      "label": "Solar Mini 4",
      "cost_input_usd_per_million": 0.05,
      "cost_output_usd_per_million": 0.2,
      "context_window": 524288,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "upstage/solar-pro-3",
      "label": "Solar Pro 3",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.6,
      "context_window": 131072,
      "max_output_tokens": 117964,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "upstage/solar-pro4",
      "label": "Solar Pro 4",
      "cost_input_usd_per_million": 0.09,
      "cost_output_usd_per_million": 0.36,
      "context_window": 524288,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "writer/palmyra-x5",
      "label": "Palmyra X5",
      "cost_input_usd_per_million": 0.6,
      "cost_output_usd_per_million": 6.0,
      "context_window": 1040000,
      "max_output_tokens": 8192,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": false,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "x-ai/grok-4.20",
      "label": "Grok 4.20",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 2.5,
      "context_window": 2000000,
      "max_output_tokens": 1800000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "x-ai/grok-4.20-multi-agent",
      "label": "Grok 4.20 Multi-Agent",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 2.5,
      "context_window": 2000000,
      "max_output_tokens": 1800000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "x-ai/grok-4.3",
      "label": "Grok 4.3",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 2.5,
      "context_window": 1000000,
      "max_output_tokens": 900000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "x-ai/grok-4.5",
      "label": "Grok 4.5",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 500000,
      "max_output_tokens": 450000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "x-ai/grok-4.6",
      "label": "Grok 4.6",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 500000,
      "max_output_tokens": 450000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "x-ai/grok-4.7",
      "label": "Grok 4.7",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 500000,
      "max_output_tokens": 450000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "x-ai/grok-build-0.1",
      "label": "Grok Build 0.1",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 2.0,
      "context_window": 256000,
      "max_output_tokens": 230400,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "xiaomi/mimo-v2.5",
      "label": "MiMo-V2.5",
      "cost_input_usd_per_million": 0.14,
      "cost_output_usd_per_million": 0.28,
      "context_window": 1050000,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image",
        "audio",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "xiaomi/mimo-v2.5-pro",
      "label": "MiMo-V2.5-Pro",
      "cost_input_usd_per_million": 0.435,
      "cost_output_usd_per_million": 0.87,
      "context_window": 1050000,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "xiaomi/mimo-v2.6-flash",
      "label": "MiMo-V2.6-Flash",
      "cost_input_usd_per_million": 0.14,
      "cost_output_usd_per_million": 0.28,
      "context_window": 1050000,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image",
        "audio",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "xiaomi/mimo-v2.6-pro",
      "label": "MiMo-V2.6-Pro",
      "cost_input_usd_per_million": 0.435,
      "cost_output_usd_per_million": 0.87,
      "context_window": 1050000,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image",
        "audio",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "xiaomi/mimo-v2.6-pro-ultraspeed",
      "label": "MiMo-V2.6-Pro-UltraSpeed",
      "cost_input_usd_per_million": 4.35,
      "cost_output_usd_per_million": 8.7,
      "context_window": 1048576,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image",
        "audio",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "flagship"
    },
    {
      "id": "z-ai/glm-4.5",
      "label": "GLM-4.5",
      "cost_input_usd_per_million": 0.6,
      "cost_output_usd_per_million": 2.2,
      "context_window": 131072,
      "max_output_tokens": 98304,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "z-ai/glm-4.5-air",
      "label": "GLM-4.5-Air",
      "cost_input_usd_per_million": 0.13,
      "cost_output_usd_per_million": 0.85,
      "context_window": 131072,
      "max_output_tokens": 98304,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "z-ai/glm-4.5v",
      "label": "GLM-4.5V",
      "cost_input_usd_per_million": 0.6,
      "cost_output_usd_per_million": 1.8,
      "context_window": 65536,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "z-ai/glm-4.6",
      "label": "GLM-4.6",
      "cost_input_usd_per_million": 0.43,
      "cost_output_usd_per_million": 1.75,
      "context_window": 204800,
      "max_output_tokens": 16384,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "z-ai/glm-4.6v",
      "label": "GLM-4.6V",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 0.9,
      "context_window": 131072,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "z-ai/glm-4.7",
      "label": "GLM-4.7",
      "cost_input_usd_per_million": 0.6,
      "cost_output_usd_per_million": 2.2,
      "context_window": 204800,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "z-ai/glm-4.7-flash",
      "label": "GLM-4.7-Flash",
      "cost_input_usd_per_million": 0.0605,
      "cost_output_usd_per_million": 0.4,
      "context_window": 200000,
      "max_output_tokens": 117964,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "z-ai/glm-5",
      "label": "GLM-5",
      "cost_input_usd_per_million": 0.6,
      "cost_output_usd_per_million": 1.92,
      "context_window": 204800,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "z-ai/glm-5-turbo",
      "label": "GLM-5-Turbo",
      "cost_input_usd_per_million": 1.2,
      "cost_output_usd_per_million": 4.0,
      "context_window": 202752,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "z-ai/glm-5.1",
      "label": "GLM-5.1",
      "cost_input_usd_per_million": 0.9646,
      "cost_output_usd_per_million": 3.0316,
      "context_window": 204800,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "z-ai/glm-5.2",
      "label": "GLM-5.2",
      "cost_input_usd_per_million": 0.41,
      "cost_output_usd_per_million": 3.99,
      "context_window": 1048576,
      "max_output_tokens": 943718,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "z-ai/glm-5.3",
      "label": "GLM-5.3",
      "cost_input_usd_per_million": 1.4,
      "cost_output_usd_per_million": 4.4,
      "context_window": 1048576,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "z-ai/glm-5.3-flash",
      "label": "GLM-5.3-Flash",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.5,
      "context_window": 1048576,
      "max_output_tokens": 943717,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "z-ai/glm-5.3-flashx",
      "label": "GLM 5.3 FlashX",
      "cost_input_usd_per_million": 0.37,
      "cost_output_usd_per_million": 1.25,
      "context_window": 1048576,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "z-ai/glm-5.3-prime",
      "label": "GLM 5.3 Prime",
      "cost_input_usd_per_million": 2.8,
      "cost_output_usd_per_million": 8.8,
      "context_window": 1000000,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "z-ai/glm-5v-turbo",
      "label": "GLM-5V-Turbo",
      "cost_input_usd_per_million": 1.2,
      "cost_output_usd_per_million": 4.0,
      "context_window": 202752,
      "max_output_tokens": 131072,
      "modalities_input": [
        "image",
        "text",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": false,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "~anthropic/claude-fable-latest",
      "label": "Claude Fable Latest",
      "cost_input_usd_per_million": 10.0,
      "cost_output_usd_per_million": 50.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "~anthropic/claude-haiku-latest",
      "label": "Claude Haiku Latest",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 5.0,
      "context_window": 200000,
      "max_output_tokens": 64000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "~anthropic/claude-opus-latest",
      "label": "Claude Opus Latest",
      "cost_input_usd_per_million": 4.0,
      "cost_output_usd_per_million": 20.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "~anthropic/claude-sonnet-latest",
      "label": "Claude Sonnet Latest",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 10.0,
      "context_window": 1000000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "~deepseek/deepseek-flash-latest",
      "label": "DeepSeek Flash Latest",
      "cost_input_usd_per_million": 0.015,
      "cost_output_usd_per_million": 0.676999,
      "context_window": 1048576,
      "max_output_tokens": 943718,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "~deepseek/deepseek-pro-latest",
      "label": "DeepSeek Pro Latest",
      "cost_input_usd_per_million": 0.132,
      "cost_output_usd_per_million": 0.396,
      "context_window": 1048576,
      "max_output_tokens": 393216,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "~deepseek/deepseek-v4-flash-latest",
      "label": "DeepSeek V4 Flash Latest",
      "cost_input_usd_per_million": 0.008625,
      "cost_output_usd_per_million": 0.808374,
      "context_window": 1048576,
      "max_output_tokens": 943718,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "~google/gemini-flash-latest",
      "label": "Gemini Flash Latest",
      "cost_input_usd_per_million": 0.75,
      "cost_output_usd_per_million": 3.75,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image",
        "video",
        "pdf",
        "audio"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "~google/gemini-pro-latest",
      "label": "Gemini Pro Latest",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 12.0,
      "context_window": 1048576,
      "max_output_tokens": 65536,
      "modalities_input": [
        "audio",
        "pdf",
        "image",
        "text",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "~moonshotai/kimi-latest",
      "label": "Kimi Latest",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 11.357,
      "context_window": 1048576,
      "max_output_tokens": 943718,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "~openai/gpt-astra-latest",
      "label": "GPT Astra Latest",
      "cost_input_usd_per_million": 10.0,
      "cost_output_usd_per_million": 50.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "pdf",
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": "flagship"
    },
    {
      "id": "~openai/gpt-luna-latest",
      "label": "GPT Luna Latest",
      "cost_input_usd_per_million": 0.1,
      "cost_output_usd_per_million": 0.5,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "pdf",
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "~openai/gpt-mini-latest",
      "label": "GPT Mini Latest",
      "cost_input_usd_per_million": 0.75,
      "cost_output_usd_per_million": 4.5,
      "context_window": 400000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "pdf",
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "~openai/gpt-sol-latest",
      "label": "GPT Sol Latest",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 10.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "pdf",
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "~openai/gpt-terra-latest",
      "label": "GPT Terra Latest",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 12.0,
      "context_window": 1050000,
      "max_output_tokens": 128000,
      "modalities_input": [
        "pdf",
        "image",
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "~x-ai/grok-latest",
      "label": "Grok Latest",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 500000,
      "max_output_tokens": 450000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "~z-ai/glm-flash-latest",
      "label": "GLM Flash Latest",
      "cost_input_usd_per_million": 0.02625,
      "cost_output_usd_per_million": 0.928749,
      "context_window": 1048576,
      "max_output_tokens": 943718,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "~z-ai/glm-latest",
      "label": "GLM Latest",
      "cost_input_usd_per_million": 0.12,
      "cost_output_usd_per_million": 4.0,
      "context_window": 1048576,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    }
  ],
  "togetherai": [
    {
      "id": "LiquidAI/LFM2-24B-A2B",
      "label": "LFM2-24B-A2B",
      "cost_input_usd_per_million": 0.03,
      "cost_output_usd_per_million": 0.12,
      "context_window": 32768,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "MiniMaxAI/MiniMax-M2.5",
      "label": "MiniMax-M2.5",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.2,
      "context_window": 204800,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "MiniMaxAI/MiniMax-M2.7",
      "label": "MiniMax-M2.7",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.2,
      "context_window": 196608,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "MiniMaxAI/MiniMax-M3",
      "label": "MiniMax-M3",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.2,
      "context_window": 524288,
      "max_output_tokens": 250000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "Qwen/Qwen2.5-7B-Instruct-Turbo",
      "label": "Qwen 2.5 7B Instruct Turbo",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 0.3,
      "context_window": 32768,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "Qwen/Qwen3-235B-A22B-Instruct-2507-tput",
      "label": "Qwen3 235B A22B Instruct 2507 FP8",
      "cost_input_usd_per_million": 0.2,
      "cost_output_usd_per_million": 0.6,
      "context_window": 262144,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8",
      "label": "Qwen3 Coder 480B A35B Instruct",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 2.0,
      "context_window": 262144,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "Qwen/Qwen3-Coder-Next-FP8",
      "label": "Qwen3 Coder Next FP8",
      "cost_input_usd_per_million": 0.5,
      "cost_output_usd_per_million": 1.2,
      "context_window": 262144,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "Qwen/Qwen3.5-397B-A17B",
      "label": "Qwen3.5 397B A17B",
      "cost_input_usd_per_million": 0.6,
      "cost_output_usd_per_million": 3.6,
      "context_window": 262144,
      "max_output_tokens": 130000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": true,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "Qwen/Qwen3.5-9B",
      "label": "Qwen3.5 9B",
      "cost_input_usd_per_million": 0.17,
      "cost_output_usd_per_million": 0.25,
      "context_window": 262144,
      "max_output_tokens": 65536,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "Qwen/Qwen3.6-Plus",
      "label": "Qwen3.6 Plus",
      "cost_input_usd_per_million": 0.5,
      "cost_output_usd_per_million": 3.0,
      "context_window": 1000000,
      "max_output_tokens": 500000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "Qwen/Qwen3.7-Max",
      "label": "Qwen3.7 Max",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 3.75,
      "context_window": 1000000,
      "max_output_tokens": 500000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "deepseek-ai/DeepSeek-R1",
      "label": "DeepSeek-R1",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 7.0,
      "context_window": 163839,
      "max_output_tokens": 163839,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "flagship"
    },
    {
      "id": "deepseek-ai/DeepSeek-V3",
      "label": "DeepSeek-V3",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 1.25,
      "context_window": 131072,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek-ai/DeepSeek-V3-1",
      "label": "DeepSeek V3.1",
      "cost_input_usd_per_million": 0.6,
      "cost_output_usd_per_million": 1.7,
      "context_window": 131072,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek-ai/DeepSeek-V4-Flash-0731",
      "label": "DeepSeek V4 Flash 0731",
      "cost_input_usd_per_million": 0.14,
      "cost_output_usd_per_million": 0.28,
      "context_window": 1048576,
      "max_output_tokens": 384000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek-ai/DeepSeek-V4-Pro-0813",
      "label": "DeepSeek V4 Pro 0813",
      "cost_input_usd_per_million": 1.32,
      "cost_output_usd_per_million": 3.96,
      "context_window": 1048576,
      "max_output_tokens": 384000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "deepseek-ai/DeepSeek-V4.1-Flash",
      "label": "DeepSeek V4.1 Flash",
      "cost_input_usd_per_million": 0.3,
      "cost_output_usd_per_million": 1.2,
      "context_window": 1048576,
      "max_output_tokens": 384000,
      "modalities_input": [
        "text",
        "image"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "essentialai/Rnj-1-Instruct",
      "label": "Rnj-1 Instruct",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.15,
      "context_window": 32768,
      "max_output_tokens": 32768,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
      "label": "Llama 3.3 70B",
      "cost_input_usd_per_million": 1.04,
      "cost_output_usd_per_million": 1.04,
      "context_window": 131072,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": false,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "moonshotai/Kimi-K3",
      "label": "Kimi K3",
      "cost_input_usd_per_million": 3.0,
      "cost_output_usd_per_million": 15.0,
      "context_window": 1048576,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "flagship"
    },
    {
      "id": "nvidia/nemotron-3-ultra-550b-a55b",
      "label": "Nemotron 3 Ultra 550B A55B",
      "cost_input_usd_per_million": 0.6,
      "cost_output_usd_per_million": 3.6,
      "context_window": 512300,
      "max_output_tokens": 512300,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "openai/gpt-oss-120b",
      "label": "GPT OSS 120B",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.6,
      "context_window": 131072,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": null,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "thinkingmachines/Inkling",
      "label": "Inkling",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 4.05,
      "context_window": 524288,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text",
        "image",
        "audio"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "zai-org/GLM-5",
      "label": "GLM-5",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 3.2,
      "context_window": 202752,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "zai-org/GLM-5.1",
      "label": "GLM-5.1",
      "cost_input_usd_per_million": 1.4,
      "cost_output_usd_per_million": 4.4,
      "context_window": 202752,
      "max_output_tokens": 131072,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "zai-org/GLM-5.2",
      "label": "GLM-5.2",
      "cost_input_usd_per_million": 1.4,
      "cost_output_usd_per_million": 4.4,
      "context_window": 1048575,
      "max_output_tokens": 164000,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "zai-org/GLM-5.3",
      "label": "GLM-5.3",
      "cost_input_usd_per_million": 1.4,
      "cost_output_usd_per_million": 4.4,
      "context_window": 1048576,
      "max_output_tokens": 262144,
      "modalities_input": [
        "text"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": false,
      "attachment": false,
      "open_weights": true,
      "tier": "opensource"
    },
    {
      "id": "zai-org/GLM-5.3-Flash",
      "label": "GLM-5.3-Flash",
      "cost_input_usd_per_million": 0.15,
      "cost_output_usd_per_million": 0.5,
      "context_window": 1048575,
      "max_output_tokens": 400000,
      "modalities_input": [
        "text",
        "image",
        "video"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": true,
      "tier": "opensource"
    }
  ],
  "xai": [
    {
      "id": "grok-4.20-0309-non-reasoning",
      "label": "Grok 4.20 (Non-Reasoning)",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 2.5,
      "context_window": 1000000,
      "max_output_tokens": 30000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "grok-4.20-0309-reasoning",
      "label": "Grok 4.20 (Reasoning)",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 2.5,
      "context_window": 1000000,
      "max_output_tokens": 30000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "grok-4.20-multi-agent-0309",
      "label": "Grok 4.20 Multi-Agent",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 2.5,
      "context_window": 1000000,
      "max_output_tokens": 30000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": false,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "grok-4.3",
      "label": "Grok 4.3",
      "cost_input_usd_per_million": 1.25,
      "cost_output_usd_per_million": 2.5,
      "context_window": 1000000,
      "max_output_tokens": 30000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "grok-4.5",
      "label": "Grok 4.5",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 500000,
      "max_output_tokens": 500000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "grok-4.6",
      "label": "Grok 4.6",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 500000,
      "max_output_tokens": 500000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "grok-4.7",
      "label": "Grok 4.7",
      "cost_input_usd_per_million": 2.0,
      "cost_output_usd_per_million": 6.0,
      "context_window": 500000,
      "max_output_tokens": 500000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "grok-build-0.1",
      "label": "Grok Build 0.1",
      "cost_input_usd_per_million": 1.0,
      "cost_output_usd_per_million": 2.0,
      "context_window": 256000,
      "max_output_tokens": 256000,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "text"
      ],
      "tool_call": true,
      "structured_output": true,
      "reasoning": true,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "grok-imagine-image",
      "label": "Grok Imagine Image",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 16000,
      "max_output_tokens": null,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "image",
        "pdf"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "grok-imagine-image-quality",
      "label": "Grok Imagine Image Quality",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 16000,
      "max_output_tokens": null,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "image",
        "pdf"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "grok-imagine-video",
      "label": "Grok Imagine Video",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 1024,
      "max_output_tokens": null,
      "modalities_input": [
        "text",
        "image",
        "video",
        "pdf"
      ],
      "modalities_output": [
        "video"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "grok-imagine-video-1.5",
      "label": "Grok Imagine Video 1.5",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 1024,
      "max_output_tokens": null,
      "modalities_input": [
        "text",
        "image",
        "audio",
        "pdf"
      ],
      "modalities_output": [
        "video"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    },
    {
      "id": "grok-imagine-video-1.5-lite",
      "label": "Grok Imagine Video 1.5 Lite",
      "cost_input_usd_per_million": null,
      "cost_output_usd_per_million": null,
      "context_window": 1024,
      "max_output_tokens": null,
      "modalities_input": [
        "text",
        "image",
        "pdf"
      ],
      "modalities_output": [
        "video"
      ],
      "tool_call": false,
      "structured_output": null,
      "reasoning": false,
      "vision": true,
      "attachment": true,
      "open_weights": false,
      "tier": null
    }
  ]
};
