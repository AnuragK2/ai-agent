from client.llm_client import LLMClient
import asyncio

async def main():
    client = LLMClient()
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is capital of India?"}
    ]
    async for event in client.chat_completion(messages=messages, stream=True):
        print(event)


if __name__ == "__main__":
    asyncio.run(main())