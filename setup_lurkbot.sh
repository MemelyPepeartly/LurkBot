#!/bin/bash

# Ensure Python is accessible
if ! command -v python &> /dev/null
then
    echo "Python could not be found. Please ensure it is installed and added to your PATH."
    exit
fi

# Create virtual environment
python -m venv lurkbotEnv

# Check if virtual environment was created successfully
if [ ! -d "lurkbotEnv" ]; then
    echo "Failed to create virtual environment. Please check for errors."
    exit
fi

# Activate virtual environment
source lurkbotEnv/Scripts/activate

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Deactivate virtual environment
deactivate

echo "Setup complete. To activate the virtual environment, run:"
echo "source lurkbotEnv/Scripts/activate"
