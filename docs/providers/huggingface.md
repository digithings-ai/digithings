# Hugging Face Inference Providers

**Free tier:** Small anonymous quota (unreliable); HF PRO ($9/mo) users get ~$2/mo credits routed across providers.

**Best for:** model discovery, evals, and routing through HF's aggregator to Together/Fireworks/SambaNova behind the scenes.

## 1. Sign up

- Go to https://huggingface.co and create an account.
- (Optional) Upgrade to PRO at https://huggingface.co/pro for the monthly inference credits.

## 2. Create access token

- Go to https://huggingface.co/settings/tokens → **Create new token**.
- Type: **Read** (sufficient for inference).
- Name it, copy (starts with `hf_...`).

## 3. Add to `.env`

```bash
HF_TOKEN=hf_...
```

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: hf-llama-70b
    litellm_params:
      model: huggingface/meta-llama/Llama-3.3-70B-Instruct
      api_key: os.environ/HF_TOKEN

  - model_name: hf-qwen-coder
    litellm_params:
      model: huggingface/Qwen/Qwen2.5-Coder-32B-Instruct
      api_key: os.environ/HF_TOKEN
```

## 5. Verify

```bash
curl -s https://router.huggingface.co/v1/chat/completions \
  -H "Authorization: Bearer $HF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"meta-llama/Llama-3.3-70B-Instruct","messages":[{"role":"user","content":"Say hi"}]}'
```

## Gotchas

- Free quota is unreliable for production — use as model-discovery surface, not primary.
- Router pricing = upstream provider pricing + small HF markup.

## Docs

https://huggingface.co/docs/inference-providers
