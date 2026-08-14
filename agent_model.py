###############
# AGENT MODEL #
###############
import datetime
from besser.BUML.metamodel.state_machine.state_machine import Body, Condition, ConfigProperty, CustomCodeAction
from besser.BUML.metamodel.state_machine.agent import Agent, AgentReply, LLMReply, LLMChatReply, RAGReply, DBReply, WebCrawlLLMReply, WebSocketReplyMarkdown, WebSocketReplyHTML, WebSocketReplySpeech, WebSocketReplyOptions, WebSocketReplyLocation, WebSocketReplyFile, WebSocketReplyImage, WebSocketReplyDataframe, WebSocketReplyPlotly, LLMOpenAI, LLMHuggingFace, LLMHuggingFaceAPI, LLMReplicate, RAGVectorStore, RAGTextSplitter, Tool, Skill, Workspace, ReasoningState, ReceiveTextEvent, ReceiveFileEvent, ReceiveJSONEvent, ReceiveMessageEvent, WildcardEvent, DummyEvent
from besser.BUML.metamodel.structural import Metadata
import operator

agent = Agent('Agent_Diagram')


# INTENTS

# RAG CONFIGURATIONS
rag_0_vector_store = RAGVectorStore(
    embedding_provider='openai',
    embedding_parameters={'api_key_property': 'nlp.OPENAI_API_KEY'},
    persist_directory='vector_store/rag_db',
)
rag_0_splitter = RAGTextSplitter(
    splitter_type='recursive_character',
    chunk_size=1000,
    chunk_overlap=100,
)
rag_0_rag = agent.new_rag(
    name='RAG_DB',
    vector_store=rag_0_vector_store,
    splitter=rag_0_splitter,
    llm_name='',
    llm_prompt=None,
    k=8,
    num_previous_messages=2,
    use_hybrid_rag=True,
    bm25_weight=0.6,
)

default_llm = None

# STATES
greetings_state = agent.new_state('greetings_state', initial=True)

# greetings_state state
def greetings_body(session: 'Session'):
    session.reply(
        "Hi! 👋 I'm the BESSER assistant — built with the BESSER Agentic Framework (BAF). "
        "Ask me anything about BESSER!"
    )
    websocket_platform.reply_options(session, options=_FAQS)

CustomCodeAction_greetings_state = CustomCodeAction(callable=greetings_body)
greetings_state_body = Body('greetings_state_body')
greetings_state_body.add_action(CustomCodeAction_greetings_state)

greetings_state.set_body(greetings_state_body)
greetings_state.when_no_intent_matched().go_to(chat_state)

# chat_state state
chat_state = agent.new_state('chat_state')

def chat_body(session: 'Session'):
    session.run_rag(rag_0_rag)

CustomCodeAction_chat_state = CustomCodeAction(callable=chat_body)
chat_state_body = Body('chat_state_body')
chat_state_body.add_action(CustomCodeAction_chat_state)

chat_state.set_body(chat_state_body)
chat_state.when_no_intent_matched().go_to(chat_state)
