#!/bin/bash
# Start Ollama in the background
/bin/ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "Waiting for Ollama to start..."
sleep 5

# Pull the model if not already present
# Pull the model if not already present
echo "Pulling llama3.1:8b model (larger model for better constraint following)..."
ollama pull llama3.1:8b

echo "Model ready. Ollama is running."
# Keep Ollama running in the foreground
wait $OLLAMA_PID
