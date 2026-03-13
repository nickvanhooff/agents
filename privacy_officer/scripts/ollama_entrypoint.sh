#!/bin/bash
# Start Ollama in the background
/bin/ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "Waiting for Ollama to start..."
sleep 5

# Pull the model if not already present
OLLAMA_MODEL=${OLLAMA_MODEL:-aya-expanse:8b}
echo "Pulling ${OLLAMA_MODEL} model (as requested)..."
ollama pull ${OLLAMA_MODEL}

echo "Model ready. Ollama is running."
# Keep Ollama running in the foreground
wait $OLLAMA_PID
