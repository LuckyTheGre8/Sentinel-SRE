from sentinel_ops.acp import text_message
from sentinel_ops.guided_demo import GuidedDemo
from sentinel_ops.state import StateStore


async def test_guided_demo_measures_outage_approval_and_recovery(tmp_path):
    store = StateStore(tmp_path / "chat.sqlite")
    demo = GuidedDemo(tmp_path, store)

    async def ask(command, session="judge"):
        return await demo.handle("operator", session, text_message(command))

    try:
        assert await ask("normal live request") is None
        assert "Send demo start first" in await ask("demo recover")
        message = text_message("demo start")
        first = await demo.handle("operator", "judge", message)
        assert "HTTP 503" in first
        assert "zero PRs" in first
        assert await demo.handle("operator", "judge", message) == first
        assert "No approved PR" in await ask("demo recover")
        assert "Send demo start first" in await ask("demo approve", "other")
        assert "DEMO-2026-001" in await ask("demo evidence")
        assert "Total PRs: 1" in await ask("demo approve")
        assert "Total PRs: 1" in await ask("demo approve")
        assert "HTTP 200" in await ask("demo recover")
        assert "HTTP 200" in await ask("demo recover")
        assert "HTTP 503" in await ask("demo start")
    finally:
        store.close()


async def test_registered_chat_handler_routes_demo(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from uagents_core.contrib.protocols.chat import ChatAcknowledgement, ChatMessage

    from sentinel_ops.agents.orchestrator_agent import build_orchestrator_agent

    monkeypatch.setenv("SENTINEL_DEMO_MODE", "true")
    store = StateStore(tmp_path / "registered.sqlite")
    agent, _, _ = build_orchestrator_agent(root=tmp_path, mailbox=False, store=store)
    sent = []

    async def send(target, message):
        sent.append(message)

    try:
        handler = agent._signed_message_handlers[ChatMessage.build_schema_digest(ChatMessage)]
        await handler(
            SimpleNamespace(session="judge", send=send), "operator", text_message("demo help")
        )
        assert isinstance(sent[0], ChatAcknowledgement)
        assert "DEMO SANDBOX" in sent[-1].content[0].text
        assert agent._handle_messages_concurrently
    finally:
        store.close()
