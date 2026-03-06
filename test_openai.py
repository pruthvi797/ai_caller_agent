import os
from dotenv import load_dotenv
from openai import OpenAI

# Load .env file
load_dotenv()

# Get API key
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    print("❌ OPENAI_API_KEY not found in .env file")
    exit()

print("✅ Key loaded:", api_key[:12] + "...")

try:
    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": "Say hello in one sentence"}
        ],
        max_tokens=20
    )

    print("\n✅ API WORKING")
    print("Response:", response.choices[0].message.content)

except Exception as e:
    print("\n❌ API FAILED")
    print(e)