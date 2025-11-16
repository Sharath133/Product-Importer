#!/bin/bash
# Startup script for local development

echo "Starting Acme Product Importer..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "Warning: .env file not found. Creating from .env.example..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "Please update .env with your database and Redis credentials."
    else
        echo "Error: .env.example not found. Please create .env manually."
        exit 1
    fi
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate 2>/dev/null || source venv/Scripts/activate 2>/dev/null

# Install dependencies
echo "Installing dependencies..."
pip install -r backend/requirements.txt

# Run database migrations (if Alembic is set up)
if [ -d "backend/alembic" ]; then
    echo "Running database migrations..."
    cd backend
    alembic upgrade head
    cd ..
fi

echo ""
echo "Setup complete!"
echo ""
echo "To start the application:"
echo "  Terminal 1 (API): uvicorn backend.app.main:app --reload --port 8000"
echo "  Terminal 2 (Worker): dramatiq backend.app.tasks --processes 1 --threads 4"
echo ""
echo "Then open http://localhost:8000 in your browser."

