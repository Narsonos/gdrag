#!/bin/bash
set -e

mkdir -p /root/.ollama
ollama serve &
echo "Starting ollama...waiting 5 sec"
sleep 5


#Split the space-separated list into an array
IFS=' ' read -r -a MODELS <<< "$PRELOAD_MODELS"

#Iterate over models and preload them
for MODEL in "${MODELS[@]}"; do
    echo "Preloading model: $MODEL"
    ollama pull "$MODEL"
done

wait