"""
agents.py – Generator and Critic multi-agent logic for Local-Review-Critic.
"""
from __future__ import annotations

import logging
import re
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


GENERATOR_SYSTEM = (
    "You are a specialized code generator. "
    "Output only code and brief explanations."
)

CRITIC_SYSTEM = (
    "You are a senior code reviewer. "
    "Analyze the provided code for bugs, efficiency, and security. "
    "Suggest specific improvements."
)


def _chat(client: OpenAI, model: str, system: str, user: str) -> str:
    """Send a single-turn chat request and return the assistant text."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.4,
    )
    return response.choices[0].message.content or ""


def extract_code(text: str) -> str:
    """
    Strip markdown fences from LLM output.
    Returns the inner code block if present, otherwise the full text.
    """
    pattern = r"```(?:\w+)?\n?(.*?)```"
    blocks = re.findall(pattern, text, re.DOTALL)
    if blocks:
        return "\n\n".join(block.strip() for block in blocks)
    return text.strip()


def run_pipeline(client: OpenAI, model: str, user_prompt: str) -> dict:
    """
    Execute the three-step Generator → Critic → Synthesis pipeline.

    Returns a dict with:
      - chat_history: list of {role, content} messages shown in the UI
      - critic_comments: raw feedback from Agent B
      - final_code: cleaned final output from the second Generator call
    """
    logger.info("Starting pipeline with user prompt: %s", user_prompt)
    chat_history: list[dict] = []

    # Step 1 – Generator (first pass)
    logger.info("Step 1: Generator drafting initial code...")
    draft = _chat(client, model, GENERATOR_SYSTEM, user_prompt)
    logger.info("Generator draft response (length: %d chars): %s", len(draft), draft)
    chat_history.append({"role": "generator", "content": draft})

    # Step 2 – Critic reviews the draft
    logger.info("Step 2: Critic reviewing the draft...")
    critic_input = (
        f"Please review the following code and suggest specific improvements:\n\n"
        f"{draft}"
    )
    critic_comments = _chat(client, model, CRITIC_SYSTEM, critic_input)
    logger.info("Critic review response (length: %d chars): %s", len(critic_comments), critic_comments)
    chat_history.append({"role": "critic", "content": critic_comments})

    # Step 3 – Generator produces the final refined code
    logger.info("Step 3: Generator synthesizing final code with critic feedback...")
    synthesis_prompt = (
        f"Original request: {user_prompt}\n\n"
        f"Your first draft:\n{draft}\n\n"
        f"Code review feedback:\n{critic_comments}\n\n"
        f"Please produce the final, improved version of the code incorporating "
        f"all the reviewer's suggestions."
    )
    final_response = _chat(client, model, GENERATOR_SYSTEM, synthesis_prompt)
    logger.info("Generator final response (length: %d chars): %s", len(final_response), final_response)
    chat_history.append({"role": "generator", "content": final_response})

    final_code = extract_code(final_response)
    logger.info("Pipeline completed successfully. Final code extracted (length: %d chars)", len(final_code))

    return {
        "chat_history": chat_history,
        "critic_comments": critic_comments,
        "final_code": final_code,
    }
