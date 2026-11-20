# Local model setup

The repository excludes downloaded binaries and weights. Forms, records and explicitly parsed commands work without them. Email drafting, local-model responses and note extraction need the engine.

Copy **Handoff-Studio/engine** from the portable Windows release, if available, into the same location in this checkout.

For manual Windows x64 setup:

1. Download the Windows CPU x64 archive from [llama.cpp b12431](https://github.com/ggml-org/llama.cpp/releases/tag/b12431).
2. Put **llama-completion.exe** and its companion DLLs in **Handoff-Studio/engine/**.
3. Download **qwen2.5-1.5b-instruct-q4_k_m.gguf** from the official [Qwen model files](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/tree/main), into that directory.
4. Restart PeopleDesk.

The model used in development has SHA-256:

```text
6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e
```

Alternatively set **PEOPLEDESK_ENGINE** to the folder containing the runtime, DLLs and model. Generation speed depends on hardware. The model can misunderstand; review its output.

Retain vendor licenses when redistributing. [Qwen model card](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF) · [llama.cpp source](https://github.com/ggml-org/llama.cpp/tree/b12431).
