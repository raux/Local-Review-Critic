"""
agents.py – Generator and Critic multi-agent logic for Local-Review-Critic.
"""
from __future__ import annotations

import re
from openai import OpenAI


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
    chat_history: list[dict] = []

    # Step 1 – Generator (first pass)
    draft = _chat(client, model, GENERATOR_SYSTEM, user_prompt)
    chat_history.append({"role": "generator", "content": draft})

    # Step 2 – Critic reviews the draft
    critic_input = (
        f"Please review the following code and suggest specific improvements:\n\n"
        f"{draft}"
    )
    critic_comments = _chat(client, model, CRITIC_SYSTEM, critic_input)
    chat_history.append({"role": "critic", "content": critic_comments})

    # Step 3 – Generator produces the final refined code
    synthesis_prompt = (
        f"Original request: {user_prompt}\n\n"
        f"Your first draft:\n{draft}\n\n"
        f"Code review feedback:\n{critic_comments}\n\n"
        f"Please produce the final, improved version of the code incorporating "
        f"all the reviewer's suggestions."
    )
    final_response = _chat(client, model, GENERATOR_SYSTEM, synthesis_prompt)
    chat_history.append({"role": "generator", "content": final_response})

    final_code = extract_code(final_response)

    return {
        "chat_history": chat_history,
        "critic_comments": critic_comments,
        "final_code": final_code,
    }
