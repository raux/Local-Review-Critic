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

AGENT_MD_SYSTEM = (
    "You are a technical documentation writer. "
    "Generate a concise AGENT.MD markdown document that describes the given AI agent. "
    "Include the following sections: # Agent Name, ## Role, ## System Prompt, "
    "## Capabilities, ## Behavior Patterns, ## Constraints. "
    "Base your analysis on the agent's system prompt and its sample output."
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


def _chat_with_reasoning(client: OpenAI, model: str, system: str, user: str) -> dict:
    """
    Send a single-turn chat request and return both the assistant text and reasoning/thinking.
    Returns a dict with 'content' and optionally 'reasoning' if the model provides it.
    """
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.4,
    )
    result = {
        "content": response.choices[0].message.content or "",
    }
    # Check if the model provides reasoning/thinking (e.g., o1 models)
    if hasattr(response.choices[0].message, 'reasoning_content') and response.choices[0].message.reasoning_content:
        result["reasoning"] = response.choices[0].message.reasoning_content
    return result


def generate_code(client: OpenAI, model: str, user_prompt: str) -> dict:
    """
    Step 1: Generator creates initial code from user request.

    Returns a dict with:
      - content: the generated code/response
      - reasoning: optional thinking/reasoning from the model
    """
    logger.info("Step 1: Generator drafting initial code for prompt: %s", user_prompt)
    result = _chat_with_reasoning(client, model, GENERATOR_SYSTEM, user_prompt)
    logger.info("Generator draft response (length: %d chars)", len(result["content"]))
    return result


def critique_code(client: OpenAI, model: str, draft_code: str) -> dict:
    """
    Step 2: Critic reviews the draft code.

    Returns a dict with:
      - content: the review/feedback
      - reasoning: optional thinking/reasoning from the model
    """
    logger.info("Step 2: Critic reviewing the draft...")
    critic_input = (
        f"Please review the following code and suggest specific improvements:\n\n"
        f"{draft_code}"
    )
    result = _chat_with_reasoning(client, model, CRITIC_SYSTEM, critic_input)
    logger.info("Critic review response (length: %d chars)", len(result["content"]))
    return result


def synthesize_code(client: OpenAI, model: str, user_prompt: str, draft: str, critic_comments: str) -> dict:
    """
    Step 3: Generator produces final refined code incorporating feedback.

    Returns a dict with:
      - content: the final code/response
      - reasoning: optional thinking/reasoning from the model
      - final_code: extracted code without markdown fences
    """
    logger.info("Step 3: Generator synthesizing final code with critic feedback...")
    synthesis_prompt = (
        f"Original request: {user_prompt}\n\n"
        f"Your first draft:\n{draft}\n\n"
        f"Code review feedback:\n{critic_comments}\n\n"
        f"Please produce the final, improved version of the code incorporating "
        f"all the reviewer's suggestions."
    )
    result = _chat_with_reasoning(client, model, GENERATOR_SYSTEM, synthesis_prompt)
    logger.info("Generator final response (length: %d chars)", len(result["content"]))

    # Extract clean code
    result["final_code"] = extract_code(result["content"])
    logger.info("Final code extracted (length: %d chars)", len(result["final_code"]))

    return result


def generate_agent_md(client: OpenAI, model: str, agent_name: str,
                      system_prompt: str, sample_output: str) -> dict:
    """
    Generate an AGENT.MD markdown document describing the given agent.

    Returns a dict with:
      - content: the generated AGENT.MD markdown
      - reasoning: optional thinking/reasoning from the model
    """
    logger.info("Generating AGENT.MD for agent: %s", agent_name)
    user_input = (
        f"Generate an AGENT.MD document for the following AI agent:\n\n"
        f"**Agent Name:** {agent_name}\n\n"
        f"**System Prompt:** {system_prompt}\n\n"
        f"**Sample Output:**\n{sample_output}\n\n"
        f"Create a well-structured markdown document that fully describes "
        f"this agent's role, capabilities, and behavior."
    )
    result = _chat_with_reasoning(client, model, AGENT_MD_SYSTEM, user_input)
    logger.info("AGENT.MD for %s generated (length: %d chars)", agent_name, len(result["content"]))
    return result


def run_pipeline(client: OpenAI, model: str, user_prompt: str) -> dict:
    """
    Execute the three-step Generator → Critic → Synthesis pipeline.
    This function maintains backward compatibility with the existing /chat endpoint.

    Returns a dict with:
      - chat_history: list of {role, content} messages shown in the UI
      - critic_comments: raw feedback from Agent B
      - final_code: cleaned final output from the second Generator call
    """
    logger.info("Starting pipeline with user prompt: %s", user_prompt)
    chat_history: list[dict] = []

    # Step 1 – Generator (first pass)
    gen_result = generate_code(client, model, user_prompt)
    chat_history.append({"role": "generator", "content": gen_result["content"]})

    # Step 2 – Critic reviews the draft
    critic_result = critique_code(client, model, gen_result["content"])
    critic_comments = critic_result["content"]
    chat_history.append({"role": "critic", "content": critic_comments})

    # Step 3 – Generator produces the final refined code
    synth_result = synthesize_code(client, model, user_prompt, gen_result["content"], critic_comments)
    chat_history.append({"role": "generator", "content": synth_result["content"]})

    logger.info("Pipeline completed successfully.")

    return {
        "chat_history": chat_history,
        "critic_comments": critic_comments,
        "final_code": synth_result["final_code"],
    }
