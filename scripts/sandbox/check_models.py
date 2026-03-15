# 診断用スクリプト: check_models.py
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# 利用可能なモデルを一覧表示
print("利用可能なモデルリスト:")
for model in client.models.list():
    print(f"Name: {model.name}, Supported Actions: {model.supported_actions}")