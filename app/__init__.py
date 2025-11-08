import os
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

def create_app():
    app = Flask(__name__)

    # Terraform Cloud configuration
    app.config['TERRAFORM_TOKEN'] = os.getenv('TERRAFORM_TOKEN')
    app.config['TERRAFORM_ORG_NAME'] = os.getenv('TERRAFORM_ORG_NAME')
    app.config['TERRAFORM_WORKSPACE'] = os.getenv('TERRAFORM_WORKSPACE')

    # LLM configuration (Hugging Face only)
    app.config['LLM_PROVIDER'] = os.getenv('LLM_PROVIDER', 'hf')
    app.config['HF_TOKEN'] = os.getenv('HF_TOKEN')

    # Register Flask blueprints
    from app.main import main_bp
    app.register_blueprint(main_bp)

    return app
