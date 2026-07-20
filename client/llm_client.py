from openai import APIConnectionError, AsyncOpenAI, RateLimitError, APIError
import os
from typing import Any, AsyncGenerator
from client.response import TextDelta, StreamEvent, TokenUsage, EventType
import asyncio

class LLMClient:
    """Thin async wrapper around the OpenAI chat completions API.

    Owns a single reusable ``AsyncOpenAI`` instance and exposes a unified
    ``chat_completion`` entry point that yields ``StreamEvent`` objects for
    both streaming and non-streaming calls. Credentials and base URL are read
    from ``OPENAI_API_KEY`` and ``OPENAI_BASE_URL`` environment variables.
    """

    def __init__(self)-> None:
        """Create a client with no underlying OpenAI connection yet.

        The real ``AsyncOpenAI`` instance is created lazily on first use via
        ``get_client`` so construction stays cheap and does not require env
        vars to be present until a request is made.
        """
        self._client : AsyncOpenAI | None = None
        self.max_retries : int = 3

    def get_client(self)-> AsyncOpenAI:
        """Return the shared ``AsyncOpenAI`` instance, creating it if needed.

        Why this exists:
            Centralizes client construction so every call path reuses one
            HTTP client (connection pooling) instead of building a new one
            per request.

        Returns:
            AsyncOpenAI: Configured with ``api_key`` from ``OPENAI_API_KEY``
            and ``base_url`` from ``OPENAI_BASE_URL``. Raises if the API key
            is missing when the client is first constructed.
        """
        if self._client is None:
            self._client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))
        return self._client

    async def close(self)-> None:
        """Shut down the underlying OpenAI client and clear the cached handle.

        Why this exists:
            Releases network resources (open connections) when the app is
            done. Safe to call if no client was ever created.
        """
        if self._client:
            await self._client.close()
            self._client = None

    async def chat_completion(self, messages: list[dict[str, any]], stream: bool = True,)->AsyncGenerator[StreamEvent, None]:
        """Run a chat completion and yield normalized ``StreamEvent`` values.

        Builds the OpenAI request kwargs (model, messages, stream flag), then
        delegates to either ``_stream_response`` or ``_non_stream_response``.
        Callers always consume an async iterator of events, so streaming and
        non-streaming share the same consumer API.

        Args:
            messages: Chat history in OpenAI format — a list of dicts with
                at least ``role`` (e.g. ``system``, ``user``, ``assistant``)
                and ``content``. Passed straight through to the API.
            stream: If ``True`` (default), tokens arrive as incremental
                ``TEXT_DELTA`` events and end with ``MESSAGE_COMPLETE``.
                If ``False``, a single ``MESSAGE_COMPLETE`` event is yielded
                with the full reply text.

        Yields:
            StreamEvent: Token deltas and/or a final completion event,
            depending on ``stream``.
        """
        client = self.get_client()
        kwargs= {
            "model":"gpt-4o-mini",
            "messages":messages,
            "stream":stream,
        }

        for attempt in range(self.max_retries+1):
            try:
                if stream:
                    async for event in self._stream_response(client, kwargs):
                        yield event
                else:
                    event=await self._non_stream_response(client, kwargs)
                    yield event
                return
            except RateLimitError as e:
                if attempt < self.max_retries:
                    wait_time=2**attempt
                    await asyncio.sleep(wait_time)
                else:
                    yield StreamEvent(
                        type=EventType.ERROR,
                        error=f"Rate limit exceeded: {e}",
                    )
                    return

            except APIConnectionError as e:
                if attempt < self.max_retries:
                    wait_time=2**attempt
                    await asyncio.sleep(wait_time)
                else:
                    yield StreamEvent(
                        type=EventType.ERROR,
                        error=f"API connection error: {e}",
                    )
                    return

            except APIError as e:
                    yield StreamEvent(
                        type=EventType.ERROR,
                        error=f"API error: {e}",
                    )
                    return


    async def _stream_response(self, client: AsyncOpenAI, kwargs: dict[str, Any])-> AsyncGenerator[StreamEvent, None]:
        """Consume an OpenAI streaming completion and map chunks to events.

        Logic:
            1. Call ``chat.completions.create`` with ``stream=True`` in kwargs.
            2. Walk each SSE chunk from the async stream.
            3. If a chunk carries usage (typically only when the request
               includes ``stream_options.include_usage``), store it as
               ``TokenUsage`` for the final event.
            4. Skip chunks with an empty ``choices`` list (e.g. usage-only
               trailing chunks).
            5. For each choice delta with text, yield a ``TEXT_DELTA`` event.
            6. Capture ``finish_reason`` when the model signals completion.
            7. After the stream ends, yield one ``MESSAGE_COMPLETE`` event
               with accumulated ``finish_reason`` and ``usage``.

        Args:
            client: The shared ``AsyncOpenAI`` instance from ``get_client``.
            kwargs: Request body for ``create`` — must include ``model``,
                ``messages``, and ``stream=True``. Extra OpenAI options can
                be added by the caller before invoke.

        Yields:
            StreamEvent: Zero or more ``TEXT_DELTA`` events, then one
            ``MESSAGE_COMPLETE``. ``usage`` may be ``None`` if the API did
            not return usage on the stream.
        """
        response= await client.chat.completions.create(**kwargs)
        usage: TokenUsage | None = None
        finish_reason: str | None = None

        async for chunk in response:
            if hasattr(chunk, "usage") and chunk.usage:
                usage=TokenUsage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                    cached_tokens=chunk.usage.prompt_tokens_details.cached_tokens,
                )
            if not chunk.choices:
                continue

            choice=chunk.choices[0]
            delta=choice.delta

            if choice.finish_reason:
                finish_reason=choice.finish_reason

            if delta.content:
                yield StreamEvent(
                    type=EventType.TEXT_DELTA,
                    text_delta=TextDelta(content=delta.content),
                )

        yield StreamEvent(
            type=EventType.MESSAGE_COMPLETE,
            finish_reason=finish_reason,
            usage=usage
        )

    async def _non_stream_response(self, client: AsyncOpenAI, kwargs: dict[str, Any])-> StreamEvent:
        """Run a non-streaming completion and return a single final event.

        Logic:
            1. Call ``chat.completions.create`` (``stream`` should be false
               in kwargs) and wait for the full response.
            2. Read the first choice's message content into a ``TextDelta``
               when present (full reply in one piece).
            3. If the response includes usage, map it into ``TokenUsage``,
               including cached prompt tokens from ``prompt_tokens_details``.
            4. Return one ``MESSAGE_COMPLETE`` ``StreamEvent`` with text,
               usage, and finish reason.

        Args:
            client: The shared ``AsyncOpenAI`` instance from ``get_client``.
            kwargs: Request body for ``create`` — must include ``model``,
                ``messages``, and typically ``stream=False``.

        Returns:
            StreamEvent: A ``MESSAGE_COMPLETE`` event carrying the full
            assistant text (when any), token usage (when any), and the
            model's ``finish_reason``.
        """
        response= await client.chat.completions.create(**kwargs)
        choice=response.choices[0]
        message=choice.message

        text_delta=None
        if message.content:
            text_delta=TextDelta(content=message.content)

        if response.usage:
            usage=TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                cached_tokens=response.usage.prompt_tokens_details.cached_tokens,
            )

        return StreamEvent(
            type=EventType.MESSAGE_COMPLETE,
            usage=usage,
            finish_reason=response.choices[0].finish_reason,
            text_delta=text_delta,
        )


        
