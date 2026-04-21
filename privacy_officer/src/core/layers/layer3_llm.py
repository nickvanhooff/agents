import os
import re
import json
import asyncio
import logging
from typing import Optional

import ollama
from openai import OpenAI, AsyncOpenAI

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# LLM_BACKEND selects which inference server to use: "vllm" (default) or "ollama".
LLM_BACKEND = os.getenv('LLM_BACKEND', 'vllm')

# vLLM — OpenAI-compatible API server. Defaults work for Docker Compose setup.
VLLM_HOST = os.getenv('VLLM_HOST', 'http://localhost:8001')
vllm_client = OpenAI(base_url=f"{VLLM_HOST}/v1", api_key="not-needed")
vllm_async_client = AsyncOpenAI(base_url=f"{VLLM_HOST}/v1", api_key="not-needed")

# Ollama — kept as fallback backend.
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
# httpx (used by ollama-python) defaults to ~60s read timeout if unset, which aborts
# /api/chat while the server is still loading a large model into VRAM (see Ollama logs: 1m0s).
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "600"))
ollama_client = ollama.Client(host=OLLAMA_HOST, timeout=OLLAMA_TIMEOUT_SECONDS)

logging.info(f"LLM backend: {LLM_BACKEND}")
if LLM_BACKEND == 'vllm':
    logging.info(f"Connecting to vLLM at: {VLLM_HOST}")
else:
    logging.info(f"Connecting to Ollama at: {OLLAMA_HOST} (HTTP timeout {OLLAMA_TIMEOUT_SECONDS}s)")


def parse_llm_json_response(raw: str) -> Optional[dict]:
    """
    Parse a JSON object from LLM output. Qwen/Ollama usually return clean JSON; Gemma and others
    may wrap content in markdown fences or add prose despite format="json".
    """
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()

    def _try_load(fragment: str) -> Optional[dict]:
        try:
            obj = json.loads(fragment)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None

    direct = _try_load(s)
    if direct is not None:
        return direct

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", s, re.IGNORECASE)
    if fence:
        inner = _try_load(fence.group(1).strip())
        if inner is not None:
            logging.info("Parsed LLM JSON from markdown code fence (model returned extra wrapping).")
            return inner

    start = s.find("{")
    if start >= 0:
        try:
            obj, _ = json.JSONDecoder().raw_decode(s[start:])
            if isinstance(obj, dict):
                logging.info("Parsed LLM JSON via raw_decode (leading/trailing non-JSON text stripped).")
                return obj
        except json.JSONDecodeError:
            pass

    return None


def get_dynamic_prompt(config: Optional[dict] = None) -> str:
    """Builds a strict JSON extraction prompt based on user settings."""
    prompt = """You are a strict data extraction tool. Your ONLY job is to extract identifying entities from the text.
You MUST output ONLY a valid JSON object. Do not output anything else.
The JSON object must contain arrays of exact strings found in the text that match the requested categories.
If no matches are found for a category, return an empty array [] for that key.

=== CATEGORIES TO EXTRACT ===\n"""

    if not config or config.get("names", True):
        prompt += "- 'names': Personal names (students, teachers, staff)\n"
    if not config or config.get("titles", True):
        prompt += "- 'titles': Honorifics or titles directly before a name (e.g., Meneer, Mevrouw, Dr., docent, mentor)\n"
    if not config or config.get("locations", True):
        prompt += "- 'locations': Specific locations (cities, campuses, street names)\n"
    if not config or config.get("courses", True):
        prompt += "- 'courses': Specific named courses or department names\n"
    if not config or config.get("pii", True) or config.get("student_nr", True):
        prompt += "- 'pii': Email addresses, student numbers, employee numbers, phone numbers\n"
    if not config or config.get("physical", True):
        prompt += "- 'physical': Physical appearance details identifying a person (e.g., kaal, baard, rode jas)\n"

    prompt += "\n=== STRICT RULES ===\n"
    prompt += "1. The strings in your JSON arrays MUST be EXACT substrings from the input text. Do not correct spelling or alter capitalization.\n"
    prompt += "2. DO NOT extract generic words (like 'workshop', 'bibliotheek', 'kantine', 'eten', 'voeten', 'blij').\n"
    prompt += "3. DO NOT extract standalone numbers or grades (like '1', '4', '8.5').\n"
    prompt += "4. The output must be parsable by Python's json.loads().\n"

    if config and not config.get("titles", True):
        prompt += "5. DO NOT extract honorifics or titles (Meneer, Mevrouw, Dhr., Mevr., Dr., docent, mentor, coach, begeleider, professor) — not even as part of a name string.\n"
    if config and not config.get("names", True):
        prompt += "6. DO NOT extract personal names of any kind.\n"
    if config and not config.get("locations", True):
        prompt += "7. DO NOT extract locations, cities, campuses or street names.\n"
    if config and not config.get("physical", True):
        prompt += "8. DO NOT extract physical appearance details.\n"
    if config and not config.get("courses", True):
        prompt += "9. DO NOT extract course names or department names.\n"
    return prompt


async def anonymize_with_llm_async(
    text: str,
    model_name: str,
    config: Optional[dict] = None,
) -> str:
    """Run Layer 3 LLM on a single text. Returns anonymized text or [NEEDS_REVIEW_*] on failure."""
    try:
        prompt_str = get_dynamic_prompt(config)
        messages = [
            {"role": "system", "content": prompt_str},
            {"role": "user", "content": text},
        ]

        if LLM_BACKEND == 'vllm':
            completion = await vllm_async_client.chat.completions.create(
                model=model_name,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0,
            )
            raw_content = completion.choices[0].message.content.strip()
        else:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    ollama_client.chat, model=model_name, messages=messages, format="json"
                ),
                timeout=OLLAMA_TIMEOUT_SECONDS,
            )
            raw_content = response['message']['content'].strip()

        extracted_entities = parse_llm_json_response(raw_content)
        if extracted_entities is None:
            logging.error(f"Failed to parse JSON for input: {text[:30]}")
            return f"[NEEDS_REVIEW_ERROR] {text}"

        anonymized = text
        tag_map = {
            "names": "[NAME]",
            "titles": "[TITLE]",
            "locations": "[LOCATION]",
            "courses": "[COURSE/DEPT]",
            "pii": "[PII]",
            "physical": "[PHYSICAL_DESCRIPTOR]"
        }

        llm_replaced = []
        for category, entities in extracted_entities.items():
            if isinstance(entities, list) and category in tag_map:
                tag = tag_map[category]
                entities.sort(key=len, reverse=True)
                for entity in entities:
                    if isinstance(entity, str) and entity and entity in anonymized:
                        pattern = re.compile(re.escape(entity), re.IGNORECASE)
                        new_anonymized = pattern.sub(tag, anonymized)
                        if new_anonymized != anonymized:
                            llm_replaced.append(f"'{entity}' ({category} → {tag})")
                            anonymized = new_anonymized

        if llm_replaced:
            logging.info(f"LLM caught {len(llm_replaced)} additional entities: {', '.join(llm_replaced)}")

        return anonymized

    except asyncio.TimeoutError:
        logging.error(f"Ollama timeout after {OLLAMA_TIMEOUT_SECONDS}s on '{text[:30]}...'")
        return f"[NEEDS_REVIEW_TIMEOUT] {text}"
    except Exception as e:
        logging.error(f"LLM error on '{text[:30]}...': {e}")
        return f"[NEEDS_REVIEW_ERROR] {text}"
