from langchain_core.messages import HumanMessage
from llm.llm_config import get_llm
from config.langsmith_config import setup_langsmith_tracing

# Setup LangSmith tracing (returns CallbackManager if enabled)
callback_manager = setup_langsmith_tracing()

setup_langsmith_tracing("ncert-book-engine")


# Get the LLM instance, providing callback_manager if tracing is enabled
llm = get_llm("groq")

invoke_kwargs = {}
if callback_manager is not None:
    invoke_kwargs["callbacks"] = [callback_manager]

response = llm.invoke([
    HumanMessage(content="what is the personalization engine in ncert")
], **invoke_kwargs)

print(response.content)
