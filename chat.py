import os
from pprint import pprint
from dotenv import load_dotenv
from openai import OpenAI

'''connecting through the Generative Engine API for non-streaming responses using openai package.'''

# Load environment variables
load_dotenv()

api_key = os.getenv("LLM_API_KEY")
if not api_key:
    raise SystemExit(
        "Error: LLM_API_KEY is not set. Add it to your environment or .env file before running chat.py."
    )

# Initialize the client with Generative Engine endpoint
client = OpenAI(
    base_url="https://openai.generative.engine.capgemini.com/v1",
    api_key=api_key
)

# Make a request to the API
completion = client.chat.completions.create(
    model="amazon.nova-lite-v1:0",  # Default model for non-RAG use cases
    messages=[
        {
            "role": "user",
            "content": "Write a one-sentence bedtime story about a unicorn."
        }
    ]
)

# Print the response using pprint
print("\n=== Response ===")
pprint(completion.choices[0].message.content)

# To see the full response object
print("\n=== Full Response Object ===")
pprint(completion.model_dump())