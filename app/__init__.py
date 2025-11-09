import os
from flask import Flask
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

def create_app():
    app = Flask(__name__)

    # Secret key for sessions (set in .env)
    app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")

    # Terraform Cloud configuration
    app.config['TERRAFORM_TOKEN'] = os.getenv('TERRAFORM_TOKEN')
    app.config['TERRAFORM_ORG_NAME'] = os.getenv('TERRAFORM_ORG_NAME')

    # LLM configuration (Hugging Face)
    app.config['LLM_PROVIDER'] = os.getenv('LLM_PROVIDER', 'hf')
    app.config['HF_TOKEN'] = os.getenv('HF_TOKEN')

    # MongoDB
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_dbname = os.getenv("MONGO_DB", "llm_terraform")
    mongo_client = MongoClient(mongo_uri)
    app.mongo = mongo_client[mongo_dbname]

    # Register Flask blueprint (contains auth, dashboard, prompt routes)
    from app.main import main_bp
    app.register_blueprint(main_bp)

    return app
