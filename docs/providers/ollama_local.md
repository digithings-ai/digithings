# Ollama (Local)

**Cost:** zero per-token cost — inference runs on your own hardware.

**Best for:** offline dev, privacy-critical work, unlimited testing on small-to-mid models.

**Hardware rule of thumb:** 7–14B models run comfortably on 16GB Mac / consumer GPU (Q4/Q5 quant). 70B needs 48GB+ VRAM or aggressive quantization.

## 1. Install

**macOS / Windows:**

```bash
# macOS via Homebrew
brew install ollama
# Or download from https://ollama.com/download
```

**Linux:**

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

## 2. Start the server

```bash
ollama serve  # runs on http://localhost:11434
```

(On macOS the app auto-starts a background server.)

## 3. Pull a model

```bash
ollama pull llama3.3:70b        # ~40 GB, needs 48 GB+ RAM
ollama pull qwen2.5-coder:14b   # ~9 GB, comfortable on 16 GB Mac
ollama pull gemma3:4b           # ~3 GB, fast
ollama pull deepseek-r1:8b      # reasoning
```

Browse catalog at https://ollama.com/library.

## 4. LiteLLM entry

```yaml
model_list:
  - model_name: local-llama-70b
    litellm_params:
      model: ollama_chat/llama3.3:70b
      api_base: http://localhost:11434

  - model_name: local-coder
    litellm_params:
      model: ollama_chat/qwen2.5-coder:14b
      api_base: http://localhost:11434

  - model_name: local-small
    litellm_params:
      model: ollama_chat/gemma3:4b
      api_base: http://localhost:11434
```

If LiteLLM runs in Docker and Ollama runs on the host, use `http://host.docker.internal:11434` instead of `localhost`.

## 5. Verify

```bash
curl -s http://localhost:11434/api/chat \
  -d '{"model":"qwen2.5-coder:14b","messages":[{"role":"user","content":"Say hi"}],"stream":false}'
```

Or via the OpenAI-compatible endpoint:

```bash
curl -s http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5-coder:14b","messages":[{"role":"user","content":"Say hi"}]}'
```

## Tips

- `ollama ps` — show running models and VRAM usage.
- `ollama rm <model>` — free disk space.
- For concurrent requests set `OLLAMA_NUM_PARALLEL=N` in env.
- To pre-load a model so first request is fast: `ollama run <model> ""` on startup.

## Docs

https://github.com/ollama/ollama
