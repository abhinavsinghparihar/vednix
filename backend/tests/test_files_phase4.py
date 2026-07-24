"""
Phase 4 e2e: uploads → extraction → chat-with-file context, vision routing,
and the FTS5 knowledge base injected into LLM turns. All against real storage.
"""

from __future__ import annotations

import base64
import pytest

from ai_engine.engine import AttachmentRef
from services.knowledge import KnowledgeService, chunk_text
from tests.conftest import FakeLLM

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


async def collect(agen) -> str:
    return "".join([c async for c in agen])


# --- FileStore --------------------------------------------------------------

async def test_file_store_saves_and_extracts(files_store):
    row = await files_store.save("notes.txt", "text/plain", "Vednix stores me.".encode())
    assert row.kind == "text" and row.extracted_chars > 0
    assert await files_store.read_text(row.id) == "Vednix stores me."


async def test_two_uploads_same_extension_do_not_collide(files_store):
    """Regression: blob/text paths must be per-upload (a pre-flush column default
    left every file at 'None.<ext>', each upload clobbering the previous one)."""
    first = await files_store.save("a.txt", "text/plain", b"first body")
    second = await files_store.save("b.txt", "text/plain", b"second body")
    assert first.id != second.id
    assert first.path != second.path and first.text_path != second.text_path
    assert await files_store.read_text(first.id) == "first body"
    assert await files_store.read_text(second.id) == "second body"


async def test_file_store_validation(files_store):
    with pytest.raises(ValueError, match="unsupported"):
        await files_store.save("evil.exe", "application/octet-stream", b"MZ..")
    with pytest.raises(ValueError, match="empty"):
        await files_store.save("zero.txt", "text/plain", b"")


async def test_image_stored_without_extraction(files_store):
    row = await files_store.save("dot.png", "image/png", PNG_BYTES)
    assert row.kind == "image" and row.extracted_chars == 0
    b64 = await files_store.read_blob_base64(row.id)
    assert base64.b64decode(b64) == PNG_BYTES


# --- chat-with-file (engine enrichment) ---------------------------------------

async def test_chat_includes_file_context(core, memory, files_store, settings):
    row = await files_store.save("plan.txt", "text/plain", "The secret code is GARUDA-77.".encode())
    llm = FakeLLM()
    conv = await memory.create_conversation()
    engine_core = core(llm, files=files_store)
    session = engine_core.create_session(memory, conv.id)

    await collect(session.stream_reply(
        "what is the secret code?",
        attachments=[AttachmentRef(id=row.id, name=row.name, kind=row.kind, size=row.size)],
    ))

    fed = llm.calls[0][-1]["content"]
    assert "### File: plan.txt" in fed
    assert "GARUDA-77" in fed
    assert fed.endswith("what is the secret code?")


async def test_attachment_skips_plugin_routing(core, memory, files_store):
    row = await files_store.save("clock.txt", "text/plain", "arbitrary text".encode())
    llm = FakeLLM()
    conv = await memory.create_conversation()
    session = core(llm, files=files_store).create_session(memory, conv.id)
    # "what time" would normally hit the time plugin — attachments mean LLM intent
    await collect(session.stream_reply(
        "what time does the file mention?",
        attachments=[AttachmentRef(id=row.id, name=row.name, kind=row.kind, size=row.size)],
    ))
    assert len(llm.calls) == 1 and session.last_plugins == []


async def test_vision_guard_without_vision_model(core, memory, files_store):
    row = await files_store.save("screen.png", "image/png", PNG_BYTES)
    llm = FakeLLM()  # model "fake-model" is not vision-capable; cache lists no vision model
    conv = await memory.create_conversation()
    session = core(llm, files=files_store).create_session(memory, conv.id)

    reply = await collect(session.stream_reply(
        "what's on my screen?",
        attachments=[AttachmentRef(id=row.id, name=row.name, kind=row.kind, size=row.size)],
    ))

    assert "vision-capable model" in reply
    assert "ollama pull" in reply
    assert llm.calls == []  # never called with a guess
    history = await memory.recent_history(conv.id, max_turns=5)
    assert [m["role"] for m in history] == ["user"]  # guidance never persisted (audit B2)


async def test_vision_auto_routes_to_available_vision_model(core, memory, files_store):
    row = await files_store.save("screen.png", "image/png", PNG_BYTES)

    class VisionAwareLLM(FakeLLM):
        async def list_models_cached(self, ttl: float = 30.0):
            return ["fake-model", "llama3.2-vision"]

    llm = VisionAwareLLM()
    conv = await memory.create_conversation()
    session = core(llm, files=files_store).create_session(memory, conv.id)

    reply = await collect(session.stream_reply(
        "describe this image",
        attachments=[AttachmentRef(id=row.id, name=row.name, kind=row.kind, size=row.size)],
    ))

    assert "Routed images to `llama3.2-vision`" in reply
    assert llm.last_model == "llama3.2-vision"
    assert llm.last_images and len(llm.last_images) == 1  # base64 reached the LLM


# --- chunking ------------------------------------------------------------------

def test_chunk_text_boundaries():
    text = ("word " * 400).strip()  # ~2000 chars
    chunks = chunk_text(text, chunk_chars=900, overlap=150)
    assert len(chunks) >= 3
    assert all(len(c) <= 900 for c in chunks)
    assert chunk_text("") == []
    assert chunk_text("  ") == []
    assert len(chunk_text("short", 900, 150)) == 1


# --- knowledge base --------------------------------------------------------------

KB_TEXT = (
    "Deployment handbook. The production deploy window is every Friday at 5 PM IST. "
    "Rollback takes ten minutes via the release dashboard. Notify the on-call engineer "
    "before any change. Security patches may ship out of window with CTO approval. "
) * 4


async def test_knowledge_index_and_fts_search(knowledge):
    doc = await knowledge.add_document("Deploy Handbook", KB_TEXT)
    assert doc.chunk_count >= 2

    hits = await knowledge.search("when is the deploy window")
    assert hits, "FTS5 should find the deploy window chunk"
    assert "Deploy Handbook" in hits[0].title
    assert "Friday" in hits[0].snippet or "deploy" in hits[0].snippet.lower()

    assert await knowledge.delete_document(doc.id) is True
    assert await knowledge.search("deploy window") == []


async def test_knowledge_injected_into_llm_turn(core, memory, knowledge):
    await knowledge.add_document("Deploy Handbook", KB_TEXT)
    llm = FakeLLM()
    conv = await memory.create_conversation()
    session = core(llm, knowledge=knowledge).create_session(memory, conv.id)

    await collect(session.stream_reply("when is the deployment window?"))

    fed = llm.calls[0][-1]["content"]
    assert "knowledge-base excerpts" in fed
    assert "Deploy Handbook" in fed
    assert session.last_kb_sources == ["Deploy Handbook"]


async def test_irrelevant_query_gets_clean_prompt(core, memory, knowledge):
    await knowledge.add_document("Deploy Handbook", KB_TEXT)
    llm = FakeLLM()
    conv = await memory.create_conversation()
    session = core(llm, knowledge=knowledge).create_session(memory, conv.id)
    await collect(session.stream_reply("xyzqq zzz nonexistent term"))
    assert "knowledge-base excerpts" not in llm.calls[0][-1]["content"]
    assert session.last_kb_sources == []


async def test_like_fallback_search(db):
    kb = KnowledgeService(db[1], fts_enabled=False)  # simulate sqlite without FTS5
    await kb.add_document("Notes", "python decorators wrap functions elegantly")
    hits = await kb.search("decorators")
    assert hits and "wrap functions" in hits[0].snippet
