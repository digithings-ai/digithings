# Nvidia NIM (build.nvidia.com)

**Free tier:** 1,000 credits on signup; 5,000 more with Developer Program membership. **Credits don't refill** — once exhausted you need an enterprise contract or self-hosted NIM.

**Best for:** evaluating a wide catalog of open models (Nemotron, Llama 3.3/4, DeepSeek R1, embeddings) before choosing a long-term host.

## 1. Sign up

- Go to https://build.nvidia.com and sign in (personal NVIDIA account).
- For +5,000 credits, join https://developer.nvidia.com (free).

## 2. Create API key

- Pick any model on build.nvidia.com → **Get API Key** button on the model page.
- Copy (starts with `nvapi-...`).

## 3. Add to `.env`

```bash
NVIDIA_NIM_API_KEY=nvapi-...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: nim-nemotron-70b
    litellm_params:
      model: nvidia_nim/nvidia/llama-3.1-nemotron-70b-instruct
      api_key: os.environ/NVIDIA_NIM_API_KEY

  - model_name: nim-llama-70b
    litellm_params:
      model: nvidia_nim/meta/llama-3.3-70b-instruct
      api_key: os.environ/NVIDIA_NIM_API_KEY

  - model_name: nim-deepseek-r1
    litellm_params:
      model: nvidia_nim/deepseek-ai/deepseek-r1
      api_key: os.environ/NVIDIA_NIM_API_KEY
```

## 5. Verify

```bash
curl -s https://integrate.api.nvidia.com/v1/chat/completions \
  -H "Authorization: Bearer $NVIDIA_NIM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"meta/llama-3.3-70b-instruct","messages":[{"role":"user","content":"Say hi"}]}'
```

## Docs

https://docs.api.nvidia.com
