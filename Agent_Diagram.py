# You may need to add your working directory to the Python path. To do so, uncomment the following lines of code
# import sys
# sys.path.append("/Path/to/directory/besser-agentic-framework") # Replace with your directory path

import json
import logging
import operator
import os
import pickle
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from baf.core.agent import Agent
from baf.library.transition.events.base_events import *
from baf.nlp.llm.llm_huggingface import LLMHuggingFace
from baf.nlp.llm.llm_huggingface_api import LLMHuggingFaceAPI
from baf.nlp.llm.llm_ollama import LLMOllama
from baf.nlp.llm.llm_openai_api import LLMOpenAI
from baf.nlp.llm.llm_replicate_api import LLMReplicate
from baf.core.session import Session
from baf.nlp.intent_classifier.intent_classifier_configuration import LLMIntentClassifierConfiguration, SimpleIntentClassifierConfiguration
from baf.nlp.speech2text.openai_speech2text import OpenAISpeech2Text
from baf.nlp.text2speech.openai_text2speech import OpenAIText2Speech
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_community.document_loaders.recursive_url_loader import RecursiveUrlLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from baf import nlp
from baf.nlp.rag.rag import RAG, RAGMessage, HybridRAG
from baf.exceptions.logger import logger
from system_prompt import SYSTEM_PROMPT
from translations import LANG_CODE_TO_NAME

# Configure the logging module
logging.basicConfig(level=logging.INFO, format='{levelname} - {asctime}: {message}', style='{')

_HERE = os.path.dirname(os.path.abspath(__file__))


# Create the bot
agent = Agent('Agent_Diagram')
# Load bot properties stored in a dedicated file
agent.load_properties('config.yaml')

# Define the platform your chatbot will use
platform = agent.use_websocket_platform(use_ui=False)

gpt = LLMOpenAI(agent=agent, name='gpt-5.4-mini', parameters={'temperature': 0})

##############################
# RAG CONFIGURATIONS
##############################

rag_db_vector_store = Chroma(
    embedding_function=OpenAIEmbeddings(openai_api_key=agent.get_property(nlp.OPENAI_API_KEY)),
    persist_directory='vector_store/rag_db'
)
rag_db_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)

_SPLITS_PATH = os.path.join('vector_store', 'rag_db', 'splits.pkl')
_facts_path  = os.path.join(_HERE, 'besser_facts.md')

_BESSER_DOMAINS = ('besser.readthedocs.io', 'besser-pearl.org', 'github.com/BESSER-PEARL', 'besser-agentic-framework.readthedocs.io')
_DOCS_ROOT = 'https://besser.readthedocs.io/en/latest/'

_EXCLUDE_URL_FRAGMENTS = (
    'genindex', '/api/', 'releases/v1', 'releases/v2', 'releases/v3',
    'releases/v4', 'releases/v5', 'releases/v6', '_static/', '_sources/', 'search.html',
)


def _bs4_extractor(html: str) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    canonical = soup.find('link', attrs={'rel': 'canonical'})
    page_url = canonical['href'] if canonical else _DOCS_ROOT
    main = (
        soup.find('div', role='main') or soup.find('div', class_='rst-content') or
        soup.find('article') or soup.find('main') or soup
    )
    for tag in main.find_all(['script', 'style', 'nav']):
        tag.decompose()
    for tag in main.select('.headerlink, .toctree-wrapper'):
        tag.decompose()
    for a_tag in main.find_all('a', href=True):
        href = a_tag['href']
        if href.startswith('#'):
            a_tag.replace_with(a_tag.get_text())
            continue
        full_url = urljoin(page_url, href)
        text = a_tag.get_text().strip()
        if any(domain in full_url for domain in _BESSER_DOMAINS):
            a_tag.replace_with(f'{text} [{full_url}]' if text else full_url)
        else:
            a_tag.replace_with(text)
    result = ' '.join(main.get_text().split())
    dialog_links = []
    for dialog in soup.find_all('dialog'):
        for a_tag in dialog.find_all('a', href=True):
            href = a_tag['href']
            if href.startswith('#'):
                continue
            full_url = urljoin(page_url, href)
            if any(domain in full_url for domain in _BESSER_DOMAINS):
                text = a_tag.get_text().strip()
                dialog_links.append(f'{text} [{full_url}]' if text else full_url)
    if dialog_links:
        result += ' ' + ' '.join(dialog_links)
    return result


if rag_db_vector_store._collection.count() == 0:
    facts_loader = TextLoader(_facts_path, encoding='utf-8')
    logger.info('Crawling BESSER documentation and website')
    docs_loader = RecursiveUrlLoader(
        url='https://besser.readthedocs.io/en/latest/',
        max_depth=3, extractor=_bs4_extractor, prevent_outside=True, timeout=20,
    )
    website_loader = RecursiveUrlLoader(
        url='https://besser-pearl.org/',
        max_depth=3, extractor=_bs4_extractor, prevent_outside=True, timeout=20,
    )
    baf_loader = RecursiveUrlLoader(
        url='https://besser-agentic-framework.readthedocs.io/latest/',
        max_depth=3, extractor=_bs4_extractor, prevent_outside=True, timeout=20,
    )
    besser_wiki_loader = RecursiveUrlLoader(
        url='https://besser.readthedocs.io/en/wiki/',
        max_depth=3, extractor=_bs4_extractor, prevent_outside=True, timeout=20,
    )
    baf_wiki_loader = RecursiveUrlLoader(
        url='https://besser-agentic-framework.readthedocs.io/latest/wiki/',
        max_depth=3, extractor=_bs4_extractor, prevent_outside=True, timeout=20,
    )
    all_docs = (
        facts_loader.load() + docs_loader.load() + website_loader.load()
        + baf_loader.load() + besser_wiki_loader.load() + baf_wiki_loader.load()
    )
    all_docs = [
        d for d in all_docs
        if not any(frag in d.metadata.get('source', '') for frag in _EXCLUDE_URL_FRAGMENTS)
    ]
    splits = rag_db_splitter.split_documents(all_docs)
    with open(_SPLITS_PATH, 'wb') as f:
        pickle.dump(splits, f)
    splits_for_vector = [
        Document(
            page_content=f"[Source: {s.metadata['source']}]\n{s.page_content}",
            metadata=s.metadata,
        ) if s.metadata.get('source', '').startswith('http') else s
        for s in splits
    ]
    rag_db_vector_store.add_documents(splits_for_vector)
    logger.info(f'Indexed {len(splits)} chunks (facts + readthedocs + besser-wiki + baf-docs + baf-wiki + website)')

_rag_kwargs: dict = {}
if os.path.exists(_SPLITS_PATH):
    with open(_SPLITS_PATH, 'rb') as f:
        _splits_for_bm25 = pickle.load(f)
    _bm25_docs = [
        Document(
            page_content=f"[Source: {s.metadata['source']}]\n{s.page_content}",
            metadata=s.metadata,
        ) if s.metadata.get('source', '').startswith('http') else s
        for s in _splits_for_bm25
    ]
    _rag_kwargs = {'bm25_docs': _bm25_docs}
    _src_counts: dict = {}
    for _s in _splits_for_bm25:
        _src = _s.metadata.get('source', '')
        _domain = _src.split('/')[2] if _src.startswith('http') else 'local'
        _src_counts[_domain] = _src_counts.get(_domain, 0) + 1
    logger.info(f'Corpus: {len(_splits_for_bm25)} chunks across {len(_src_counts)} sources')
    for _domain, _count in sorted(_src_counts.items(), key=lambda x: -x[1]):
        logger.info(f'  {_count:>5}  {_domain}')

rag_db = HybridRAG(
    agent=agent,
    vector_store=rag_db_vector_store,
    splitter=rag_db_splitter,
    llm_name='gpt-5.4-mini',
    llm_prompt=SYSTEM_PROMPT.format(language='English'),
    k=8,
    num_previous_messages=2,
    bm25_weight=0.5,
    **_rag_kwargs)


ic_config = SimpleIntentClassifierConfiguration(
    framework='pytorch',
    num_epochs=50,
    embedding_dim=128,
    hidden_dim=128,
    input_max_num_tokens=15,
    discard_oov_sentences=True,
    check_exact_prediction_match=True,
    activation_last_layer='sigmoid',
    lr=0.001
)

agent.set_default_ic_config(ic_config)

# No LLM configured; consumers referencing default_llm will fail loudly at runtime
default_llm = None


##############################
# INTENTS
##############################


##############################
# CUSTOM CONDITIONS
##############################


##############################
# STATES
##############################


greetings_state = agent.new_state('greetings_state', initial=True)
chat_state      = agent.new_state('chat_state')

_FAQS = [
    'What is BESSER?',
    'What is B-UML?',
    'Do I need to install BESSER?',
    'What generators does BESSER have?',
]

_FALLBACK_MSG = (
    "I'm the BESSER assistant, built with the BESSER Agentic Framework (BAF). "
    "I'm specialised for BESSER questions — could you rephrase that?"
)

SEL_LANG_KEY  = 'user_selected_language'
LAST_LANG_KEY = 'last_detected_language'

_SUPPORTED_LANGS = set(LANG_CODE_TO_NAME.values())


# greetings_state
def greetings_body(session: Session):
    session.reply(
        "Hi! 👋 I'm the BESSER assistant built with the BESSER Agentic Framework (BAF). "
        "Ask me anything about BESSER!"
    )
    platform.reply_options(session, options=_FAQS)

greetings_state.set_body(greetings_body)
greetings_state.when_no_intent_matched().go_to(chat_state)


def _detect_lang_llm(text: str, fallback: str, llm) -> str:
    try:
        prompt = (
            f'What language is the prose of this text written in? '
            f'Reply with the English name only (e.g. German, French, Catalan). '
            f'Ignore English technical terms like LLM, API, BESSER, BAF, UML, Quantum, low-code, metamodel, model-driven-engineering, MDE, Render and so on. '
            f'If the text is too ambiguous to determine (e.g. "Hi", "OK", "Hello", "Thanks", "contact"), reply "ambiguous".\n\n"{text}"'
        )
        result = llm.predict(prompt).strip().rstrip('.')
        for lang in _SUPPORTED_LANGS:
            if lang.lower() in result.lower():
                return lang
        return fallback
    except Exception:
        return fallback


def _post_process(text: str) -> str:
    text = re.sub(
        r'\[([^\]]+)\]\((https?://[^\)\s`\'"]+)\)',
        lambda m: f'[{m.group(2)}]({m.group(2)})',
        text,
    )
    lines = text.split('\n')
    result, counter = [], 0
    for line in lines:
        if re.match(r'^\s*1\.\s', line):
            counter += 1
            line = re.sub(r'^(\s*)1\.', lambda m, c=counter: f'{m.group(1)}{c}.', line, count=1)
        elif line.strip():
            counter = 0
        result.append(line)
    return '\n'.join(result)


# chat_state
def chat_body(session: Session):
    message = session.event.message

    if message.startswith('/lang:'):
        lang_code = message[6:].strip()
        lang_name = LANG_CODE_TO_NAME.get(lang_code, 'English')
        session.set(SEL_LANG_KEY, lang_name)
        session.reply(
            f"Got it — I'll use {lang_name} as my fallback language. "
            f"I'll always follow the language of your questions first. 🌐"
        )
        return

    platform.reply_reasoning_step(session, {
        'kind': 'llm_text', 'step': 1, 'summary': 'Thinking…', 'details': {},
    })

    globe_lang    = session.get(SEL_LANG_KEY)  or 'English'
    history_lang  = session.get(LAST_LANG_KEY) or globe_lang
    detected_lang = _detect_lang_llm(message, history_lang, gpt)
    session.set(LAST_LANG_KEY, detected_lang)

    lang_suffix = (
        f'\n\nIMPORTANT: The Question below is in {detected_lang}. '
        f'Your entire Answer MUST be written in {detected_lang}. '
        f'Do not write any sentence in English.'
        if detected_lang != 'English' else ''
    )

    try:
        rag_message: RAGMessage = rag_db.run(
            message,
            session=session,
            llm_prompt=SYSTEM_PROMPT.format(language=detected_lang) + lang_suffix,
        )
        answer = _post_process(rag_message.answer)
        platform.reply_markdown(session, answer)
    except Exception as exc:
        logger.error(f'RAG error: {exc}')
        session.reply(_FALLBACK_MSG)


chat_state.set_body(chat_body)
chat_state.when_no_intent_matched().go_to(chat_state)


def global_fallback_body(session: Session):
    session.reply(_FALLBACK_MSG)


agent.set_global_fallback_body(global_fallback_body)

# RUN APPLICATION

if __name__ == '__main__':
    agent.run()
