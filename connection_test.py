from google import genai
from google.genai import types

client = genai.Client(vertexai=True, project="bsc-research-project-511410", location="global")
r = client.models.generate_content(
    model="gemini-3.8-flash",
    contents="Reply with the single word OK.",
    config=types.GenerateContentConfig(temperature=0, max_output_tokens=50),
)
print("TEXT:", r.text)
print("USAGE:", r.usage_metadata)