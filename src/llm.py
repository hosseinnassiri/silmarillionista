"""Single source of truth for chat/embedding client construction (Azure OpenAI)."""

from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings

from src.config import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_CHAT_DEPLOYMENT,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_ROUTER_DEPLOYMENT,
)


def get_chat_llm(**kwargs) -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_deployment=AZURE_OPENAI_CHAT_DEPLOYMENT,
        **kwargs,
    )


def get_router_llm(**kwargs) -> AzureChatOpenAI:
    """Cheap/fast deployment for router_node's 3-way classification only —
    everything else (Cypher generation, synthesis) stays on get_chat_llm().
    reasoning_effort="none" is deliberate, not just a cost knob: gpt-5.6-class
    models default to "medium" reasoning, and Azure's own guidance lists
    exactly this shape of work (latency-critical classification, no chained
    tool calls) as the textbook case for turning it off. This also sidesteps
    a real gpt-5.6 gotcha — function/tool calls combined with reasoning_effort
    other than "none" are rejected outright on Chat Completions — though
    router_node's with_structured_output() defaults to the json_schema method
    (native Structured Outputs), not tool calling, so that specific failure
    mode doesn't actually apply here today.
    """
    return AzureChatOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_deployment=AZURE_OPENAI_ROUTER_DEPLOYMENT,
        reasoning_effort="none",
        **kwargs,
    )


def get_embeddings() -> AzureOpenAIEmbeddings:
    return AzureOpenAIEmbeddings(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_deployment=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    )
