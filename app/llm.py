"""
LLM factory for creating configured language model instances.
Supports both OpenAI and Anthropic providers based on .env configuration.
"""

import logging

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from app.config import Config

logger = logging.getLogger(__name__)


def get_llm():
    """
    Factory function to create an LLM instance based on configuration.

    Returns:
        ChatOpenAI or ChatAnthropic instance configured with environment settings.

    Raises:
        ValueError: If LLM_PROVIDER is invalid or required API keys are missing.

    Example:
        llm = get_llm()
        response = llm.invoke("What is the meaning of life?")
    """
    Config.validate()

    provider = Config.get_llm_provider()
    model_name = Config.get_llm_model_name()

    if provider == "openai":
        logger.info(f"Initializing OpenAI LLM with model: {model_name}")
        return ChatOpenAI(
            model=model_name,
            api_key=Config.OPENAI_API_KEY,
            temperature=0,
        )

    elif provider == "anthropic":
        logger.info(f"Initializing Anthropic LLM with model: {model_name}")
        return ChatAnthropic(
            model=model_name,
            api_key=Config.ANTHROPIC_API_KEY,
            temperature=0,
        )

    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


def get_llm_with_structured_output(schema):
    """
    Create an LLM instance with structured output support.

    Args:
        schema: Pydantic model or JSON schema to enforce as output format.

    Returns:
        LLM instance configured for structured output.

    Example:
        from app.agents.state import SubTaskList
        llm = get_llm_with_structured_output(SubTaskList)
        result = llm.invoke("Break down this query into subtasks")
    """
    llm = get_llm()
    return llm.with_structured_output(schema)
